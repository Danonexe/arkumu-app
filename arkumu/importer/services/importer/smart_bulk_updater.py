import logging
import hashlib
import csv
import io
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import dateutil.parser
from django.db import transaction, models
from django.db.models import Q, Count, Exists, OuterRef
from django.utils import timezone as django_timezone

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.mapping_executor import MappingExecutor, MappingExecutionStats
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
from arkumu.importer.services.importer.data_utils import normalize_string_nfc

logger = logging.getLogger(__name__)

# Maximum size for values to avoid btree index errors (PostgreSQL limit is ~2704 bytes)
# Using a significantly lower limit to account for index overhead (other columns + metadata).
MAX_INDEXED_VALUE_SIZE = 1000

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


class SmartBulkUpdater:
    """
    Intelligent bulk update service that leverages the URI-based data model
    for efficient duplicate detection and selective updates.
    """
    
    def __init__(self, 
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None,
                 institution: str = "DEFAULT",
                 base_uri: str = "http://arkumu.org/data",
                 link_row_cells: bool = True,
                 link_topology: str = "row",
                 multi_value_threshold: float = 0.2
                 ):
        """
        Initialize the smart bulk updater.
        
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
            logger.error(f"SBU __init__: Failed to pre-fetch standard RDF properties: {e}", exc_info=True)
            self.has_part_prop = None 
            self.rdf_value_prop = None
            self.dcterms_relation_prop = None

    def analyze_column_for_multi_values(self, column_values: List[str]) -> Dict[str, Any]:
        """
        Analyze a full column to detect multi-value patterns.
        
        Args:
            column_values: List of string values from a single column
            
        Returns:
            Dictionary with analysis results including is_multi_value and separator
        """
        if not column_values:
            return {"is_multi_value": False, "separator": None, "stats": {}}
        
        unquoted_comma_count = 0
        total_non_empty = 0
        sample_splits = []
        
        for value in column_values:
            if not value or not str(value).strip():
                continue
                
            total_non_empty += 1
            value_str = str(value).strip()
            
            try:
                # Use csv.reader to properly handle quoted commas
                parsed = list(csv.reader([value_str], delimiter=','))[0]
                if len(parsed) > 1:  # Multiple values after CSV parsing
                    unquoted_comma_count += 1
                    # Keep sample for logging
                    if len(sample_splits) < 3:
                        sample_splits.append(f"{value_str} -> {parsed}")
            except Exception as e:
                logger.debug(f"CSV parsing failed for value '{value_str}': {e}")
                continue
        
        # Calculate percentage of cells with multiple comma-separated values
        multi_value_percentage = (unquoted_comma_count / total_non_empty) if total_non_empty > 0 else 0
        is_multi_value = multi_value_percentage > self.multi_value_threshold
        
        analysis_result = {
            "is_multi_value": is_multi_value,
            "separator": "," if is_multi_value else None,
            "stats": {
                "total_cells": len(column_values),
                "non_empty_cells": total_non_empty,
                "multi_value_cells": unquoted_comma_count,
                "percentage": round(multi_value_percentage * 100, 1),
                "sample_splits": sample_splits[:3]  # Keep max 3 examples
            }
        }
        
        if is_multi_value:
            logger.info(f"Multi-value column detected: {multi_value_percentage:.1%} of cells contain comma-separated values. Samples: {sample_splits}")
        
        return analysis_result

    def analyze_dataset_multi_values(self, csv_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all columns in the dataset to detect multi-value patterns.
        
        Args:
            csv_data: List of row dictionaries from CSV
            
        Returns:
            Dictionary mapping column names to their multi-value analysis
        """
        if not csv_data:
            return {}
        
        # Group values by column
        column_data = {}
        for row in csv_data:
            for column_name, value in row.items():
                if column_name not in column_data:
                    column_data[column_name] = []
                column_data[column_name].append(value)
        
        # Analyze each column
        multi_value_analysis = {}
        for column_name, values in column_data.items():
            analysis = self.analyze_column_for_multi_values(values)
            multi_value_analysis[column_name] = analysis
            
            if analysis["is_multi_value"]:
                stats = analysis["stats"]
                logger.info(f"Column '{column_name}': Multi-value detected ({stats['percentage']}% of {stats['non_empty_cells']} cells)")
        
        return multi_value_analysis

    def split_cell_values(self, value: str, separator: str = ",") -> List[str]:
        """
        Split a cell value respecting CSV quoting rules.
        
        Args:
            value: The cell value to split
            separator: The separator to use (default: comma)
            
        Returns:
            List of individual values
        """
        if not value or not str(value).strip():
            return []
        
        try:
            # Use csv.reader to properly handle quoted values
            parsed = list(csv.reader([str(value).strip()], delimiter=separator))[0]
            # Clean up each value (strip whitespace)
            return [v.strip() for v in parsed if v.strip()]
        except Exception as e:
            logger.warning(f"Failed to parse multi-value cell '{value}' with separator '{separator}': {e}")
            # Fallback to simple split
            return [v.strip() for v in str(value).split(separator) if v.strip()]

    def _extract_row_id_from_uri(self, cell_uri: str) -> Optional[str]:
        """Helper to extract row_id from a standard cell URI."""
        # Standard URI: {base_uri}/{institution}/datasets/{dataset_name}/{column_name}/{row_id}
        try:
            return cell_uri.split('/')[-1]
        except IndexError:
            logger.warning(f"Could not parse row_id from cell_uri: {cell_uri}")
            return None

    def analyze_dataset_changes(self, 
                              dataset_name: str,
                              csv_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze what would change if we imported this CSV data.
        This is a dry-run analysis without making any changes.
        
        Args:
            dataset_name: Name of the dataset
            csv_data: List of row dictionaries from CSV
            
        Returns:
            Analysis report with statistics and recommendations
        """
        analysis = {
            "total_rows": len(csv_data),
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
        
        # Analyze each row
        for row_num, row in enumerate(csv_data):
            row_id_val = row.get('id', row.get('ID', str(row_num)))
            
            for column_name, value in row.items():
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
                            if self.timestamp_column and self.timestamp_column in row:
                                new_timestamp_str = str(row.get(self.timestamp_column, '')).strip()
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
    
    def get_existing_resources_bulk(self, uris: List[str]) -> Dict[str, Resource]:
        """
        Efficiently fetch existing resources for a list of URIs.
        
        Args:
            uris: List of URIs to check
            
        Returns:
            Dictionary mapping URI to Resource object
        """
        existing = Resource.objects.filter(uri__in=uris).select_related()
        return {resource.uri: resource for resource in existing}
    
    def determine_update_actions(self, 
                               csv_data: List[Dict[str, Any]], 
                               dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        updates = []
        all_uris = []
        action_stats = BulkUpdateStats()
        
        # First, analyze the dataset for multi-value columns
        multi_value_analysis = self.analyze_dataset_multi_values(csv_data)
        
        uri_to_data_map = {}
        for row_num, row in enumerate(csv_data):
            row_id_val = row.get('id', row.get('ID', str(row_num)))
            safe_row_id = slugify_uri_part(str(row_id_val))
            
            for column_name, value in row.items():
                if value and str(value).strip():
                    original_value_str = str(value).strip()
                    original_value_str = normalize_string_nfc(original_value_str)
                    current_value_str = original_value_str

                    # Truncation logic for oversized values
                    try:
                        original_byte_size = len(current_value_str.encode('utf-8'))
                        if original_byte_size > MAX_INDEXED_VALUE_SIZE:
                            temp_val = current_value_str
                            while len(temp_val.encode('utf-8')) > MAX_INDEXED_VALUE_SIZE:
                                temp_val = temp_val[:-1]
                            current_value_str = temp_val + "..."
                            action_stats.truncated_values += 1
                            logger.warning(
                                f"SBU: Value truncated for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'. "
                                f"Original byte size: {original_byte_size}, new byte size: {len(current_value_str.encode('utf-8'))}"
                            )
                    except UnicodeEncodeError:
                        logger.warning(f"SBU: Could not encode value to check size for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'. Using original.")
                        # Fallback to original if encoding fails, though this might still error later

                    safe_column_name = slugify_uri_part(column_name)
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, safe_row_id)
                    all_uris.append(cell_uri)
                    uri_to_data_map[cell_uri] = {
                        'value': current_value_str,
                        'column_name': column_name,
                        'row_id': safe_row_id,
                        'row_data': row,
                        'is_multi_value_column': multi_value_analysis.get(column_name, {}).get('is_multi_value', False),
                        'separator': multi_value_analysis.get(column_name, {}).get('separator', ',')
                    }
        
        existing_resources = self.get_existing_resources_bulk(all_uris)
        
        for uri, data in uri_to_data_map.items():
            update = ResourceUpdate(uri=uri)
            
            # Handle multi-value vs single-value fields
            if data['is_multi_value_column']:
                update.new_values = self.split_cell_values(data['value'], data['separator'])
                update.is_multi_value = True
                action_stats.multi_value_cells_detected += 1
                action_stats.total_values_created += len(update.new_values)
            else:
                update.new_values = [data['value']]  # Single value as list for consistency
                update.is_multi_value = False
                action_stats.total_values_created += 1
            
            update.new_name = data['column_name']
            update.new_datatype = "http://www.w3.org/2001/XMLSchema#string"
            
            if uri in existing_resources:
                existing = existing_resources[uri]
                update.existing_resource = existing
                
                # Determine update strategy
                if self.default_strategy == UpdateStrategy.SKIP_EXISTING:
                    update.action = UpdateStrategy.SKIP_EXISTING
                elif self.default_strategy == UpdateStrategy.UPDATE_VALUES:
                    # For multi-value fields, we need to compare differently
                    if update.is_multi_value:
                        # For now, always update multi-value fields (complex comparison)
                        update.action = UpdateStrategy.UPDATE_VALUES
                    else:
                        if existing.value != data['value']:
                            update.action = UpdateStrategy.UPDATE_VALUES
                        else:
                            update.action = UpdateStrategy.SKIP_EXISTING
                elif self.default_strategy == UpdateStrategy.TIMESTAMP_BASED:
                    update.action = self._determine_timestamp_action(existing, data)
                else:
                    update.action = self.default_strategy
            else:
                # New resource
                update.action = UpdateStrategy.UPDATE_VALUES  # Create new
            
            updates.append(update)
        
        return updates, action_stats
    
    def execute_bulk_update(self, 
                          updates: List[ResourceUpdate],
                          dataset_name: str, 
                          action_phase_stats: BulkUpdateStats,
                          batch_size: int = 1000) -> BulkUpdateStats:
        stats = BulkUpdateStats()
        stats.merge(action_phase_stats)
        
        creates = [u for u in updates if u.existing_resource is None]
        skips = [u for u in updates if u.action == UpdateStrategy.SKIP_EXISTING]
        value_updates = [u for u in updates if u.action == UpdateStrategy.UPDATE_VALUES and u.existing_resource is not None]
        
        logger.info(f"Executing bulk update: {len(creates)} creates, {len(value_updates)} updates, {len(skips)} skips for dataset {dataset_name}")
        
        # Process creates in batches
        if creates:
            stats.merge(self._execute_creates(creates, batch_size, dataset_name))
        
        # Process updates in batches
        if value_updates:
            stats.merge(self._execute_updates(value_updates, batch_size, dataset_name))
        
        # Count skips
        stats.resources_skipped = len(skips)
        
        return stats
    
    def _execute_creates(self, creates: List[ResourceUpdate], batch_size: int, dataset_name: str) -> BulkUpdateStats:
        stats = BulkUpdateStats()
        
        if not all([self.has_part_prop, self.rdf_value_prop, self.dcterms_relation_prop]):
            logger.error("SBU _execute_creates: Standard RDF properties not initialized. Cannot create triples.")
            # Count an error for each item that would have been processed in this call if properties were available
            stats.errors += len(creates) 
            return stats
        
        try:
            dataset_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name)
            dataset_resource, ds_created = Resource.objects.get_or_create(
                uri=dataset_uri,
                defaults={"resource_type": ResourceType.IRI, "name": dataset_name, "source": self.institution}
            )
            if ds_created: stats.resources_created += 1

            for i in range(0, len(creates), batch_size):
                batch_of_updates = creates[i:i + batch_size]
                
                try:
                    with transaction.atomic():
                        cell_iris_to_create_in_db_batch = []
                        uri_to_original_update_map: Dict[str, ResourceUpdate] = {}

                        for update_item in batch_of_updates:
                            # Stage only Cell IRIs for bulk creation
                            cell_iris_to_create_in_db_batch.append(Resource(
                                uri=update_item.uri,
                                resource_type=ResourceType.IRI,
                                source=self.institution,
                                name=update_item.new_name
                            ))
                            uri_to_original_update_map[update_item.uri] = update_item
                        
                        # Bulk create only Cell IRIs
                        if cell_iris_to_create_in_db_batch:
                            Resource.objects.bulk_create(
                                cell_iris_to_create_in_db_batch, 
                                ignore_conflicts=True,
                                batch_size=500 
                            )
                        
                        # Increment resources_created for the cell IRIs just processed by bulk_create
                        # Note: ignore_conflicts=True means we don't get a precise count of *actually* created.
                        # This count assumes all in batch_of_updates were new URIs if they reached here.
                        stats.resources_created += len({u.uri for u in batch_of_updates})

                        stats.cells_processed += len(batch_of_updates)

                        structural_triples_to_create = []
                        row_grouping_for_linking: Dict[str, List[Resource]] = {}

                        for cell_uri, original_update_item in uri_to_original_update_map.items():
                            try:
                                cell_db_resource = Resource.objects.get(uri=cell_uri)
                                
                                # Get or create literal individually to ensure uniqueness and reuse
                                value_db_resource, literal_created = Resource.objects.get_or_create(
                                    resource_type=ResourceType.LITERAL,
                                    source=self.institution,
                                    name=original_update_item.new_name,
                                    value=original_update_item.new_values[0],
                                    datatype=original_update_item.new_datatype,
                                    # language=original_update_item.new_language, # Add if language is used
                                    defaults={'source': self.institution} 
                                )
                                if literal_created:
                                    stats.resources_created += 1 # Count newly created literals
                                
                                structural_triples_to_create.append(Triple(subject=dataset_resource, predicate=self.has_part_prop, object=cell_db_resource))
                                structural_triples_to_create.append(Triple(subject=cell_db_resource, predicate=self.rdf_value_prop, object=value_db_resource))

                                if self.link_row_cells:
                                    row_id = self._extract_row_id_from_uri(cell_uri)
                                    if row_id:
                                        if row_id not in row_grouping_for_linking:
                                            row_grouping_for_linking[row_id] = []
                                        row_grouping_for_linking[row_id].append(cell_db_resource)
                                    else:
                                        logger.warning(f"SBU _execute_creates: Could not extract row_id from {cell_uri} for row linking.")

                            except Resource.DoesNotExist:
                                logger.error(f"SBU _execute_creates: Cell resource {cell_uri} not found after bulk create. Skipping triples.")
                                stats.errors += 1 
                            except Exception as e_triple:
                                logger.error(f"SBU _execute_creates: Error preparing structural triples for cell {cell_uri}: {e_triple}", exc_info=True)
                                stats.errors += 1
                        
                        all_triples_for_batch = list(structural_triples_to_create)

                        if self.link_row_cells and row_grouping_for_linking:
                            row_linking_triples_to_create = []
                            for row_id_key, cell_db_resources_in_row in row_grouping_for_linking.items():
                                if not cell_db_resources_in_row: 
                                    continue

                                if self.link_topology == "row":
                                    try:
                                        row_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "rows", row_id_key)
                                        row_resource, row_created = Resource.objects.get_or_create(
                                            uri=row_uri,
                                            defaults={
                                                "resource_type": ResourceType.IRI, 
                                                "name": f"Row {row_id_key}", 
                                                "source": self.institution
                                            }
                                        )
                                        if row_created: 
                                            stats.resources_created += 1
                                        # No rdf:type for Row resource as we are not using a custom ark:Row class.
                                        for cell_res in cell_db_resources_in_row:
                                            row_linking_triples_to_create.append(Triple(subject=row_resource, predicate=self.has_part_prop, object=cell_res))
                                            stats.row_links_created += 1
                                    except Exception as e_row_link:
                                        logger.error(f"SBU _execute_creates: Error creating 'row' topology links for row_id {row_id_key}: {e_row_link}", exc_info=True)
                                        stats.errors +=1 
                                
                                elif self.link_topology == "first_column" and len(cell_db_resources_in_row) > 1:
                                    anchor_cell = cell_db_resources_in_row[0]
                                    for idx in range(1, len(cell_db_resources_in_row)):
                                        row_linking_triples_to_create.append(Triple(subject=anchor_cell, predicate=self.dcterms_relation_prop, object=cell_db_resources_in_row[idx]))
                                        stats.row_links_created += 1
                                
                                elif self.link_topology == "mesh" and len(cell_db_resources_in_row) > 1:
                                    for i_idx in range(len(cell_db_resources_in_row)):
                                        for j_idx in range(i_idx + 1, len(cell_db_resources_in_row)):
                                            row_linking_triples_to_create.append(Triple(subject=cell_db_resources_in_row[i_idx], predicate=self.dcterms_relation_prop, object=cell_db_resources_in_row[j_idx]))
                                            stats.row_links_created += 1
                            all_triples_for_batch.extend(row_linking_triples_to_create)
                        
                        if all_triples_for_batch:
                            actual_triples_created_objs = Triple.objects.bulk_create(
                                all_triples_for_batch, 
                                ignore_conflicts=True, 
                                batch_size=1000 
                            )
                            stats.triples_created += len(actual_triples_created_objs)
                            
                except Exception as e_batch_processing: # Catch errors specific to this batch processing
                    logger.error(f"SBU _execute_creates: Error processing batch (starts with {batch_of_updates[0].uri if batch_of_updates else 'N/A'}) for dataset '{dataset_name}': {e_batch_processing}", exc_info=True)
                    stats.errors += len(batch_of_updates) # Count errors for all items in this failed batch
        
        except Exception as e_outer: # Catch errors like dataset creation failure or issues outside batch loop
            logger.error(f"SBU _execute_creates: Major error processing creates for dataset '{dataset_name}': {e_outer}", exc_info=True)
            # Count an error for each item that would have been processed if this major step hadn't failed.
            # This might overestimate if some batches already processed, but better than undercounting.
            stats.errors += len(creates) 

        return stats
    
    def _execute_updates(self, updates: List[ResourceUpdate], batch_size: int, dataset_name: str) -> BulkUpdateStats:
        """Execute resource updates in batches."""
        stats = BulkUpdateStats()
        
        # Ensure common RDF resources are loaded for updates if needed (e.g. self.rdf_value_prop)
        if not self.rdf_value_prop:
            logger.error("SBU _execute_updates: rdf:value property not initialized. Cannot correctly identify literals to update.")
            stats.errors += sum(1 for i in range(0, len(updates), batch_size) for _ in updates[i:i + batch_size])
            return stats

        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            
            try:
                with transaction.atomic():
                    for update in batch:
                        if update.existing_resource and update.existing_resource.value != update.new_values[0]:
                            try:
                                cell_resource_uri = update.existing_resource.uri
                                value_triple = Triple.objects.select_related('object').filter(
                                    subject__uri=cell_resource_uri,
                                    predicate=self.rdf_value_prop,
                                    object__resource_type=ResourceType.LITERAL
                                ).first()

                                if value_triple and value_triple.object:
                                    literal_to_update = value_triple.object
                                    if literal_to_update.value != update.new_values[0]:
                                        literal_to_update.value = update.new_values[0]
                                        literal_to_update.save()
                                        stats.resources_updated += 1
                                        stats.triples_updated +=1
                                else:
                                    logger.warning(f"SBU _execute_updates: Could not find value triple/literal for cell {cell_resource_uri} to update.")
                                    stats.errors +=1

                            except Exception as e_update_lit:
                                logger.error(f"SBU _execute_updates: Error updating literal for cell {update.existing_resource.uri}: {e_update_lit}", exc_info=True)
                                stats.errors += 1
                                
                    stats.cells_processed += len(batch)
                    
            except Exception as e:
                logger.error(f"SBU _execute_updates: Error updating batch for dataset '{dataset_name}': {e}", exc_info=True)
                stats.errors += len(batch)
        
        return stats
    
    def _determine_timestamp_action(self, existing: Resource, new_data: Dict[str, Any]) -> UpdateStrategy:
        """Determine action based on timestamp comparison."""
        if not self.timestamp_column or self.timestamp_column not in new_data['row_data']:
            # Fallback to skip if timestamp column not in this specific row's data
            logger.debug(f"Timestamp column '{self.timestamp_column}' not found in new_data for {existing.uri}")
            return UpdateStrategy.SKIP_EXISTING
        
        try:
            # Get the new timestamp from CSV data
            new_timestamp_str = str(new_data['row_data'].get(self.timestamp_column, '')).strip()
            if not new_timestamp_str:
                logger.debug(f"No timestamp value found in column '{self.timestamp_column}' for {existing.uri}")
                return UpdateStrategy.SKIP_EXISTING
            
            # Parse the new timestamp
            new_timestamp = self._parse_timestamp(new_timestamp_str)
            if not new_timestamp:
                logger.warning(f"Could not parse timestamp '{new_timestamp_str}' for {existing.uri}")
                return UpdateStrategy.SKIP_EXISTING
            
            # Get the existing resource's timestamp
            existing_timestamp = self._get_existing_timestamp(existing, new_data)
            if not existing_timestamp:
                logger.debug(f"No existing timestamp found for {existing.uri}, allowing update")
                return UpdateStrategy.UPDATE_VALUES
            
            # Compare timestamps
            if new_timestamp > existing_timestamp:
                logger.debug(f"New timestamp {new_timestamp} is newer than existing {existing_timestamp} for {existing.uri}")
                return UpdateStrategy.UPDATE_VALUES
            elif new_timestamp == existing_timestamp:
                logger.debug(f"Timestamps are equal for {existing.uri}, skipping")
                return UpdateStrategy.SKIP_EXISTING
            else:
                logger.debug(f"New timestamp {new_timestamp} is older than existing {existing_timestamp} for {existing.uri}, skipping")
                return UpdateStrategy.SKIP_EXISTING
                
        except Exception as e:
            logger.error(f"Error comparing timestamps for {existing.uri}: {e}")
            return UpdateStrategy.SKIP_EXISTING
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parse a timestamp string into a datetime object.
        Supports various common formats.
        """
        if not timestamp_str or timestamp_str.lower() in ['', 'null', 'none', 'n/a']:
            return None
        
        try:
            # Try parsing with dateutil (handles many formats automatically)
            parsed = dateutil.parser.parse(timestamp_str)
            
            # Ensure timezone-aware datetime
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            
            return parsed
            
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse timestamp '{timestamp_str}': {e}")
            
            # Try some common fallback formats
            common_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d',
                '%d.%m.%Y %H:%M:%S',
                '%d.%m.%Y',
                '%d/%m/%Y %H:%M:%S',
                '%d/%m/%Y',
                '%Y%m%d_%H%M%S',
                '%Y%m%d',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%fZ'
            ]
            
            for fmt in common_formats:
                try:
                    parsed = datetime.strptime(timestamp_str, fmt)
                    # Ensure timezone-aware
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except ValueError:
                    continue
            
            return None
    
    def _get_existing_timestamp(self, existing: Resource, new_data: Dict[str, Any]) -> Optional[datetime]:
        """
        Get the timestamp for an existing resource.
        This looks for the timestamp in the same row's timestamp column.
        """
        try:
            # Get the row_id and dataset info to find the timestamp cell
            row_id = new_data['row_id']
            dataset_name = existing.uri.split('/datasets/')[1].split('/')[0]
            
            # Construct URI for the timestamp cell in the same row
            timestamp_cell_uri = mint_uri(
                self.base_uri, 
                self.institution, 
                "datasets", 
                dataset_name, 
                slugify_uri_part(str(self.timestamp_column)), 
                row_id
            )
            
            # Find the corresponding literal resource with the timestamp value
            try:
                timestamp_cell = Resource.objects.get(uri=timestamp_cell_uri)
                timestamp_triples = Triple.objects.filter(
                    subject=timestamp_cell,
                    predicate=self.rdf_value_prop
                ).select_related('object')
                
                if timestamp_triples.exists():
                    timestamp_value = timestamp_triples.first().object.value
                    return self._parse_timestamp(timestamp_value)
                    
            except Resource.DoesNotExist:
                pass
            
            # Fallback: use the resource's updated_at field if available
            if hasattr(existing, 'updated_at') and existing.updated_at:
                return existing.updated_at
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get existing timestamp for {existing.uri}: {e}")
            return None
    
    def _get_existing_timestamp_for_analysis(self, dataset_name: str, row_id: str, fallback_updated_at) -> Optional[datetime]:
        """
        Get existing timestamp for analysis purposes (simpler version).
        """
        if not self.timestamp_column:
            return fallback_updated_at
        
        try:
            # row_id here is expected to be the slugified version for URI construction
            timestamp_cell_uri = mint_uri(
                self.base_uri, 
                self.institution, 
                "datasets", 
                dataset_name, 
                slugify_uri_part(str(self.timestamp_column)), 
                row_id
            )
            
            try:
                timestamp_cell = Resource.objects.get(uri=timestamp_cell_uri)
                timestamp_triples = Triple.objects.filter(
                    subject=timestamp_cell,
                    predicate=self.rdf_value_prop
                ).select_related('object')
                
                if timestamp_triples.exists():
                    timestamp_value = timestamp_triples.first().object.value
                    parsed = self._parse_timestamp(timestamp_value)
                    if parsed:
                        return parsed
                        
            except Resource.DoesNotExist:
                pass
            
            # Fallback to updated_at
            if fallback_updated_at and fallback_updated_at.tzinfo is None:
                return fallback_updated_at.replace(tzinfo=timezone.utc)
            return fallback_updated_at
            
        except Exception as e:
            logger.debug(f"Could not get timestamp for analysis: {e}")
            if fallback_updated_at and fallback_updated_at.tzinfo is None:
                return fallback_updated_at.replace(tzinfo=timezone.utc)
            return fallback_updated_at
    
    def import_csv_with_smart_updates(self,
                                    csv_data: List[Dict[str, Any]],
                                    dataset_name: str,
                                    strategy: Optional[UpdateStrategy] = None) -> BulkUpdateStats:
        """
        Import CSV data with intelligent update handling.
        
        Args:
            csv_data: List of row dictionaries from CSV
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
            logger.info(f"Starting smart bulk import for dataset: {dataset_name} with linking: {self.link_row_cells}, topology: {self.link_topology}")
            
            updates, action_stats = self.determine_update_actions(csv_data, dataset_name)
            overall_stats.merge(action_stats)
            logger.info(f"Determined {len(updates)} update actions. Truncated values: {action_stats.truncated_values}")
            
            execution_stats = self.execute_bulk_update(updates, dataset_name, action_stats, batch_size=1000)
            overall_stats.merge(execution_stats)
            
            logger.info(f"Smart bulk import completed: {overall_stats}")
            return overall_stats
            
        finally:
            if strategy:
                self.default_strategy = original_strategy

    def import_csv_with_mappings(self,
                               csv_data: List[Dict[str, Any]],
                               dataset_name: str,
                               organization_id: str,
                               auto_create_entity_mapping: bool = True) -> Dict[str, Any]:
        """
        Import CSV data using Mapping definitions for efficient entity-focused triple creation.
        
        Args:
            csv_data: List of row dictionaries from CSV
            dataset_name: Name of the dataset  
            organization_id: Organization identifier
            auto_create_entity_mapping: Whether to auto-create entity mapping if none exists
            
        Returns:
            Dictionary with execution results and statistics
        """
        logger.info(f"Starting mapping-based import for dataset: {dataset_name}, org: {organization_id}")
        
        try:
            # Look for existing mappings for this dataset
            existing_mappings = Mapping.objects.filter(
                organization_id=organization_id,
                source_datasets__contains=dataset_name,
                validation_status='active'
            )
            
            results = {
                'dataset_name': dataset_name,
                'organization_id': organization_id,
                'mappings_executed': [],
                'total_entities_created': 0,
                'total_triples_created': 0,
                'total_errors': 0,
                'execution_time': None
            }
            
            start_time = datetime.now()
            executor = MappingExecutor(base_uri=self.base_uri)
            
            if not existing_mappings.exists():
                if auto_create_entity_mapping:
                    logger.info(f"No mappings found for {dataset_name}. Auto-creating entity mapping.")
                    entity_mapping = self._auto_create_entity_mapping(
                        csv_data, dataset_name, organization_id
                    )
                    existing_mappings = [entity_mapping]
                else:
                    raise ValueError(f"No active mappings found for dataset {dataset_name} in organization {organization_id}")
            
            # Execute all available mappings (no type ordering needed with flexible model)
            for mapping in existing_mappings:
                    try:
                        logger.info(f"Executing mapping: {mapping.name}")
                        
                        stats = executor.execute_mapping(mapping, csv_data)
                        
                        mapping_result = {
                            'mapping_id': str(mapping.id),
                            'mapping_name': mapping.name,
                            'description': mapping.description,
                            'entities_created': stats.entities_created,
                            'entities_updated': stats.entities_updated,
                            'triples_created': stats.triples_created,
                            'lookups_resolved': stats.lookups_resolved,
                            'rows_processed': stats.rows_processed,
                            'errors': stats.errors
                        }
                        
                        results['mappings_executed'].append(mapping_result)
                        results['total_entities_created'] += stats.entities_created
                        results['total_triples_created'] += stats.triples_created
                        results['total_errors'] += stats.errors
                        
                        logger.info(f"Mapping {mapping.name} completed: {stats.entities_created} entities, {stats.triples_created} triples")
                        
                    except Exception as e:
                        logger.error(f"Error executing mapping {mapping.name}: {e}", exc_info=True)
                        results['total_errors'] += 1
                        
                        error_result = {
                            'mapping_id': str(mapping.id),
                            'mapping_name': mapping.name,
                            'description': mapping.description,
                            'error': str(e),
                            'entities_created': 0,
                            'triples_created': 0,
                            'errors': 1
                        }
                        results['mappings_executed'].append(error_result)
            
            end_time = datetime.now()
            results['execution_time'] = (end_time - start_time).total_seconds()
            
            logger.info(f"Mapping-based import completed: {results['total_entities_created']} entities, "
                       f"{results['total_triples_created']} triples, {results['total_errors']} errors")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in mapping-based import: {e}", exc_info=True)
            raise

    def _auto_create_entity_mapping(self, 
                                  csv_data: List[Dict[str, Any]], 
                                  dataset_name: str, 
                                  organization_id: str) -> Mapping:
        """
        Auto-create a basic entity mapping for a dataset.
        
        Analyzes the CSV structure and creates sensible defaults:
        - Uses first column or 'ID' column as subject
        - Maps remaining columns to generic properties
        """
        if not csv_data:
            raise ValueError("Cannot create mapping from empty CSV data")
        
        # Get column names from first row
        columns = list(csv_data[0].keys())
        
        # Determine subject column (prefer 'ID', 'id', or first column)
        subject_column = None
        for candidate in ['ID', 'id', 'Id', 'uuid', 'UUID']:
            if candidate in columns:
                subject_column = candidate
                break
        
        if not subject_column:
            subject_column = columns[0]
            logger.info(f"Using first column '{subject_column}' as subject for entity mapping")
        
        # Create predicate mappings for other columns
        predicate_mappings = {}
        base_predicate_uri = f"http://arkumu.org/vocab/{organization_id}/"
        
        for column in columns:
            if column != subject_column:
                # Create a simple predicate URI from column name
                predicate_name = slugify_uri_part(column.lower().replace(' ', '_'))
                predicate_mappings[column] = f"{base_predicate_uri}{predicate_name}"
        
        # Create the mapping
        mapping_config = {
            'subject_column': subject_column,
            'predicate_mappings': predicate_mappings,
            'base_uri_template': f'{self.base_uri}/{organization_id}/{dataset_name}/entities/{{subject}}'
        }
        
        mapping = Mapping.objects.create(
            name=f"Auto-generated Entity Mapping for {dataset_name}",
            description=f"Automatically generated mapping for dataset {dataset_name}",
            organization_id=organization_id,
            source_datasets=[dataset_name],
            mapping_config=mapping_config,
            validation_status='active'
        )
        
        logger.info(f"Auto-created entity mapping {mapping.id} for {dataset_name} with subject column: {subject_column}")
        return mapping 