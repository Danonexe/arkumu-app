import logging
import warnings
from typing import Dict, Any, List
from django.db import transaction

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)

# Deprecation warning
warnings.warn(
    "The RowLinker class is deprecated and will be removed in a future version. "
    "Use the integrated row linking functionality in bulk_import.py instead, "
    "which supports multiple linking topologies (row, first_column, mesh).",
    DeprecationWarning,
    stacklevel=2
)

class RowLinker:
    """
    Service for creating explicit links between cells in the same row.
    This enhances the cell-based import model by adding row-level relationships.
    
    DEPRECATED: This functionality has been integrated into bulk_import.py.
    Use import_csv_as_cells with the link_topology parameter instead.
    """
    
    @staticmethod
    def link_row_cells(
        dataset_name: str,
        row_id: str,
        cell_resources: List[Resource],
        same_row_property: Resource,
        link_to_first_column: bool = False
    ) -> Dict[str, Any]:
        """
        Create explicit links between cells in the same row.
        
        DEPRECATED: Use import_csv_as_cells with link_topology="first_column" or link_topology="mesh" instead.
        
        Args:
            dataset_name: Name of the dataset
            row_id: Identifier for the row
            cell_resources: List of cell resources from the same row
            same_row_property: Pre-created sameRow property resource
            link_to_first_column: If True, use the first column as the anchor and link all other cells to it
                                  If False, create a complete network of links between all cells
            
        Returns:
            Dict with statistics about created links
        """
        warnings.warn(
            "link_row_cells is deprecated. Use import_csv_as_cells with link_topology parameter instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        stats = {
            "row_links_created": 0,
            "triples_created": 0,
            "errors": 0
        }
        
        if not cell_resources or len(cell_resources) < 2:
            logger.debug(f"Not enough cell resources to link for row {row_id} in {dataset_name}")
            return stats
        
        try:
            # Prepare triples for bulk creation
            triples_to_create = []
            
            # Create links between cells based on the selected strategy
            if link_to_first_column and cell_resources:
                # Strategy 1: Link all cells to the first column (star topology)
                anchor_cell = cell_resources[0]
                logger.debug(f"Using first column as anchor: {anchor_cell.name}")
                
                for i in range(1, len(cell_resources)):
                    # Create unidirectional links from anchor to other cells
                    triples_to_create.append(
                        Triple(
                            subject=anchor_cell,
                            predicate=same_row_property,
                            object=cell_resources[i]
                        )
                    )
                    stats["row_links_created"] += 1
                    
                    logger.debug(f"Prepared link {anchor_cell.name} → {cell_resources[i].name}")
            else:
                # Strategy 2: Link all cells to each other (mesh topology)
                # Use a consistent direction (lower index → higher index)
                for i in range(len(cell_resources)):
                    for j in range(i+1, len(cell_resources)):
                        # Create unidirectional links between all pairs of cells
                        triples_to_create.append(
                            Triple(
                                subject=cell_resources[i],
                                predicate=same_row_property,
                                object=cell_resources[j]
                            )
                        )
                        stats["row_links_created"] += 1
                        
                        logger.debug(f"Prepared link {cell_resources[i].name} → {cell_resources[j].name}")
            
            # Bulk create all triples for this row
            if triples_to_create:
                Triple.objects.bulk_create(triples_to_create, ignore_conflicts=True)
                stats["triples_created"] = len(triples_to_create)
                logger.debug(f"Bulk created {len(triples_to_create)} triples for row {row_id}")
            
            logger.debug(f"Created {stats['row_links_created']} row links for {dataset_name}, row {row_id}")
            return stats
                
        except Exception as e:
            logger.error(f"Error linking row cells for {dataset_name}, row {row_id}: {e}")
            stats["errors"] += 1
            return stats
    
    @staticmethod
    def create_same_row_property(
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data"
    ) -> Resource:
        """
        Create or get the sameRow property resource.
        This should be called once per dataset import, not per row.
        
        DEPRECATED: This functionality is now handled internally by import_csv_as_cells.
        
        Args:
            institution: Institution code
            base_uri: Base URI for generated resources
            
        Returns:
            The sameRow property resource
        """
        warnings.warn(
            "create_same_row_property is deprecated. This is now handled internally by import_csv_as_cells.",
            DeprecationWarning,
            stacklevel=2
        )
        
        same_row_property, created = Resource.objects.get_or_create(
            uri=f"{base_uri}/properties/sameRow",
            defaults={
                "resource_type": ResourceType.PROPERTY,
                "name": "sameRow",
                "source": institution,
                "is_placeholder": False
            }
        )
        if created:
            logger.info(f"Created sameRow property resource")
        else:
            logger.debug(f"Retrieved existing sameRow property resource")
        
        return same_row_property
    
    @staticmethod
    def process_dataset(
        dataset_name: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        link_to_first_column: bool = False,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Process an entire dataset to create row links for all rows.
        This can be run after the initial import to add row-level relationships.
        
        DEPRECATED: Use import_csv_as_cells with link_topology parameter instead.
        For existing data, consider using the semantic linking functionality.
        
        Args:
            dataset_name: Name of the dataset
            institution: Institution code
            base_uri: Base URI for generated resources
            link_to_first_column: If True, use the first column as the anchor
            batch_size: Number of rows to process in each batch
            
        Returns:
            Dict with statistics about created links
        """
        warnings.warn(
            "process_dataset is deprecated. Use import_csv_as_cells with link_topology parameter instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        stats = {
            "rows_processed": 0,
            "row_links_created": 0,
            "resources_created": 0,
            "triples_created": 0,
            "errors": 0
        }
        
        try:
            # Get the dataset resource
            dataset_uri = f"{base_uri}/datasets/{dataset_name}"
            try:
                dataset = Resource.objects.get(uri=dataset_uri)
                logger.info(f"Found dataset resource for {dataset_name}")
            except Resource.DoesNotExist:
                logger.error(f"Dataset resource not found for {dataset_name}")
                stats["errors"] += 1
                return stats
            
            # Create the sameRow property once for the entire dataset
            same_row_property = RowLinker.create_same_row_property(institution, base_uri)
            stats["resources_created"] += 1 if same_row_property else 0
            
            # Get all row IDs in this dataset by parsing cell URIs
            # This assumes cell URIs follow the pattern {dataset_uri}/{column_name}/{row_id}
            from django.db.models import Q
            import re
            
            # Find all cells belonging to this dataset
            pattern = f"^{re.escape(dataset_uri)}/[^/]+/(.+)$"
            cells = Resource.objects.filter(uri__regex=pattern)
            
            # Extract row IDs from cell URIs
            row_ids = set()
            for cell in cells:
                match = re.match(pattern, cell.uri)
                if match:
                    row_id = match.group(1)
                    row_ids.add(row_id)
            
            logger.info(f"Found {len(row_ids)} rows in dataset {dataset_name}")
            
            # Process each row
            for row_id in row_ids:
                try:
                    # Get all cells for this row
                    row_pattern = f"^{re.escape(dataset_uri)}/([^/]+)/{re.escape(row_id)}$"
                    row_cells = Resource.objects.filter(uri__regex=row_pattern)
                    
                    if row_cells:
                        # Link cells in this row
                        row_stats = RowLinker.link_row_cells(
                            dataset_name=dataset_name,
                            row_id=row_id,
                            cell_resources=list(row_cells),
                            same_row_property=same_row_property,
                            link_to_first_column=link_to_first_column
                        )
                        
                        # Aggregate statistics
                        for key in ["row_links_created", "triples_created", "errors"]:
                            if key in row_stats:
                                stats[key] += row_stats[key]
                        
                        stats["rows_processed"] += 1
                        
                        # Log progress periodically
                        if stats["rows_processed"] % batch_size == 0:
                            logger.info(f"Processed {stats['rows_processed']} rows...")
                    
                except Exception as e:
                    logger.error(f"Error processing row {row_id} in {dataset_name}: {e}")
                    stats["errors"] += 1
            
            logger.info(f"Completed row linking for {dataset_name}: {stats['rows_processed']} rows processed, "
                        f"{stats['row_links_created']} row links created")
            return stats
            
        except Exception as e:
            logger.error(f"Error processing dataset {dataset_name} for row linking: {e}")
            stats["errors"] += 1
            return stats 