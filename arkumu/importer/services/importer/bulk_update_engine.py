import logging
import polars as pl
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

from arkumu.metadata.models import Resource
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
from arkumu.importer.services.importer.bulk_data_analyzer import BulkDataAnalyzer, MAX_INDEXED_VALUE_SIZE

logger = logging.getLogger(__name__)


class UpdateStrategy(Enum):
    """Strategies for handling existing data during bulk imports."""
    SKIP_EXISTING = "skip_existing"  # Skip if resource already exists
    UPDATE_VALUES = "update_values"  # Update existing literal values
    MERGE_TRIPLES = "merge_triples"  # Add new triples, keep existing ones
    REPLACE_ALL = "replace_all"      # Replace all data for the entity
    TIMESTAMP_BASED = "timestamp_based"  # Use timestamps to determine updates


@dataclass
class BulkUpdateStats:
    """Statistics for bulk update operations."""
    rows_processed: int = 0
    cells_processed: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    resources_skipped: int = 0
    triples_created: int = 0
    triples_updated: int = 0
    triples_skipped: int = 0
    row_links_created: int = 0
    errors: int = 0
    truncated_values: int = 0
    multi_value_cells_detected: int = 0
    total_values_created: int = 0
    relationships_created: int = 0
    
    def merge(self, other: 'BulkUpdateStats'):
        """Merge another stats object into this one."""
        self.rows_processed += other.rows_processed
        self.cells_processed += other.cells_processed
        self.resources_created += other.resources_created
        self.resources_updated += other.resources_updated
        self.resources_skipped += other.resources_skipped
        self.triples_created += other.triples_created
        self.triples_updated += other.triples_updated
        self.triples_skipped += other.triples_skipped
        self.row_links_created += other.row_links_created
        self.errors += other.errors
        self.truncated_values += other.truncated_values
        self.multi_value_cells_detected += other.multi_value_cells_detected
        self.total_values_created += other.total_values_created
        self.relationships_created += other.relationships_created


@dataclass
class ResourceUpdate:
    """Represents a potential resource update."""
    uri: str
    new_values: List[str] = field(default_factory=list)  # Changed from new_value to support multiple values
    new_name: Optional[str] = None
    new_datatype: Optional[str] = None
    new_language: Optional[str] = None
    action: UpdateStrategy = UpdateStrategy.SKIP_EXISTING
    existing_resource: Optional[Resource] = None
    is_multi_value: bool = False


class BulkUpdateEngine:
    """
    Handles update strategy logic and action determination for bulk import operations.
    
    Responsibilities:
    - Determine update actions based on existing vs new data
    - Compare resource values and decide on skip/update/create
    - Handle resource conflict resolution
    - Prepare update data with proper truncation and validation
    """
    
    def __init__(self, default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 uri_service: BulkURIService = None,
                 data_analyzer: BulkDataAnalyzer = None):
        """
        Initialize the update engine.
        
        Args:
            default_strategy: Default strategy for handling existing resources
            uri_service: URI service for generating resource URIs
            data_analyzer: Data analyzer for processing input data
        """
        self.default_strategy = default_strategy
        self.uri_service = uri_service
        self.data_analyzer = data_analyzer or BulkDataAnalyzer()
        
        # Initialize RDF properties (will be set later)
        self.rdf_value_prop = None
    
    def set_rdf_properties(self, rdf_value_prop: Resource):
        """Set the RDF properties needed for update operations."""
        self.rdf_value_prop = rdf_value_prop
    
    def prepare_update_data_vectorized(self, df: pl.DataFrame, dataset_name: str, 
                                     column_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        OPTIMIZED: Fully vectorized approach with multi-value support when configured.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            column_configs: Optional column configurations from mapping system
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        if df.height == 0:
            return [], BulkUpdateStats()
        
        # STEP 1: Apply vectorized Unicode normalization
        logger.debug(f"Step 1: Applying vectorized Unicode normalization")
        df_normalized = self.data_analyzer.normalize_unicode_vectorized(df)
        
        # STEP 2: Multi-value analysis with mapping configs
        logger.debug(f"Step 2: Analyzing multi-value columns")
        multi_value_analysis = self.data_analyzer.analyze_dataset_multi_values(df_normalized, column_configs)
        
        # STEP 3: Add row identifiers (start from 0 consistently)
        logger.debug(f"Step 3: Adding row identifiers")
        df_with_ids = df_normalized.with_row_index(name='row_id', offset=0)
        
        # STEP 4: Efficient conversion to updates (vectorized with multi-value support)
        logger.debug(f"Step 4: Converting to ResourceUpdate objects")
        updates = []
        stats = BulkUpdateStats()
        
        # Track statistics properly
        stats.rows_processed = df.height
        
        row_iterator = df_with_ids.iter_rows(named=True)
        
        for row_data in row_iterator:
            row_id_val = row_data.get('row_id', 'unknown')
            
            for column_name, value in row_data.items():
                # Skip internal columns and None column names
                if column_name == 'row_id' or column_name is None:
                    continue
                
                if value is not None and str(value).strip():
                    current_value_str = str(value).strip()
                    
                    # Check if this column is multi-value
                    column_analysis = multi_value_analysis.get(column_name, {"is_multi_value": False})
                    is_multi_value = column_analysis.get("is_multi_value", False)
                    separator = column_analysis.get("separator", ",")
                    
                    # Split values if multi-value
                    if is_multi_value:
                        values = self.data_analyzer.split_cell_values(current_value_str, separator)
                    else:
                        values = [current_value_str]
                    
                    # Process each value (single or multiple)
                    for value_index, value_item in enumerate(values):
                        if not value_item or not value_item.strip():
                            continue
                            
                        value_str = value_item.strip()
                        
                        # Vectorized truncation logic
                        try:
                            original_byte_size = len(value_str.encode('utf-8'))
                            if original_byte_size > MAX_INDEXED_VALUE_SIZE:
                                temp_val = value_str
                                while len(temp_val.encode('utf-8')) > MAX_INDEXED_VALUE_SIZE:
                                    temp_val = temp_val[:-1]
                                value_str = temp_val + "..."
                                stats.truncated_values += 1
                                logger.warning(
                                    f"Value truncated for dataset '{dataset_name}', column '{column_name}', row_id '{row_id_val}'. "
                                    f"Original byte size: {original_byte_size}, new byte size: {len(value_str.encode('utf-8'))}"
                                )
                        except UnicodeEncodeError:
                            logger.warning(f"Could not encode value to check size for dataset '{dataset_name}', column '{column_name}', row_id '{row_id_val}'.")
                        
                        # Create resource update with unique URI for multi-value items
                        if self.uri_service:
                            # For multi-value columns, include value index to make URI unique
                            if is_multi_value and len(values) > 1:
                                cell_uri = self.uri_service.generate_cell_uri(
                                    dataset_name, column_name, row_id_val, value_index
                                )
                            else:
                                cell_uri = self.uri_service.generate_cell_uri(
                                    dataset_name, column_name, row_id_val
                                )
                        else:
                            # Fallback URI generation (for backward compatibility)
                            from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
                            safe_column_name = slugify_uri_part(column_name)
                            display_row_id = int(row_id_val) + 1 if str(row_id_val).isdigit() else row_id_val
                            safe_display_row_id = slugify_uri_part(str(display_row_id))
                            
                            if is_multi_value and len(values) > 1:
                                cell_uri = mint_uri("http://arkumu.org/data", "default", "datasets", 
                                                  dataset_name, safe_column_name, safe_display_row_id, f"v{value_index}")
                            else:
                                cell_uri = mint_uri("http://arkumu.org/data", "default", "datasets", 
                                                  dataset_name, safe_column_name, safe_display_row_id)
                        
                        update = ResourceUpdate(
                            uri=cell_uri,
                            new_values=[value_str],
                            new_name=column_name,
                            new_datatype="http://www.w3.org/2001/XMLSchema#string",
                            action=UpdateStrategy.SKIP_EXISTING,  # Will be determined later
                            is_multi_value=is_multi_value
                        )
                        
                        updates.append(update)
        
        multi_value_count = sum(1 for analysis in multi_value_analysis.values() if analysis.get("is_multi_value", False))
        logger.info(f"Generated {len(updates)} updates for dataset '{dataset_name}' with {multi_value_count} multi-value columns")
        return updates, stats

    def get_existing_resources_bulk(self, uris: List[str]) -> Dict[str, Resource]:
        """
        Efficiently fetch existing resources for a list of URIs.
        """
        existing = Resource.objects.filter(uri__in=uris).select_related()
        return {resource.uri: resource for resource in existing}

    def determine_update_actions(self, df: pl.DataFrame, dataset_name: str,
                               column_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        Determine update actions using Polars DataFrame operations.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            column_configs: Optional column configurations from mapping system
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        # Prepare the basic update data
        updates, action_stats = self.prepare_update_data_vectorized(df, dataset_name, column_configs)
        
        if not updates:
            return updates, action_stats
        
        # Get all URIs and check for existing resources
        all_uris = [update.uri for update in updates]
        existing_resources = self.get_existing_resources_bulk(all_uris)
        
        # Process each update to determine the action
        for update in updates:
            if update.uri in existing_resources:
                existing = existing_resources[update.uri]
                update.existing_resource = existing
                
                # Determine update strategy
                if self.default_strategy == UpdateStrategy.SKIP_EXISTING:
                    update.action = UpdateStrategy.SKIP_EXISTING
                    action_stats.resources_skipped += 1
                elif self.default_strategy == UpdateStrategy.UPDATE_VALUES:
                    # For multi-value fields, we need to compare differently
                    if update.is_multi_value:
                        # For now, always update multi-value fields (complex comparison)
                        update.action = UpdateStrategy.UPDATE_VALUES
                        action_stats.resources_updated += 1
                    else:
                        # For single values, check if the literal value has changed
                        # The existing resource is a cell resource (IRI type)
                        # We need to find the literal resource connected to it via rdf:value triple
                        try:
                            if self.rdf_value_prop:
                                value_triple = Triple.objects.filter(
                                    subject=existing,
                                    predicate=self.rdf_value_prop
                                ).first()
                                
                                if value_triple and value_triple.object:
                                    # Compare the literal value with the new value
                                    current_literal_value = value_triple.object.value
                                    new_value = update.new_values[0]
                                    
                                    if current_literal_value == new_value:
                                        # Value hasn't changed
                                        update.action = UpdateStrategy.SKIP_EXISTING
                                        action_stats.resources_skipped += 1
                                    else:
                                        # Value has changed
                                        update.action = UpdateStrategy.UPDATE_VALUES
                                        action_stats.resources_updated += 1
                                else:
                                    # No existing value triple, so this is effectively new
                                    update.action = UpdateStrategy.UPDATE_VALUES
                                    action_stats.resources_updated += 1
                            else:
                                # No rdf:value property available, default to update
                                update.action = UpdateStrategy.UPDATE_VALUES
                                action_stats.resources_updated += 1
                        except Exception as e:
                            logger.warning(f"Error comparing values for {update.uri}: {e}")
                            # If we can't determine, default to update
                            update.action = UpdateStrategy.UPDATE_VALUES
                            action_stats.resources_updated += 1
                elif self.default_strategy == UpdateStrategy.TIMESTAMP_BASED:
                    # This would need the row data for timestamp comparison
                    # For now, default to UPDATE_VALUES
                    update.action = UpdateStrategy.UPDATE_VALUES
                    action_stats.resources_updated += 1
                else:
                    update.action = UpdateStrategy.UPDATE_VALUES
                    action_stats.resources_updated += 1
            else:
                # New resource
                update.action = UpdateStrategy.UPDATE_VALUES  # Create new
                action_stats.resources_created += 1
        
        return updates, action_stats

    def filter_updates_by_strategy(self, updates: List[ResourceUpdate], 
                                 target_strategies: List[UpdateStrategy]) -> List[ResourceUpdate]:
        """
        Filter updates to only include those with specific strategies.
        
        Args:
            updates: List of ResourceUpdate objects
            target_strategies: List of strategies to include
            
        Returns:
            Filtered list of updates
        """
        return [update for update in updates if update.action in target_strategies]

    def group_updates_by_dataset(self, updates: List[ResourceUpdate]) -> Dict[str, List[ResourceUpdate]]:
        """
        Group updates by dataset for batch processing.
        
        Args:
            updates: List of ResourceUpdate objects
            
        Returns:
            Dictionary mapping dataset names to their updates
        """
        grouped = {}
        
        for update in updates:
            if self.uri_service:
                dataset_name = self.uri_service.extract_dataset_name_from_uri(update.uri)
            else:
                # Fallback parsing
                try:
                    parts = update.uri.split('/')
                    if 'datasets' in parts:
                        datasets_index = parts.index('datasets')
                        if datasets_index + 1 < len(parts):
                            dataset_name = parts[datasets_index + 1]
                        else:
                            dataset_name = "unknown"
                    else:
                        dataset_name = "unknown"
                except:
                    dataset_name = "unknown"
            
            if dataset_name not in grouped:
                grouped[dataset_name] = []
            grouped[dataset_name].append(update)
        
        return grouped

    def validate_updates(self, updates: List[ResourceUpdate]) -> Tuple[List[ResourceUpdate], List[str]]:
        """
        Validate updates for consistency and correctness.
        
        Args:
            updates: List of ResourceUpdate objects to validate
            
        Returns:
            Tuple of (valid_updates, error_messages)
        """
        valid_updates = []
        errors = []
        
        for update in updates:
            # Check required fields
            if not update.uri:
                errors.append(f"Update missing URI")
                continue
            
            if not update.new_values:
                errors.append(f"Update {update.uri} has no values")
                continue
            
            # Validate URI format
            if self.uri_service:
                validation = self.uri_service.validate_uri_pattern(update.uri)
                if not validation["is_valid"]:
                    errors.append(f"Invalid URI pattern {update.uri}: {validation['errors']}")
                    continue
            
            # Validate values
            valid_values = []
            for value in update.new_values:
                if value and str(value).strip():
                    valid_values.append(str(value).strip())
            
            if not valid_values:
                errors.append(f"Update {update.uri} has no valid values after cleaning")
                continue
            
            update.new_values = valid_values
            valid_updates.append(update)
        
        return valid_updates, errors