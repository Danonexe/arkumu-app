import logging
import polars as pl
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.bulk_update_engine import BulkUpdateStats
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
from arkumu.importer.services.importer.uri_utils import slugify_uri_part

logger = logging.getLogger(__name__)


@dataclass
class FKRelationship:
    """Foreign key relationship configuration"""
    source_column: str
    source_dataset: str
    target_column: str
    target_dataset: str
    relationship_type: str


class BulkRelationshipProcessor:
    """
    Handles foreign key relationships and cross-dataset entity linking.
    
    Responsibilities:
    - Process FK relationships between datasets
    - Create cross-dataset entity links
    - Handle junction table relationships
    - Resolve entity references and create proper triples
    """
    
    def __init__(self, uri_service: BulkURIService):
        """
        Initialize the relationship processor.
        
        Args:
            uri_service: URI service for generating resource URIs
        """
        self.uri_service = uri_service
    
    def process_fk_relationships(self, datasets: Dict[str, Union[List[Dict[str, Any]], pl.DataFrame]], 
                                fk_relationships: List[FKRelationship]) -> BulkUpdateStats:
        """
        Process foreign key relationships between datasets.
        
        Args:
            datasets: Dictionary mapping dataset names to their data
            fk_relationships: List of FKRelationship configurations
            
        Returns:
            BulkUpdateStats with FK processing results
        """
        if not fk_relationships:
            return BulkUpdateStats()
        
        logger.info(f"Processing {len(fk_relationships)} FK relationships")
        fk_stats = BulkUpdateStats()
        
        for fk_rel in fk_relationships:
            try:
                self._process_single_fk_relationship(fk_rel, datasets, fk_stats)
            except Exception as e:
                logger.error(f"Error processing FK relationship {fk_rel}: {e}", exc_info=True)
                fk_stats.errors += 1
        
        logger.info(f"FK processing completed: {fk_stats.triples_created} relationship triples created")
        return fk_stats
    
    def _process_single_fk_relationship(self, fk_rel: FKRelationship, 
                                      datasets: Dict[str, Union[List[Dict[str, Any]], pl.DataFrame]], 
                                      stats: BulkUpdateStats):
        """Process a single FK relationship."""
        
        # Get source and target datasets
        if fk_rel.source_dataset not in datasets or fk_rel.target_dataset not in datasets:
            logger.warning(f"Missing dataset for FK relationship: {fk_rel}")
            return
        
        source_df = self._ensure_dataframe(datasets[fk_rel.source_dataset])
        target_df = self._ensure_dataframe(datasets[fk_rel.target_dataset])
        
        if fk_rel.source_column not in source_df.columns:
            logger.warning(f"Source column '{fk_rel.source_column}' not found in dataset '{fk_rel.source_dataset}'")
            return
            
        if fk_rel.target_column not in target_df.columns:
            logger.warning(f"Target column '{fk_rel.target_column}' not found in dataset '{fk_rel.target_dataset}'")
            return
        
        # Create property resource for relationship
        relationship_prop, _ = Resource.objects.get_or_create(
            uri=self.uri_service.generate_property_uri(fk_rel.relationship_type),
            defaults={
                "resource_type": ResourceType.PROPERTY,
                "name": fk_rel.relationship_type,
                "source": self.uri_service.institution,
                "is_placeholder": False
            }
        )
        
        # Build target value lookup (target_column_value -> target_entity_uri)
        target_lookup = {}
        target_df_with_ids = target_df.with_row_index(name='row_id', offset=0)
        
        for target_row in target_df_with_ids.iter_rows(named=True):
            target_value = target_row.get(fk_rel.target_column)
            if target_value and str(target_value).strip():
                target_row_id = target_row.get('row_id', 0)
                display_row_id = int(target_row_id) + 1 if str(target_row_id).isdigit() else target_row_id
                
                # Target entity URI (using anchor column pattern)
                target_entity_uri = self.uri_service.generate_entity_uri(
                    fk_rel.target_dataset, str(target_value).strip()
                )
                target_lookup[str(target_value).strip()] = target_entity_uri
        
        # Process source dataset and create relationships
        source_df_with_ids = source_df.with_row_index(name='row_id', offset=0)
        relationship_triples = []
        
        for source_row in source_df_with_ids.iter_rows(named=True):
            fk_value = source_row.get(fk_rel.source_column)
            if fk_value and str(fk_value).strip():
                fk_value_str = str(fk_value).strip()
                
                if fk_value_str in target_lookup:
                    # Create source entity URI
                    source_row_id = source_row.get('row_id', 0)
                    source_anchor_value = self._get_anchor_value_for_row(source_row, fk_rel.source_dataset)
                    source_entity_uri = self.uri_service.generate_entity_uri(
                        fk_rel.source_dataset, source_anchor_value
                    )
                    
                    target_entity_uri = target_lookup[fk_value_str]
                    
                    # Get or create source and target entity resources
                    source_entity, _ = Resource.objects.get_or_create(
                        uri=source_entity_uri,
                        defaults={
                            "resource_type": ResourceType.IRI,
                            "name": source_anchor_value,
                            "source": self.uri_service.institution,
                            "is_placeholder": False
                        }
                    )
                    
                    target_entity, _ = Resource.objects.get_or_create(
                        uri=target_entity_uri,
                        defaults={
                            "resource_type": ResourceType.IRI,
                            "name": fk_value_str,
                            "source": self.uri_service.institution,
                            "is_placeholder": True  # Target might be stub
                        }
                    )
                    
                    # Create relationship triple
                    relationship_triples.append(
                        Triple(
                            subject=source_entity,
                            predicate=relationship_prop,
                            object=target_entity
                        )
                    )
        
        # Bulk create relationship triples
        if relationship_triples:
            Triple.objects.bulk_create(relationship_triples, ignore_conflicts=True)
            stats.triples_created += len(relationship_triples)
            stats.relationships_created += len(relationship_triples)
            logger.info(f"Created {len(relationship_triples)} relationship triples for {fk_rel.relationship_type}")
    
    def _get_anchor_value_for_row(self, row_data: Dict[str, Any], dataset_name: str) -> str:
        """Get anchor value for a row - simplified to use first available value or row ID."""
        # Try common anchor column names first
        for anchor_col in ['id', 'ID', 'name', 'Name']:
            if anchor_col in row_data and row_data[anchor_col]:
                return str(row_data[anchor_col]).strip()
        
        # Fall back to row_id
        row_id = row_data.get('row_id', 'unknown')
        display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
        return str(display_row_id)

    def _ensure_dataframe(self, data: Union[List[Dict[str, Any]], pl.DataFrame]) -> pl.DataFrame:
        """Convert data to Polars DataFrame if it's not already."""
        if isinstance(data, pl.DataFrame):
            return data
        else:
            return pl.DataFrame(data)

    def create_junction_table_relationships(self, junction_data: pl.DataFrame, 
                                          primary_fk_column: str, primary_dataset: str,
                                          secondary_fk_column: str, secondary_dataset: str,
                                          relationship_type: str = "related_to",
                                          context_attributes: Optional[List[str]] = None) -> BulkUpdateStats:
        """
        Create relationships through a junction table with optional context attributes.
        
        Args:
            junction_data: DataFrame containing junction table data
            primary_fk_column: Column name for primary FK
            primary_dataset: Name of primary dataset
            secondary_fk_column: Column name for secondary FK  
            secondary_dataset: Name of secondary dataset
            relationship_type: Type of relationship to create
            context_attributes: Optional list of additional columns to include as context
            
        Returns:
            BulkUpdateStats with junction processing results
        """
        stats = BulkUpdateStats()
        
        if junction_data.height == 0:
            return stats
        
        logger.info(f"Processing junction table with {junction_data.height} rows")
        
        # Create relationship property
        relationship_prop, _ = Resource.objects.get_or_create(
            uri=self.uri_service.generate_property_uri(relationship_type),
            defaults={
                "resource_type": ResourceType.PROPERTY,
                "name": relationship_type,
                "source": self.uri_service.institution,
                "is_placeholder": False
            }
        )
        
        # Process each junction row
        junction_triples = []
        context_triples = []
        
        junction_df_with_ids = junction_data.with_row_index(name='junction_id', offset=0)
        
        for junction_row in junction_df_with_ids.iter_rows(named=True):
            primary_value = junction_row.get(primary_fk_column)
            secondary_value = junction_row.get(secondary_fk_column)
            junction_id = junction_row.get('junction_id', 0)
            
            if not primary_value or not secondary_value:
                continue
            
            try:
                # Create entity URIs
                primary_entity_uri = self.uri_service.generate_entity_uri(
                    primary_dataset, str(primary_value).strip()
                )
                secondary_entity_uri = self.uri_service.generate_entity_uri(
                    secondary_dataset, str(secondary_value).strip()
                )
                
                # Get or create entity resources
                primary_entity, _ = Resource.objects.get_or_create(
                    uri=primary_entity_uri,
                    defaults={
                        "resource_type": ResourceType.IRI,
                        "name": str(primary_value).strip(),
                        "source": self.uri_service.institution,
                        "is_placeholder": True
                    }
                )
                
                secondary_entity, _ = Resource.objects.get_or_create(
                    uri=secondary_entity_uri,
                    defaults={
                        "resource_type": ResourceType.IRI,
                        "name": str(secondary_value).strip(),
                        "source": self.uri_service.institution,
                        "is_placeholder": True
                    }
                )
                
                # Create direct relationship
                junction_triples.append(
                    Triple(
                        subject=primary_entity,
                        predicate=relationship_prop,
                        object=secondary_entity
                    )
                )
                
                # Handle context attributes if specified
                if context_attributes:
                    # Create junction entity for context
                    junction_uri = self.uri_service.generate_junction_uri(
                        f"{primary_dataset}_{secondary_dataset}", 
                        relationship_type, 
                        str(junction_id)
                    )
                    
                    junction_entity, _ = Resource.objects.get_or_create(
                        uri=junction_uri,
                        defaults={
                            "resource_type": ResourceType.IRI,
                            "name": f"Junction {junction_id}",
                            "source": self.uri_service.institution,
                            "is_placeholder": False
                        }
                    )
                    
                    # Link junction to both entities
                    has_part_prop, _ = Resource.objects.get_or_create(
                        uri="http://purl.org/dc/terms/hasPart",
                        defaults={
                            "resource_type": ResourceType.PROPERTY,
                            "name": "hasPart",
                            "source": self.uri_service.institution,
                            "is_placeholder": False
                        }
                    )
                    
                    context_triples.extend([
                        Triple(subject=junction_entity, predicate=has_part_prop, object=primary_entity),
                        Triple(subject=junction_entity, predicate=has_part_prop, object=secondary_entity)
                    ])
                    
                    # Add context attribute values
                    for attr_column in context_attributes:
                        attr_value = junction_row.get(attr_column)
                        if attr_value and str(attr_value).strip():
                            # Create context property
                            context_prop, _ = Resource.objects.get_or_create(
                                uri=self.uri_service.generate_property_uri(attr_column),
                                defaults={
                                    "resource_type": ResourceType.PROPERTY,
                                    "name": attr_column,
                                    "source": self.uri_service.institution,
                                    "is_placeholder": False
                                }
                            )
                            
                            # Create literal value
                            context_literal, _ = Resource.objects.get_or_create(
                                resource_type=ResourceType.LITERAL,
                                value=str(attr_value).strip(),
                                source=self.uri_service.institution,
                                defaults={"name": attr_column}
                            )
                            
                            context_triples.append(
                                Triple(subject=junction_entity, predicate=context_prop, object=context_literal)
                            )
                
            except Exception as e:
                logger.error(f"Error processing junction row {junction_id}: {e}")
                stats.errors += 1
        
        # Bulk create all triples
        all_triples = junction_triples + context_triples
        if all_triples:
            Triple.objects.bulk_create(all_triples, ignore_conflicts=True)
            stats.triples_created += len(all_triples)
            stats.relationships_created += len(junction_triples)
            logger.info(f"Created {len(junction_triples)} junction relationships and {len(context_triples)} context triples")
        
        return stats

    def resolve_entity_references(self, dataset_name: str, anchor_column: str,
                                reference_datasets: List[str]) -> Dict[str, Any]:
        """
        Resolve entity references by looking up values in reference datasets.
        
        Args:
            dataset_name: Name of the dataset containing references
            anchor_column: Column containing reference values
            reference_datasets: List of dataset names to search for matching entities
            
        Returns:
            Dictionary with resolution results and statistics
        """
        results = {
            "resolved_references": 0,
            "unresolved_references": 0,
            "reference_mappings": {},
            "errors": 0
        }
        
        try:
            # Get all cells from the anchor column in the main dataset
            dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
            column_uri = self.uri_service.generate_column_uri(dataset_name, anchor_column)
            
            # Find all cell resources for this column
            anchor_cells = Resource.objects.filter(
                uri__startswith=column_uri
            )
            
            # For each reference dataset, build a lookup of possible matches
            reference_lookup = {}
            for ref_dataset in reference_datasets:
                ref_dataset_uri = self.uri_service.generate_dataset_uri(ref_dataset)
                ref_resources = Resource.objects.filter(
                    uri__startswith=ref_dataset_uri,
                    resource_type=ResourceType.IRI
                )
                
                for resource in ref_resources:
                    # Extract value from resource name or URI
                    reference_lookup[resource.name] = resource.uri
            
            # Process each anchor cell and try to resolve references
            for cell in anchor_cells:
                try:
                    # Get the literal value for this cell
                    value_triples = Triple.objects.filter(
                        subject=cell,
                        predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                    )
                    
                    if value_triples.exists():
                        literal_value = value_triples.first().object.value
                        
                        if literal_value in reference_lookup:
                            # Found a match!
                            target_uri = reference_lookup[literal_value]
                            results["reference_mappings"][cell.uri] = target_uri
                            results["resolved_references"] += 1
                        else:
                            results["unresolved_references"] += 1
                    
                except Exception as e:
                    logger.error(f"Error resolving reference for cell {cell.uri}: {e}")
                    results["errors"] += 1
            
            logger.info(f"Entity reference resolution: {results['resolved_references']} resolved, "
                       f"{results['unresolved_references']} unresolved, {results['errors']} errors")
            
        except Exception as e:
            logger.error(f"Error in entity reference resolution: {e}", exc_info=True)
            results["errors"] += 1
        
        return results

    def create_hierarchical_relationships(self, dataset_name: str, 
                                        parent_column: str, child_column: str,
                                        relationship_type: str = "hasChild") -> BulkUpdateStats:
        """
        Create hierarchical relationships within a dataset.
        
        Args:
            dataset_name: Name of the dataset
            parent_column: Column containing parent identifiers
            child_column: Column containing child identifiers
            relationship_type: Type of hierarchical relationship
            
        Returns:
            BulkUpdateStats with hierarchy processing results
        """
        stats = BulkUpdateStats()
        
        try:
            # Create relationship property
            relationship_prop, _ = Resource.objects.get_or_create(
                uri=self.uri_service.generate_property_uri(relationship_type),
                defaults={
                    "resource_type": ResourceType.PROPERTY,
                    "name": relationship_type,
                    "source": self.uri_service.institution,
                    "is_placeholder": False
                }
            )
            
            # Get all cells from both columns
            parent_column_uri = self.uri_service.generate_column_uri(dataset_name, parent_column)
            child_column_uri = self.uri_service.generate_column_uri(dataset_name, child_column)
            
            parent_cells = Resource.objects.filter(uri__startswith=parent_column_uri)
            child_cells = Resource.objects.filter(uri__startswith=child_column_uri)
            
            # Build lookup of values to entities
            value_to_entity = {}
            
            # Process parent cells
            for cell in parent_cells:
                row_id = self.uri_service.extract_row_id_from_uri(cell.uri)
                if row_id:
                    # Get literal value
                    value_triples = Triple.objects.filter(
                        subject=cell,
                        predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                    )
                    
                    if value_triples.exists():
                        literal_value = value_triples.first().object.value
                        entity_uri = self.uri_service.generate_entity_uri(dataset_name, literal_value)
                        value_to_entity[literal_value] = entity_uri
            
            # Process child cells and create relationships
            hierarchy_triples = []
            
            for cell in child_cells:
                row_id = self.uri_service.extract_row_id_from_uri(cell.uri)
                if row_id:
                    # Get child value
                    child_value_triples = Triple.objects.filter(
                        subject=cell,
                        predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                    )
                    
                    if child_value_triples.exists():
                        child_value = child_value_triples.first().object.value
                        
                        # Find corresponding parent cell in the same row
                        parent_cell_uri = self.uri_service.generate_cell_uri(dataset_name, parent_column, row_id)
                        
                        try:
                            parent_cell = Resource.objects.get(uri=parent_cell_uri)
                            parent_value_triples = Triple.objects.filter(
                                subject=parent_cell,
                                predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                            )
                            
                            if parent_value_triples.exists():
                                parent_value = parent_value_triples.first().object.value
                                
                                # Create entity resources
                                parent_entity_uri = self.uri_service.generate_entity_uri(dataset_name, parent_value)
                                child_entity_uri = self.uri_service.generate_entity_uri(dataset_name, child_value)
                                
                                parent_entity, _ = Resource.objects.get_or_create(
                                    uri=parent_entity_uri,
                                    defaults={
                                        "resource_type": ResourceType.IRI,
                                        "name": parent_value,
                                        "source": self.uri_service.institution,
                                        "is_placeholder": False
                                    }
                                )
                                
                                child_entity, _ = Resource.objects.get_or_create(
                                    uri=child_entity_uri,
                                    defaults={
                                        "resource_type": ResourceType.IRI,
                                        "name": child_value,
                                        "source": self.uri_service.institution,
                                        "is_placeholder": False
                                    }
                                )
                                
                                # Create hierarchical relationship
                                hierarchy_triples.append(
                                    Triple(
                                        subject=parent_entity,
                                        predicate=relationship_prop,
                                        object=child_entity
                                    )
                                )
                        
                        except Resource.DoesNotExist:
                            logger.warning(f"Parent cell not found: {parent_cell_uri}")
            
            # Bulk create hierarchy triples
            if hierarchy_triples:
                Triple.objects.bulk_create(hierarchy_triples, ignore_conflicts=True)
                stats.triples_created += len(hierarchy_triples)
                stats.relationships_created += len(hierarchy_triples)
                logger.info(f"Created {len(hierarchy_triples)} hierarchical relationships")
        
        except Exception as e:
            logger.error(f"Error creating hierarchical relationships: {e}", exc_info=True)
            stats.errors += 1
        
        return stats