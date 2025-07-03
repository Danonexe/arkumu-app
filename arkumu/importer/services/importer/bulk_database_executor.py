import logging
from typing import Dict, List, Any, Optional, Set
from django.db import transaction

from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.bulk_update_engine import ResourceUpdate, UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService

logger = logging.getLogger(__name__)


class BulkDatabaseExecutor:
    """
    Handles all database operations and bulk processing for import operations.
    
    Responsibilities:
    - Bulk resource creation and updates
    - Triple generation and insertion
    - Transaction management and error handling
    - Topology implementation (row/first_column/mesh linking patterns)
    """
    
    def __init__(self, uri_service: BulkURIService, 
                 link_row_cells: bool = False,
                 link_topology: str = "row"):
        """
        Initialize the database executor.
        
        Args:
            uri_service: URI service for generating resource URIs
            link_row_cells: Whether to create links between cells in the same row
            link_topology: Topology for linking cells ('row', 'first_column', 'mesh')
        """
        self.uri_service = uri_service
        self.link_row_cells = link_row_cells
        self.link_topology = link_topology
        
        # RDF properties (will be initialized when needed)
        self.has_part_prop = None
        self.rdf_value_prop = None
        self.dcterms_relation_prop = None
    
    def ensure_rdf_properties(self):
        """Ensure RDF properties exist, creating them if necessary."""
        try:
            if self.has_part_prop is None:
                self.has_part_prop, _ = Resource.objects.get_or_create(
                    uri="http://purl.org/dc/terms/hasPart",
                    defaults={
                        "resource_type": ResourceType.PROPERTY, 
                        "name": "hasPart", 
                        "source": self.uri_service.institution, 
                        "is_placeholder": False
                    }
                )
            
            if self.rdf_value_prop is None:
                self.rdf_value_prop, _ = Resource.objects.get_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                    defaults={
                        "resource_type": ResourceType.PROPERTY, 
                        "name": "value", 
                        "source": self.uri_service.institution, 
                        "is_placeholder": False
                    }
                )
            
            if self.dcterms_relation_prop is None:
                self.dcterms_relation_prop, _ = Resource.objects.get_or_create(
                    uri="http://purl.org/dc/terms/relation",
                    defaults={
                        "resource_type": ResourceType.PROPERTY, 
                        "name": "relation", 
                        "source": self.uri_service.institution, 
                        "is_placeholder": False
                    }
                )
        except Exception as e:
            logger.error(f"Failed to ensure RDF properties: {e}", exc_info=True)

    def execute_bulk_update(self, updates: List[ResourceUpdate], dataset_name: str, 
                          batch_size: int = 1000) -> BulkUpdateStats:
        """
        Execute bulk updates with multi-value support and optimized batch processing.
        
        Args:
            updates: List of ResourceUpdate objects to execute
            dataset_name: Name of the dataset being processed
            batch_size: Size of batches for processing
            
        Returns:
            BulkUpdateStats with execution metrics
        """
        logger.info(f"Executing {len(updates)} updates for dataset '{dataset_name}' with batch size {batch_size}")
        
        if not updates:
            return BulkUpdateStats()
        
        stats = BulkUpdateStats()
        
        # Extract row_ids for row linking if enabled
        row_ids = set()
        if self.link_row_cells:
            for update in updates:
                row_id = self.uri_service.extract_row_id_from_uri(update.uri)
                if row_id:
                    row_ids.add(row_id)
        
        # Process updates in batches
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            active_updates = [u for u in batch if u.action in {UpdateStrategy.UPDATE_VALUES}]
            
            # Process the batch
            self._execute_batch_with_multi_value_support(active_updates, dataset_name, stats)
        
        logger.info(f"Bulk update execution completed: {stats}")
        return stats
    
    def _execute_batch_with_multi_value_support(self, batch: List[ResourceUpdate], 
                                              dataset_name: str, stats: BulkUpdateStats):
        """
        Execute a batch of updates with proper bulk operations.
        Creates dataset and row resources with proper hasPart relationships.
        """
        if not batch:
            return
        
        # Ensure RDF properties are available
        self.ensure_rdf_properties()
        
        # Create dataset resource first
        dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
        dataset_resource, ds_created = Resource.objects.get_or_create(
            uri=dataset_uri,
            defaults={
                "resource_type": ResourceType.IRI, 
                "name": dataset_name, 
                "source": self.uri_service.institution
            }
        )
        if ds_created:
            stats.resources_created += 1
        
        # Filter out skipped updates
        active_updates = [update for update in batch if update.action != UpdateStrategy.SKIP_EXISTING]
        if not active_updates:
            return
        
        # Collect row_ids for later use in topology
        row_ids_in_batch = set()
        for update in active_updates:
            row_id = self.uri_service.extract_row_id_from_uri(update.uri)
            if row_id:
                row_ids_in_batch.add(row_id)
        
        # Track cells processed
        stats.cells_processed += len(active_updates)
        
        # Prepare cell resources for bulk creation
        cell_resources_to_create = []
        uri_to_update_map = {}
        
        for update in active_updates:
            cell_resources_to_create.append(Resource(
                uri=update.uri,
                resource_type=ResourceType.IRI,
                source=self.uri_service.institution,
                name=update.new_name or "Cell"
            ))
            uri_to_update_map[update.uri] = update
        
        # Bulk create cell resources
        if cell_resources_to_create:
            Resource.objects.bulk_create(
                cell_resources_to_create,
                ignore_conflicts=True,
                batch_size=500
            )
            stats.resources_created += len({u.uri for u in active_updates})
        
        # Group updates by row for row creation (use 1-based IDs from URIs)
        row_grouping = {}
        for update in active_updates:
            row_id = self.uri_service.extract_row_id_from_uri(update.uri)  # This returns 1-based ID from URI
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
        unique_columns = set()
        for update in active_updates:
            column_name = self.uri_service.extract_column_name_from_uri(update.uri)
            if column_name:
                unique_columns.add(column_name)
        
        column_resources = {}
        logger.info(f"Creating {len(unique_columns)} column resources for dataset '{dataset_name}'")
        
        for column_name in unique_columns:
            column_uri = self.uri_service.generate_column_uri(dataset_name, column_name)
            
            column_resource, col_created = Resource.objects.get_or_create(
                uri=column_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": column_name,
                    "source": self.uri_service.institution
                }
            )
            
            if col_created:
                stats.resources_created += 1
                
            column_resources[column_name] = column_resource
            
            # Dataset → hasPart → Column
            if self.has_part_prop:
                structural_triples.append(
                    Triple(subject=dataset_resource, predicate=self.has_part_prop, object=column_resource)
                )
        
        # STEP 2: Topology-specific row resource creation (ONLY if needed)
        create_row_resources = (self.link_topology == "row" and self.link_row_cells)
        
        if create_row_resources:
            # ROW TOPOLOGY: Create row resources for dual hierarchy
            logger.info(f"Using 'row' topology - creating row resources")
            
            for row_id, row_updates in row_grouping.items():
                row_uri = self.uri_service.generate_row_uri(dataset_name, row_id)
                
                row_resource, row_created = Resource.objects.get_or_create(
                    uri=row_uri,
                    defaults={
                        "resource_type": ResourceType.IRI, 
                        "name": f"Row {row_id}", 
                        "source": self.uri_service.institution
                    }
                )
                if row_created:
                    stats.resources_created += 1
                
                # Dataset → hasPart → Row
                if self.has_part_prop:
                    structural_triples.append(
                        Triple(subject=dataset_resource, predicate=self.has_part_prop, object=row_resource)
                    )
        
        elif self.link_topology == "first_column":
            logger.info(f"Using 'first_column' topology - column hierarchy with star pattern")
            
        elif self.link_topology == "mesh":
            logger.info(f"Using 'mesh' topology - column hierarchy with full mesh")
            
        else:
            logger.info(f"Using column-only hierarchy with URI-based row tracking (minimal triples)")
        
        # STEP 3: Process each cell and create relationships based on topology
        logger.info(f"Starting STEP 3 - processing {len(uri_to_update_map)} cells")
        for cell_uri, update in uri_to_update_map.items():
            try:
                cell_resource = Resource.objects.get(uri=cell_uri)
                
                # ALWAYS: Link Column → hasPart → Cell (core semantic structure)
                column_name = self.uri_service.extract_column_name_from_uri(cell_uri)
                if column_name and column_name in column_resources:
                    column_resource = column_resources[column_name]
                    
                    if self.has_part_prop:
                        structural_triples.append(
                            Triple(subject=column_resource, predicate=self.has_part_prop, object=cell_resource)
                        )
                
                # TOPOLOGY-SPECIFIC: Additional cell relationships (ONLY if row resources exist)
                if create_row_resources:
                    # Row → hasPart → Cell (dual hierarchy - only when using row topology)
                    row_id = self.uri_service.extract_row_id_from_uri(cell_uri)
                    if row_id:
                        row_uri = self.uri_service.generate_row_uri(dataset_name, row_id)
                        try:
                            row_resource = Resource.objects.get(uri=row_uri)
                            
                            if self.has_part_prop:
                                structural_triples.append(
                                    Triple(subject=row_resource, predicate=self.has_part_prop, object=cell_resource)
                                )
                                stats.row_links_created += 1
                        except Resource.DoesNotExist:
                            logger.warning(f"Row resource not found: {row_uri}")
                
                # Create value resources and triples
                for value in update.new_values:
                    if value and value.strip():
                        value_resource, val_created = Resource.objects.get_or_create(
                            value=value,
                            resource_type=ResourceType.LITERAL,
                            source=self.uri_service.institution,
                            defaults={
                                "name": update.new_name or value, 
                                "datatype": update.new_datatype
                            }
                        )
                        
                        if val_created:
                            stats.resources_created += 1
                        
                        # Create rdf:value triple
                        if self.rdf_value_prop:
                            value_triples.append(
                                Triple(subject=cell_resource, predicate=self.rdf_value_prop, object=value_resource)
                            )
                        else:
                            logger.error(f"Cannot create value triple: rdf:value property not available")
                            stats.errors += 1
                        stats.total_values_created += 1
                        
            except Resource.DoesNotExist:
                logger.error(f"Cell resource {cell_uri} not found after bulk create. Skipping.")
                stats.errors += 1
            except Exception as e:
                logger.error(f"Error processing cell {cell_uri}: {e}", exc_info=True)
                stats.errors += 1
        
        # STEP 4: Post-processing topology patterns (first_column, mesh)
        topology_triples = []
        
        if self.link_topology == "first_column":
            # Create same-row property if needed
            same_row_prop, _ = Resource.objects.get_or_create(
                uri=self.uri_service.generate_property_uri("sameRow"),
                defaults={
                    "resource_type": ResourceType.PROPERTY, 
                    "name": "sameRow", 
                    "source": self.uri_service.institution
                }
            )
            
            # Group cells by row and link to first column cell (star pattern)
            for row_id, row_updates in row_grouping.items():
                if len(row_updates) > 1:
                    # Find first column cell (alphabetically first column)
                    first_column_update = min(row_updates, 
                                            key=lambda u: self.uri_service.extract_column_name_from_uri(u.uri) or "")
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
                uri=self.uri_service.generate_property_uri("sameRow"),
                defaults={
                    "resource_type": ResourceType.PROPERTY, 
                    "name": "sameRow", 
                    "source": self.uri_service.institution
                }
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

    def create_structural_hierarchy(self, dataset_name: str, unique_columns: Set[str], 
                                  row_ids: Set[str] = None) -> Dict[str, Resource]:
        """
        Create the basic structural hierarchy (Dataset → Columns → [Rows]).
        
        Args:
            dataset_name: Name of the dataset
            unique_columns: Set of unique column names
            row_ids: Optional set of row IDs for row topology
            
        Returns:
            Dictionary mapping resource types to created resources
        """
        created_resources = {}
        
        # Create dataset resource
        dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
        dataset_resource, ds_created = Resource.objects.get_or_create(
            uri=dataset_uri,
            defaults={
                "resource_type": ResourceType.IRI,
                "name": dataset_name,
                "source": self.uri_service.institution
            }
        )
        created_resources['dataset'] = dataset_resource
        
        # Create column resources
        column_resources = {}
        for column_name in unique_columns:
            column_uri = self.uri_service.generate_column_uri(dataset_name, column_name)
            
            column_resource, col_created = Resource.objects.get_or_create(
                uri=column_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": column_name,
                    "source": self.uri_service.institution
                }
            )
            column_resources[column_name] = column_resource
        
        created_resources['columns'] = column_resources
        
        # Create row resources if needed
        if row_ids and self.link_topology == "row" and self.link_row_cells:
            row_resources = {}
            for row_id in row_ids:
                row_uri = self.uri_service.generate_row_uri(dataset_name, row_id)
                
                row_resource, row_created = Resource.objects.get_or_create(
                    uri=row_uri,
                    defaults={
                        "resource_type": ResourceType.IRI,
                        "name": f"Row {row_id}",
                        "source": self.uri_service.institution
                    }
                )
                row_resources[row_id] = row_resource
            
            created_resources['rows'] = row_resources
        
        return created_resources

    def delete_dataset_resources(self, dataset_name: str) -> Dict[str, int]:
        """
        Delete all resources associated with a dataset.
        
        Args:
            dataset_name: Name of the dataset to delete
            
        Returns:
            Dictionary with deletion statistics
        """
        stats = {
            "resources_deleted": 0,
            "triples_deleted": 0,
            "errors": 0
        }
        
        try:
            with transaction.atomic():
                # Get dataset URI pattern
                dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
                
                # Find all resources related to this dataset
                dataset_resources = Resource.objects.filter(
                    uri__startswith=dataset_uri
                )
                
                # Delete triples involving these resources
                triples_deleted = Triple.objects.filter(
                    subject__in=dataset_resources
                ).delete()
                stats["triples_deleted"] += triples_deleted[0] if triples_deleted else 0
                
                triples_deleted = Triple.objects.filter(
                    object__in=dataset_resources
                ).delete()
                stats["triples_deleted"] += triples_deleted[0] if triples_deleted else 0
                
                # Delete the resources
                resources_deleted = dataset_resources.delete()
                stats["resources_deleted"] = resources_deleted[0] if resources_deleted else 0
                
                logger.info(f"Deleted dataset '{dataset_name}': {stats['resources_deleted']} resources, {stats['triples_deleted']} triples")
                
        except Exception as e:
            logger.error(f"Error deleting dataset '{dataset_name}': {e}", exc_info=True)
            stats["errors"] += 1
        
        return stats