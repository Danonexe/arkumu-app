import logging
import polars as pl
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import dateutil.parser
from django.db import transaction
import re

from arkumu.metadata.models import Resource
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
from arkumu.importer.services.importer.smart_bulk_updater import (
    UpdateStrategy, BulkUpdateStats, ResourceUpdate, MAX_INDEXED_VALUE_SIZE
)

# Note: We use vectorized Unicode normalization with Polars df.str.normalize("NFC") 
# instead of the old per-cell normalize_string_nfc() function for better performance

logger = logging.getLogger(__name__)


class SmartBulkUpdaterPolars:
    """
    Polars-optimized version of SmartBulkUpdater.
    
    This version uses Polars DataFrames for significantly better performance
    on data analysis and processing operations, especially for large datasets.
    """
    
    def __init__(self, 
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None,
                 institution: str = "DEFAULT",
                 base_uri: str = "http://arkumu.org/data",
                 link_row_cells: bool = False,
                 link_topology: str = "row",
                 multi_value_threshold: float = 0.2
                 ):
        """
        Initialize the Polars-optimized smart bulk updater.
        
        Args:
            default_strategy: Default strategy for handling existing resources
            timestamp_column: Column name containing timestamps for timestamp-based updates
            institution: Institution code for URI generation (will be automatically slugified)
            base_uri: Base URI for resource generation
            link_row_cells: Whether to link cells to rows
            link_topology: Topology for linking cells to rows
            multi_value_threshold: Threshold for detecting multi-value columns (0.2 = 20%)
        """
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
        # Pre-slugify institution once to avoid repeated slugification during URI generation
        self.institution = slugify_uri_part(str(institution)) if institution else "default"
        self.base_uri = base_uri
        self.link_row_cells = link_row_cells
        self.link_topology = link_topology
        self.multi_value_threshold = multi_value_threshold
        
        # Initialize standard RDF properties
        try:
            with transaction.atomic():
                self.has_part_prop, _ = Resource.objects.update_or_create(
                    uri="http://purl.org/dc/terms/hasPart",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": self.institution, "is_placeholder": False}
                )
                self.rdf_value_prop, _ = Resource.objects.update_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": self.institution, "is_placeholder": False}
                )
                self.dcterms_relation_prop, _ = Resource.objects.update_or_create(
                    uri="http://purl.org/dc/terms/relation",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": self.institution, "is_placeholder": False}
                )
        except Exception as e:
            logger.error(f"SBU Polars __init__: Failed to pre-fetch standard RDF properties: {e}", exc_info=True)
            self.has_part_prop = None 
            self.rdf_value_prop = None
            self.dcterms_relation_prop = None

    def _ensure_dataframe(self, data: Union[List[Dict[str, Any]], pl.DataFrame]) -> pl.DataFrame:
        """Convert data to Polars DataFrame if it's not already."""
        if isinstance(data, pl.DataFrame):
            return data
        else:
            return pl.DataFrame(data)

    def _normalize_unicode_vectorized(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized Unicode normalization using Polars built-in string methods.
        This is much more efficient than normalizing each cell individually in Python.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with all string columns normalized to NFC
        """
        # Get all string columns
        string_columns = [col for col in df.columns if df[col].dtype == pl.Utf8]
        
        if not string_columns:
            return df
        
        logger.debug(f"Applying vectorized Unicode NFC normalization to {len(string_columns)} string columns")
        
        # Apply NFC normalization to all string columns at once
        normalized_columns = [
            pl.col(col).str.normalize("NFC").alias(col) for col in string_columns
        ]
        
        # Keep non-string columns unchanged
        non_string_columns = [col for col in df.columns if col not in string_columns]
        all_columns = non_string_columns + normalized_columns
        
        return df.with_columns(all_columns)

    def analyze_column_for_multi_values_polars(self, df: pl.DataFrame, column_name: str) -> dict:
        """
        Simplified analysis: Disable multi-value splitting for now.
        Import everything as single values - split later if needed.
        """
        if column_name not in df.columns:
            return {"is_multi_value": False, "separator": None, "stats": {"percentage": 0.0}}
        
        # Always return single-value for safety and simplicity
        return {
            "is_multi_value": False,
            "separator": None,
            "stats": {
                "percentage": 0.0,
                "confidence_score": 0.0,
                "avg_commas_per_row": 0.0,
                "total_rows": df.height,
                "rows_with_commas": 0
            }
        }

    def analyze_dataset_multi_values_polars(self, df: pl.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Simplified analysis: No multi-value detection - all columns treated as single-value.
        """
        if df.height == 0:
            return {}
        
        multi_value_analysis = {}
        for column_name in df.columns:
            multi_value_analysis[column_name] = {
                "is_multi_value": False,
                "separator": None,
                "stats": {
                    "percentage": 0.0,
                    "confidence_score": 0.0,
                    "avg_commas_per_row": 0.0,
                    "total_rows": df.height,
                    "rows_with_commas": 0
                }
            }
        
        logger.info(f"Multi-value detection disabled - all {len(df.columns)} columns treated as single-value")
        return multi_value_analysis

    def split_cell_values_polars(self, value: str, separator: str = ",") -> List[str]:
        """
        Simplified: No splitting - return single value as list.
        """
        return [value.strip()] if value and value.strip() else []

    def prepare_update_data_vectorized(self, df: pl.DataFrame, dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        OPTIMIZED: Fully vectorized approach without multi-value complexity.
        Much faster since no splitting logic needed.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        if df.height == 0:
            return [], BulkUpdateStats()
        
        # STEP 1: Apply vectorized Unicode normalization
        logger.debug(f"Step 1: Applying vectorized Unicode normalization")
        df_normalized = self._normalize_unicode_vectorized(df)
        
        # STEP 2: Skip multi-value analysis (disabled)
        logger.debug(f"Step 2: Multi-value analysis skipped (disabled)")
        
        # STEP 3: Add row identifiers (start from 0 consistently)
        logger.debug(f"Step 3: Adding row identifiers")
        df_with_ids = df_normalized.with_row_index(name='row_id', offset=0)
        

        
        # STEP 4: Efficient conversion to updates (vectorized)
        logger.debug(f"Step 4: Converting to ResourceUpdate objects")
        updates = []
        stats = BulkUpdateStats()
        
        # Track statistics properly
        stats.rows_processed = df.height
        
        row_iterator = df_with_ids.iter_rows(named=True)
        
        for row_data in row_iterator:
            row_id_val = row_data.get('row_id', 'unknown')
            safe_row_id = slugify_uri_part(str(row_id_val))
            
            for column_name, value in row_data.items():
                # Skip internal columns and None column names
                if column_name == 'row_id' or column_name is None:
                    continue
                

                    
                if value is not None and str(value).strip():
                    current_value_str = str(value).strip()
                    
                    # Vectorized truncation logic
                    try:
                        original_byte_size = len(current_value_str.encode('utf-8'))
                        if original_byte_size > MAX_INDEXED_VALUE_SIZE:
                            temp_val = current_value_str
                            while len(temp_val.encode('utf-8')) > MAX_INDEXED_VALUE_SIZE:
                                temp_val = temp_val[:-1]
                            current_value_str = temp_val + "..."
                            stats.truncated_values += 1
                            logger.warning(
                                f"SBU Polars: Value truncated for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'. "
                                f"Original byte size: {original_byte_size}, new byte size: {len(current_value_str.encode('utf-8'))}"
                            )
                    except UnicodeEncodeError:
                        logger.warning(f"SBU Polars: Could not encode value to check size for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'.")
                    
                    # Create resource update with 1-based row ID in URI
                    safe_column_name = slugify_uri_part(column_name)
                    display_row_id = int(row_id_val) + 1 if str(row_id_val).isdigit() else row_id_val
                    safe_display_row_id = slugify_uri_part(str(display_row_id))
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, safe_display_row_id)
                    

                    
                    update = ResourceUpdate(
                        uri=cell_uri,
                        new_values=[current_value_str],
                        new_name=column_name,
                        new_datatype="http://www.w3.org/2001/XMLSchema#string",
                        action=UpdateStrategy.SKIP_EXISTING  # Will be determined later
                    )
                    # Note: Don't count total_values_created here - count during actual execution
                    
                    updates.append(update)
        
        logger.info(f"SBU Polars: Generated {len(updates)} updates for dataset '{dataset_name}' without multi-value splitting")
        return updates, stats

    def get_existing_resources_bulk(self, uris: List[str]) -> Dict[str, Resource]:
        """
        Efficiently fetch existing resources for a list of URIs.
        Same as original implementation.
        """
        existing = Resource.objects.filter(uri__in=uris).select_related()
        return {resource.uri: resource for resource in existing}

    def determine_update_actions_polars(self, 
                                      df: pl.DataFrame, 
                                      dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        Determine update actions using Polars DataFrame operations.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        # Prepare the basic update data
        updates, action_stats = self.prepare_update_data_vectorized(df, dataset_name)
        
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

    def execute_bulk_update(self, 
                          updates: List[ResourceUpdate],
                          dataset_name: str, 
                          action_phase_stats: BulkUpdateStats,
                          batch_size: int = 1000) -> BulkUpdateStats:
        """
        Execute bulk updates with multi-value support and optimized batch processing.
        
        Args:
            updates: List of ResourceUpdate objects to execute
            dataset_name: Name of the dataset being processed
            action_phase_stats: Statistics from the action determination phase
            batch_size: Size of batches for processing
            
        Returns:
            BulkUpdateStats with execution metrics
        """
        logger.info(f"Executing {len(updates)} updates for dataset '{dataset_name}' with batch size {batch_size}")
        
        if not updates:
            return BulkUpdateStats()
        
        stats = BulkUpdateStats()
        # Note: Don't count cells_processed here since it's already counted in prepare_update_data_vectorized
        
        # Extract row_ids for row linking if enabled
        row_ids = set()
        if self.link_row_cells:
            for update in updates:
                row_id = self._extract_row_id_from_uri(update.uri)
                if row_id:
                    row_ids.add(row_id)
        
        # Process updates in batches
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            active_updates = [u for u in batch if u.action in {UpdateStrategy.UPDATE_VALUES}]
            
                    # Process the batch
        self._execute_batch_with_multi_value_support(active_updates, dataset_name, stats)
        
        # NOTE: Row resources are now created in STEP 2 of _execute_batch_with_multi_value_support
        # with proper URI patterns, so no additional row linking needed here
        
        logger.info(f"Bulk update execution completed: {stats}")
        return stats
    
    def _execute_batch_with_multi_value_support(self, 
                                              batch: List[ResourceUpdate], 
                                              dataset_name: str, 
                                              stats: BulkUpdateStats):
        """
        Execute a batch of updates with proper bulk operations.
        Creates dataset and row resources with proper hasPart relationships.
        """
        from arkumu.metadata.models import Resource, Triple
        from arkumu.metadata.models.resource import ResourceType
        
        if not batch:
            return
        
        # Create dataset resource first
        dataset_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name)
        dataset_resource, ds_created = Resource.objects.get_or_create(
            uri=dataset_uri,
            defaults={"resource_type": ResourceType.IRI, "name": dataset_name, "source": self.institution}
        )
        if ds_created:
            stats.resources_created += 1
        
        # Filter out skipped updates
        active_updates = [update for update in batch if update.action != UpdateStrategy.SKIP_EXISTING]
        if not active_updates:
            return
        
        # Track rows processed (count unique row IDs in this batch)
        row_ids_in_batch = set()
        for update in active_updates:
            row_id = self._extract_row_id_from_uri(update.uri)
            if row_id:
                row_ids_in_batch.add(row_id)
        stats.rows_processed += len(row_ids_in_batch)
        
        # Track cells processed (active updates count)
        stats.cells_processed += len(active_updates)
        
        # Prepare cell resources for bulk creation
        cell_resources_to_create = []
        uri_to_update_map = {}
        
        for update in active_updates:
            cell_resources_to_create.append(Resource(
                uri=update.uri,
                resource_type=ResourceType.IRI,
                source=self.institution,
                name=update.new_name or "Cell"
            ))
            uri_to_update_map[update.uri] = update
        
        # Bulk create cell resources
        if cell_resources_to_create:
            # DEBUG: Count resources before and after bulk_create
            before_count = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/").count()
            logger.info(f"DEBUG: Resources before bulk_create: {before_count}")
            
            Resource.objects.bulk_create(
                cell_resources_to_create,
                ignore_conflicts=True,
                batch_size=500
            )
            
            after_count = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/").count()
            logger.info(f"DEBUG: Resources after bulk_create: {after_count} (created {after_count - before_count})")
            
            stats.resources_created += len({u.uri for u in active_updates})
        
        # Group updates by row for row creation (use 1-based IDs from URIs)
        row_grouping = {}
        for update in active_updates:
            row_id = self._extract_row_id_from_uri(update.uri)  # This returns 1-based ID from URI
            if row_id:
                if row_id not in row_grouping:
                    row_grouping[row_id] = []
                row_grouping[row_id].append(update)
        
        # =================== TOPOLOGY IMPLEMENTATION ===================
        # Creates efficient semantic structure with URI-based row tracking:
        # 
        # ALWAYS: Dataset → hasPart → Column → hasPart → Cell[row_in_URI] → rdf:value → Literal
        # 
        # TOPOLOGY OPTIONS:
        # "row": Add Row resources (Dataset → Row → Cell dual hierarchy)  
        # "first_column": Star pattern (FirstColumnCell → sameRow → OtherCells)
        # "mesh": Full connectivity (Cell → sameRow → Cell for all pairs)
        # DEFAULT: Column-only with row info embedded in cell URIs
        # ================================================================
        structural_triples = []
        value_triples = []
        
        # STEP 1: Create Column Resources (Always - for semantic structure)
        # Extract unique columns from this batch
        unique_columns = set()
        for update in active_updates:
            column_name = self._extract_column_name_from_uri(update.uri)
            if column_name:
                unique_columns.add(column_name)
        
        column_resources = {}
        logger.info(f"Creating {len(unique_columns)} column resources for dataset '{dataset_name}'")
        
        for column_name in unique_columns:
            safe_column_name = slugify_uri_part(column_name)
            column_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "columns", safe_column_name)
            
            column_resource, col_created = Resource.objects.get_or_create(
                uri=column_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": column_name,
                    "source": self.institution
                }
            )
            
            if col_created:
                stats.resources_created += 1
                
            column_resources[column_name] = column_resource
            
            # Dataset → hasPart → Column
            structural_triples.append(
                Triple(subject=dataset_resource, predicate=self.has_part_prop, object=column_resource)
            )
        
        # STEP 2: Topology-specific row resource creation (ONLY if needed)
        create_row_resources = (self.link_topology == "row" and self.link_row_cells)
        
        if create_row_resources:
            # ROW TOPOLOGY: Create row resources for dual hierarchy
            logger.info(f"Using 'row' topology - creating row resources")
            
            for row_id, row_updates in row_grouping.items():
                # row_id is already 1-based from cell URIs, use directly
                safe_row_id = slugify_uri_part(str(row_id))
                row_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "rows", safe_row_id)

                
                row_resource, row_created = Resource.objects.get_or_create(
                    uri=row_uri,
                    defaults={"resource_type": ResourceType.IRI, "name": f"Row {row_id}", "source": self.institution}
                )
                if row_created:
                    stats.resources_created += 1
                
                # Dataset → hasPart → Row
                structural_triples.append(Triple(subject=dataset_resource, predicate=self.has_part_prop, object=row_resource))
        
        elif self.link_topology == "first_column":
            # FIRST_COLUMN TOPOLOGY: Column hierarchy + star pattern
            logger.info(f"Using 'first_column' topology - column hierarchy with star pattern")
            
        elif self.link_topology == "mesh":
            # MESH TOPOLOGY: Column hierarchy + full mesh
            logger.info(f"Using 'mesh' topology - column hierarchy with full mesh")
            
        else:
            # DEFAULT: Column-only hierarchy with URI-based row tracking (MINIMAL)
            logger.info(f"Using column-only hierarchy with URI-based row tracking (minimal triples)")
        
        # STEP 3: Process each cell and create relationships based on topology
        logger.info(f"DEBUG: Starting STEP 3 - processing {len(uri_to_update_map)} cells")
        for cell_uri, update in uri_to_update_map.items():
            try:
                cell_resource = Resource.objects.get(uri=cell_uri)
                logger.info(f"DEBUG: Found cell resource for URI: {cell_uri}")
                
                # ALWAYS: Link Column → hasPart → Cell (core semantic structure)
                column_name = self._extract_column_name_from_uri(cell_uri)
                if column_name and column_name in column_resources:
                    column_resource = column_resources[column_name]
                    structural_triples.append(
                        Triple(subject=column_resource, predicate=self.has_part_prop, object=cell_resource)
                    )
                
                # TOPOLOGY-SPECIFIC: Additional cell relationships (ONLY if row resources exist)
                if create_row_resources:
                    # Row → hasPart → Cell (dual hierarchy - only when using row topology)
                    row_id = self._extract_row_id_from_uri(cell_uri)
                    if row_id:
                        # Row URI should use the same row ID that's in the cell URI (1-based)
                        safe_row_id = slugify_uri_part(str(row_id))
                        row_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "rows", safe_row_id)
                        try:
                            row_resource = Resource.objects.get(uri=row_uri)
                            structural_triples.append(
                                Triple(subject=row_resource, predicate=self.has_part_prop, object=cell_resource)
                            )
                        except Resource.DoesNotExist:
                            logger.warning(f"Row resource not found: {row_uri}")
                
                # Create value resources and triples
                for value in update.new_values:
                    if value and value.strip():
                        value_resource, val_created = Resource.objects.get_or_create(
                            value=value,
                            resource_type=ResourceType.LITERAL,
                            source=self.institution,
                            defaults={"name": update.new_name or value, "datatype": update.new_datatype}
                        )
                        
                        if val_created:
                            stats.resources_created += 1
                        
                        # Create rdf:value triple
                        value_triples.append(Triple(subject=cell_resource, predicate=self.rdf_value_prop, object=value_resource))
                        stats.total_values_created += 1
                        
            except Resource.DoesNotExist:
                logger.error(f"DEBUG: Cell resource {cell_uri} not found after bulk create. Skipping.")
                current_count = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/").count()
                logger.error(f"DEBUG: Current resource count when cell not found: {current_count}")
                stats.errors += 1
            except Exception as e:
                logger.error(f"DEBUG: Error processing cell {cell_uri}: {e}", exc_info=True)
                current_count = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/").count()
                logger.error(f"DEBUG: Current resource count when error occurred: {current_count}")
                stats.errors += 1
        
        # STEP 4: Post-processing topology patterns (first_column, mesh)
        topology_triples = []
        
        if self.link_topology == "first_column":
            # Create same-row property if needed
            same_row_prop, _ = Resource.objects.get_or_create(
                uri=mint_uri(self.base_uri, self.institution, "properties", "sameRow"),
                defaults={"resource_type": ResourceType.PROPERTY, "name": "sameRow", "source": self.institution}
            )
            
            # Group cells by row and link to first column cell (star pattern)
            for row_id, row_updates in row_grouping.items():
                if len(row_updates) > 1:
                    # Find first column cell (alphabetically first column)
                    first_column_update = min(row_updates, key=lambda u: self._extract_column_name_from_uri(u.uri) or "")
                    first_cell_uri = first_column_update.uri
                    
                    try:
                        first_cell_resource = Resource.objects.get(uri=first_cell_uri)
                        
                        # Link all other cells to first column cell
                        for update in row_updates:
                            if update.uri != first_cell_uri:
                                try:
                                    other_cell_resource = Resource.objects.get(uri=update.uri)
                                    topology_triples.append(
                                        Triple(subject=first_cell_resource, predicate=same_row_prop, object=other_cell_resource)
                                    )
                                except Resource.DoesNotExist:
                                    logger.warning(f"Cell resource not found for first_column topology: {update.uri}")
                    except Resource.DoesNotExist:
                        logger.warning(f"First column cell not found: {first_cell_uri}")
        
        elif self.link_topology == "mesh":
            # Create same-row property if needed
            same_row_prop, _ = Resource.objects.get_or_create(
                uri=mint_uri(self.base_uri, self.institution, "properties", "sameRow"),
                defaults={"resource_type": ResourceType.PROPERTY, "name": "sameRow", "source": self.institution}
            )
            
            # Group cells by row and create full mesh (all-to-all connections)
            for row_id, row_updates in row_grouping.items():
                if len(row_updates) > 1:
                    # Get all cell resources for this row
                    row_cell_resources = []
                    for update in row_updates:
                        try:
                            cell_resource = Resource.objects.get(uri=update.uri)
                            row_cell_resources.append(cell_resource)
                        except Resource.DoesNotExist:
                            logger.warning(f"Cell resource not found for mesh topology: {update.uri}")
                    
                    # Create mesh connections (i to j, j to i for all pairs)
                    for i in range(len(row_cell_resources)):
                        for j in range(i + 1, len(row_cell_resources)):
                            # Bidirectional connections for full mesh
                            topology_triples.append(
                                Triple(subject=row_cell_resources[i], predicate=same_row_prop, object=row_cell_resources[j])
                            )
                            topology_triples.append(
                                Triple(subject=row_cell_resources[j], predicate=same_row_prop, object=row_cell_resources[i])
                            )
        
        # Bulk create all triples (structural + value + topology)
        all_triples = structural_triples + value_triples + topology_triples
        if all_triples:
            Triple.objects.bulk_create(all_triples, ignore_conflicts=True)
            stats.triples_created += len(all_triples)
            logger.info(f"Created {len(structural_triples)} structural, {len(value_triples)} value, {len(topology_triples)} topology triples")
        
        logger.info(f"Batch processed: {len(batch)} updates, {len({u.uri for u in active_updates})} resources, topology: {self.link_topology}")

    def _extract_row_id_from_uri(self, cell_uri: str) -> Optional[str]:
        """Helper to extract row_id from a standard cell URI."""
        # Standard URI: {base_uri}/{institution}/datasets/{dataset_name}/{column_name}/{row_id}
        try:
            return cell_uri.split('/')[-1]
        except IndexError:
            logger.warning(f"SBU Polars: Could not parse row_id from cell_uri: {cell_uri}")
            return None

    def _extract_column_name_from_uri(self, cell_uri: str) -> Optional[str]:
        """Helper to extract column_name from a standard cell URI."""
        # Standard URI: {base_uri}/{institution}/datasets/{dataset_name}/{column_name}/{row_id}
        try:
            parts = cell_uri.split('/')
            # Find the datasets part and get the column name after it
            if 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 2 < len(parts):
                    return parts[datasets_index + 2]  # datasets/{name}/{column_name}/{row_id}
            return None
        except (IndexError, ValueError):
            logger.warning(f"SBU Polars: Could not parse column_name from cell_uri: {cell_uri}")
            return None

    def import_csv_with_smart_updates(self,
                                    csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                                    dataset_name: str,
                                    strategy: Optional[UpdateStrategy] = None) -> BulkUpdateStats:
        """
        Import CSV data with intelligent update handling using Polars optimization.
        
        Args:
            csv_data: List of row dictionaries from CSV or Polars DataFrame
            dataset_name: Name of the dataset
            strategy: Override the default update strategy
            
        Returns:
            BulkUpdateStats with operation results
        """
        if strategy:
            original_strategy = self.default_strategy
            self.default_strategy = strategy
        
        overall_stats = BulkUpdateStats()
        try:
            logger.info(f"Starting Polars-optimized smart bulk import for dataset: {dataset_name} with linking: {self.link_row_cells}, topology: {self.link_topology}")
            
            # Convert to DataFrame if needed
            df = self._ensure_dataframe(csv_data)
            
            if df.height == 0:
                logger.warning(f"Empty dataset provided for {dataset_name}")
                return overall_stats
            
            # Use Polars-optimized processing
            updates, action_stats = self.determine_update_actions_polars(df, dataset_name)
            overall_stats.merge(action_stats)
            logger.info(f"Determined {len(updates)} update actions. Truncated values: {action_stats.truncated_values}")
            
            execution_stats = self.execute_bulk_update(updates, dataset_name, action_stats, batch_size=1000)
            overall_stats.merge(execution_stats)
            
            logger.info(f"Polars-optimized smart bulk import completed: {overall_stats}")
            return overall_stats
            
        finally:
            if strategy:
                self.default_strategy = original_strategy

    # Compatibility methods that delegate to Polars versions
    def analyze_column_for_multi_values(self, column_values: List[str]) -> Dict[str, Any]:
        """Compatibility method that converts to DataFrame and uses Polars analysis."""
        if not column_values:
            return {"is_multi_value": False, "separator": None, "stats": {}}
        
        # Create a temporary DataFrame with just this column
        df = pl.DataFrame({"temp_column": column_values})
        return self.analyze_column_for_multi_values_polars(df, "temp_column")

    def analyze_dataset_multi_values(self, csv_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Compatibility method that converts to DataFrame and uses Polars analysis."""
        df = self._ensure_dataframe(csv_data)
        return self.analyze_dataset_multi_values_polars(df)

    def split_cell_values(self, value: str, separator: str = ",") -> List[str]:
        """Compatibility method that uses the same splitting logic."""
        return self.split_cell_values_polars(value, separator)

    def _process_multi_values_vectorized(self, df: pl.DataFrame, multi_value_analysis: Dict[str, Dict[str, Any]]) -> pl.DataFrame:
        """
        Simplified: No multi-value processing needed since we disabled splitting.
        Just return the original dataframe.
        """
        return df

    def prepare_update_data_polars(self, df: pl.DataFrame, dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        Legacy method for backward compatibility. 
        Delegates to the optimized vectorized version.
        """
        return self.prepare_update_data_vectorized(df, dataset_name)

    def analyze_dataset_changes(self, 
                              dataset_name: str,
                              csv_data: Union[List[Dict[str, Any]], pl.DataFrame]) -> Dict[str, Any]:
        """
        Analyze what would change if we imported this CSV data.
        This is a dry-run analysis without making any changes.
        Polars-optimized version.
        
        Args:
            dataset_name: Name of the dataset
            csv_data: List of row dictionaries from CSV or Polars DataFrame
            
        Returns:
            Analysis report with statistics and recommendations
        """
        # Ensure we have a DataFrame
        df = self._ensure_dataframe(csv_data)
        
        analysis = {
            "total_rows": df.height,
            "new_resources": 0,
            "existing_resources": 0,
            "potential_updates": 0,
            "conflicts": [],
            "recommendations": []
        }
        
        # Get all existing resources for this dataset
        dataset_uri_pattern = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "", "")
        dataset_uri_prefix = dataset_uri_pattern.rsplit('/', 2)[0]  # Remove the last two empty parts
        
        existing_resources = Resource.objects.filter(
            uri__startswith=dataset_uri_prefix
        ).values('uri', 'value', 'name', 'updated_at')
        
        existing_uri_map = {res['uri']: res for res in existing_resources}
        
        # Add row indices for processing
        df_with_ids = df.with_row_index(name='row_id')
        
        # Analyze each row using Polars iteration
        for row_data in df_with_ids.iter_rows(named=True):
            row_num = row_data.get('row_id', 0)
            row_id_val = row_data.get('id', row_data.get('ID', str(row_num)))
            
            for column_name, value in row_data.items():
                # Skip internal columns and None column names
                if column_name == 'row_id' or column_name is None:
                    continue
                    
                if value and str(value).strip():
                    # Ensure row_id is slugified for URI consistency
                    safe_row_id = slugify_uri_part(str(row_id_val))
                    safe_column_name = slugify_uri_part(column_name)
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, safe_row_id)
                    
                    if cell_uri in existing_uri_map:
                        existing = existing_uri_map[cell_uri]
                        analysis["existing_resources"] += 1
                        
                        # Check if value would change
                        if existing['value'] != str(value).strip():
                            analysis["potential_updates"] += 1
                            
                            conflict_info = {
                                "uri": cell_uri,
                                "column": column_name,
                                "row_id": row_id_val,
                                "existing_value": existing['value'],
                                "new_value": str(value).strip(),
                                "last_updated": existing.get('updated_at')
                            }
                            
                            # Add timestamp comparison if timestamp column is configured
                            if self.timestamp_column and self.timestamp_column in row_data:
                                new_timestamp_str = str(row_data.get(self.timestamp_column, '')).strip()
                                new_timestamp = self._parse_timestamp(new_timestamp_str)
                                
                                if new_timestamp:
                                    # Try to get existing timestamp for this row
                                    existing_timestamp = self._get_existing_timestamp_for_analysis(
                                        dataset_name, safe_row_id, existing.get('updated_at')
                                    )
                                    
                                    conflict_info.update({
                                        "new_timestamp": new_timestamp_str,
                                        "new_timestamp_parsed": new_timestamp.isoformat() if new_timestamp else None,
                                        "existing_timestamp": existing_timestamp.isoformat() if existing_timestamp else None,
                                        "timestamp_comparison": (
                                            "newer" if existing_timestamp and new_timestamp > existing_timestamp else
                                            "older" if existing_timestamp and new_timestamp < existing_timestamp else
                                            "equal" if existing_timestamp and new_timestamp == existing_timestamp else
                                            "unknown"
                                        )
                                    })
                            
                            analysis["conflicts"].append(conflict_info)
                    else:
                        analysis["new_resources"] += 1
        
        # Generate recommendations
        if analysis["potential_updates"] > 0:
            analysis["recommendations"].append(
                f"Found {analysis['potential_updates']} potential updates. "
                f"Consider using UPDATE_VALUES strategy."
            )
        
        if analysis["existing_resources"] > analysis["new_resources"]:
            analysis["recommendations"].append(
                "Mostly existing data detected. Consider SKIP_EXISTING for faster processing."
            )
        
        return analysis

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parse a timestamp string into a datetime object.
        """
        if not timestamp_str or not timestamp_str.strip():
            return None
            
        timestamp_str = timestamp_str.strip()
        
        try:
            # Try common ISO formats first
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d",
                "%d.%m.%Y",
                "%d/%m/%Y",
                "%m/%d/%Y"
            ]:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    # Add timezone info if missing
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue
            
            # Fallback to dateutil parser
            return dateutil.parser.parse(timestamp_str, default=datetime.now(timezone.utc))
            
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None

    def _get_existing_timestamp_for_analysis(self, dataset_name: str, row_id: str, fallback_updated_at) -> Optional[datetime]:
        """
        Get existing timestamp for analysis purposes.
        """
        if not self.timestamp_column:
            return fallback_updated_at
            
        # Try to find the timestamp cell for this row
        safe_column_name = slugify_uri_part(self.timestamp_column)
        timestamp_cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, row_id)
        
        try:
            timestamp_resource = Resource.objects.get(uri=timestamp_cell_uri)
            if timestamp_resource.value:
                return self._parse_timestamp(timestamp_resource.value)
        except Resource.DoesNotExist:
            pass
            
        return fallback_updated_at 