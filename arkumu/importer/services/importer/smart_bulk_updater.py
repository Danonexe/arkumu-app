import logging
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
import dateutil.parser
from django.db import transaction, models
from django.db.models import Q, Count, Exists, OuterRef
from django.utils import timezone as django_timezone

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.uri_utils import mint_uri

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
    errors: int = 0
    
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
        self.errors += other.errors


@dataclass
class ResourceUpdate:
    """Represents a potential resource update."""
    uri: str
    new_value: Optional[str] = None
    new_name: Optional[str] = None
    new_datatype: Optional[str] = None
    new_language: Optional[str] = None
    action: UpdateStrategy = UpdateStrategy.SKIP_EXISTING
    existing_resource: Optional[Resource] = None


class SmartBulkUpdater:
    """
    Intelligent bulk update service that leverages the URI-based data model
    for efficient duplicate detection and selective updates.
    """
    
    def __init__(self, 
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None,
                 institution: str = "DEFAULT",
                 base_uri: str = "http://arkumu.org/data"):
        """
        Initialize the smart bulk updater.
        
        Args:
            default_strategy: Default strategy for handling existing resources
            timestamp_column: Column name containing timestamps for timestamp-based updates
            institution: Institution code for URI generation
            base_uri: Base URI for resource generation
        """
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
        self.institution = institution
        self.base_uri = base_uri
        
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
            row_id = row.get('id', row.get('ID', str(row_num)))
            
            for column_name, value in row.items():
                if value and str(value).strip():
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, column_name, row_id)
                    
                    if cell_uri in existing_uri_map:
                        existing = existing_uri_map[cell_uri]
                        analysis["existing_resources"] += 1
                        
                        # Check if value would change
                        if existing['value'] != str(value).strip():
                            analysis["potential_updates"] += 1
                            
                            conflict_info = {
                                "uri": cell_uri,
                                "column": column_name,
                                "row_id": row_id,
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
                                        dataset_name, row_id, existing.get('updated_at')
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
                               dataset_name: str) -> List[ResourceUpdate]:
        """
        Determine what actions to take for each resource in the CSV data.
        
        Args:
            csv_data: List of row dictionaries from CSV
            dataset_name: Name of the dataset
            
        Returns:
            List of ResourceUpdate objects with determined actions
        """
        updates = []
        all_uris = []
        
        # Generate all URIs first
        uri_to_data_map = {}
        for row_num, row in enumerate(csv_data):
            row_id = row.get('id', row.get('ID', str(row_num)))
            
            for column_name, value in row.items():
                if value and str(value).strip():
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, column_name, row_id)
                    all_uris.append(cell_uri)
                    uri_to_data_map[cell_uri] = {
                        'value': str(value).strip(),
                        'column_name': column_name,
                        'row_id': row_id,
                        'row_data': row
                    }
        
        # Bulk fetch existing resources
        existing_resources = self.get_existing_resources_bulk(all_uris)
        
        # Determine actions for each URI
        for uri, data in uri_to_data_map.items():
            update = ResourceUpdate(uri=uri)
            update.new_value = data['value']
            update.new_name = data['column_name']
            update.new_datatype = "http://www.w3.org/2001/XMLSchema#string"
            
            if uri in existing_resources:
                existing = existing_resources[uri]
                update.existing_resource = existing
                
                # Determine update strategy
                if self.default_strategy == UpdateStrategy.SKIP_EXISTING:
                    update.action = UpdateStrategy.SKIP_EXISTING
                elif self.default_strategy == UpdateStrategy.UPDATE_VALUES:
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
        
        return updates
    
    def execute_bulk_update(self, 
                          updates: List[ResourceUpdate],
                          batch_size: int = 1000) -> BulkUpdateStats:
        """
        Execute a list of resource updates efficiently.
        
        Args:
            updates: List of ResourceUpdate objects
            batch_size: Number of updates to process in each batch
            
        Returns:
            BulkUpdateStats with operation statistics
        """
        stats = BulkUpdateStats()
        
        # Group updates by action type for efficient processing
        creates = [u for u in updates if u.existing_resource is None]
        skips = [u for u in updates if u.action == UpdateStrategy.SKIP_EXISTING]
        value_updates = [u for u in updates if u.action == UpdateStrategy.UPDATE_VALUES and u.existing_resource is not None]
        
        logger.info(f"Executing bulk update: {len(creates)} creates, {len(value_updates)} updates, {len(skips)} skips")
        
        # Process creates in batches
        if creates:
            stats.merge(self._execute_creates(creates, batch_size))
        
        # Process updates in batches
        if value_updates:
            stats.merge(self._execute_updates(value_updates, batch_size))
        
        # Count skips
        stats.resources_skipped = len(skips)
        
        return stats
    
    def _execute_creates(self, creates: List[ResourceUpdate], batch_size: int) -> BulkUpdateStats:
        """Execute resource creation in batches."""
        stats = BulkUpdateStats()
        
        for i in range(0, len(creates), batch_size):
            batch = creates[i:i + batch_size]
            
            try:
                with transaction.atomic():
                    resources_to_create = []
                    
                    for update in batch:
                        # Create cell resource
                        cell_resource = Resource(
                            uri=update.uri,
                            resource_type=ResourceType.IRI,
                            source=self.institution,
                            name=update.new_name
                        )
                        resources_to_create.append(cell_resource)
                        
                        # Create value resource
                        value_resource = Resource(
                            resource_type=ResourceType.LITERAL,
                            source=self.institution,
                            name=update.new_name,
                            value=update.new_value,
                            datatype=update.new_datatype
                        )
                        resources_to_create.append(value_resource)
                    
                    # Bulk create
                    created = Resource.objects.bulk_create(
                        resources_to_create, 
                        ignore_conflicts=True,
                        batch_size=500
                    )
                    
                    stats.resources_created += len(created)
                    stats.cells_processed += len(batch)
                    
            except Exception as e:
                logger.error(f"Error creating batch: {e}")
                stats.errors += len(batch)
        
        return stats
    
    def _execute_updates(self, updates: List[ResourceUpdate], batch_size: int) -> BulkUpdateStats:
        """Execute resource updates in batches."""
        stats = BulkUpdateStats()
        
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            
            try:
                with transaction.atomic():
                    for update in batch:
                        if update.existing_resource and update.existing_resource.value != update.new_value:
                            # Find and update the corresponding literal resource
                            literal_resources = Resource.objects.filter(
                                resource_type=ResourceType.LITERAL,
                                source=self.institution,
                                name=update.new_name,
                                value=update.existing_resource.value
                            )
                            
                            updated_count = literal_resources.update(value=update.new_value)
                            if updated_count > 0:
                                stats.resources_updated += updated_count
                            
                    stats.cells_processed += len(batch)
                    
            except Exception as e:
                logger.error(f"Error updating batch: {e}")
                stats.errors += len(batch)
        
        return stats
    
    def _determine_timestamp_action(self, existing: Resource, new_data: Dict[str, Any]) -> UpdateStrategy:
        """Determine action based on timestamp comparison."""
        if not self.timestamp_column or self.timestamp_column not in new_data:
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
            # We need to find the timestamp in the existing data
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
                self.timestamp_column, 
                row_id
            )
            
            # Find the corresponding literal resource with the timestamp value
            timestamp_resources = Resource.objects.filter(
                resource_type=ResourceType.LITERAL,
                source=self.institution,
                name=self.timestamp_column
            )
            
            # Get the cell resource first
            try:
                timestamp_cell = Resource.objects.get(uri=timestamp_cell_uri)
                # Find the literal value linked to this cell through triples
                timestamp_triples = Triple.objects.filter(
                    subject=timestamp_cell,
                    predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                ).select_related('object')
                
                if timestamp_triples.exists():
                    timestamp_value = timestamp_triples.first().object.value
                    return self._parse_timestamp(timestamp_value)
                    
            except Resource.DoesNotExist:
                # Timestamp cell doesn't exist yet, treat as no existing timestamp
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
            # Construct URI for the timestamp cell
            timestamp_cell_uri = mint_uri(
                self.base_uri, 
                self.institution, 
                "datasets", 
                dataset_name, 
                self.timestamp_column, 
                row_id
            )
            
            # Try to find the timestamp value
            try:
                timestamp_cell = Resource.objects.get(uri=timestamp_cell_uri)
                timestamp_triples = Triple.objects.filter(
                    subject=timestamp_cell,
                    predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                ).select_related('object')
                
                if timestamp_triples.exists():
                    timestamp_value = timestamp_triples.first().object.value
                    parsed = self._parse_timestamp(timestamp_value)
                    if parsed:
                        return parsed
                        
            except Resource.DoesNotExist:
                pass
            
            # Fallback to updated_at
            return fallback_updated_at
            
        except Exception as e:
            logger.debug(f"Could not get timestamp for analysis: {e}")
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
        
        try:
            logger.info(f"Starting smart bulk import for dataset: {dataset_name}")
            
            # Analyze changes first
            analysis = self.analyze_dataset_changes(dataset_name, csv_data)
            logger.info(f"Dataset analysis: {analysis}")
            
            # Determine update actions
            updates = self.determine_update_actions(csv_data, dataset_name)
            logger.info(f"Determined {len(updates)} update actions")
            
            # Execute updates
            stats = self.execute_bulk_update(updates)
            
            logger.info(f"Smart bulk import completed: {stats}")
            return stats
            
        finally:
            if strategy:
                self.default_strategy = original_strategy 