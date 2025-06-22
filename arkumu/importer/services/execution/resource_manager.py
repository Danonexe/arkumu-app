"""
Resource management for efficient URI generation and bulk operations.
"""

import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from django.db import transaction
import polars as pl

from arkumu.metadata.models import Resource
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
from arkumu.importer.services.importer.smart_bulk_updater import MAX_INDEXED_VALUE_SIZE
from .statistics import ExecutionStatistics

logger = logging.getLogger(__name__)


class ResourceManager:
    """
    Manages resource creation, URI generation, and bulk operations.
    
    Handles efficient creation of RDF resources and their relationships
    with optimized database operations and memory usage.
    """
    
    def __init__(self, 
                 institution: str,
                 base_uri: str,
                 statistics: Optional[ExecutionStatistics] = None):
        """
        Initialize the resource manager.
        
        Args:
            institution: Institution code for URI generation
            base_uri: Base URI for resource generation
            statistics: Optional statistics tracker
        """
        self.institution = slugify_uri_part(str(institution)) if institution else "default"
        self.base_uri = base_uri
        self.statistics = statistics or ExecutionStatistics()
        
        # Initialize and cache standard RDF properties
        self._init_standard_properties()
    
    def _init_standard_properties(self) -> None:
        """Initialize standard RDF properties."""
        try:
            with transaction.atomic():
                self.has_part_prop, _ = Resource.objects.get_or_create(
                    uri="http://purl.org/dc/terms/hasPart",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "hasPart",
                        "source": self.institution,
                        "is_placeholder": False
                    }
                )
                self.rdf_value_prop, _ = Resource.objects.get_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "value",
                        "source": self.institution,
                        "is_placeholder": False
                    }
                )
                self.dcterms_relation_prop, _ = Resource.objects.get_or_create(
                    uri="http://purl.org/dc/terms/relation",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "relation",
                        "source": self.institution,
                        "is_placeholder": False
                    }
                )
        except Exception as e:
            logger.error(f"Failed to initialize standard RDF properties: {e}", exc_info=True)
            self.has_part_prop = None
            self.rdf_value_prop = None
            self.dcterms_relation_prop = None
    
    def generate_dataset_uri(self, dataset_name: str) -> str:
        """Generate URI for a dataset."""
        safe_dataset_name = slugify_uri_part(dataset_name)
        return mint_uri(self.base_uri, self.institution, "datasets", safe_dataset_name)
    
    def generate_column_uri(self, dataset_name: str, column_name: str) -> str:
        """Generate URI for a column."""
        safe_dataset_name = slugify_uri_part(dataset_name)
        safe_column_name = slugify_uri_part(column_name)
        return mint_uri(self.base_uri, self.institution, "datasets", safe_dataset_name, "columns", safe_column_name)
    
    def generate_row_uri(self, dataset_name: str, row_id: str) -> str:
        """Generate URI for a row."""
        safe_dataset_name = slugify_uri_part(dataset_name)
        safe_row_id = slugify_uri_part(str(row_id))
        return mint_uri(self.base_uri, self.institution, "datasets", safe_dataset_name, "rows", safe_row_id)
    
    def generate_cell_uri(self, dataset_name: str, column_name: str, row_id: str) -> str:
        """Generate URI for a cell."""
        safe_dataset_name = slugify_uri_part(dataset_name)
        safe_column_name = slugify_uri_part(column_name)
        safe_row_id = slugify_uri_part(str(row_id))
        return mint_uri(self.base_uri, self.institution, "datasets", safe_dataset_name, safe_column_name, safe_row_id)
    
    def extract_row_id_from_uri(self, cell_uri: str) -> Optional[str]:
        """Extract row ID from a cell URI."""
        try:
            return cell_uri.split('/')[-1]
        except IndexError:
            logger.warning(f"Could not parse row_id from cell_uri: {cell_uri}")
            return None
    
    def extract_column_name_from_uri(self, cell_uri: str) -> Optional[str]:
        """Extract column name from a cell URI."""
        try:
            parts = cell_uri.split('/')
            if 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 2 < len(parts):
                    return parts[datasets_index + 2]
            return None
        except (IndexError, ValueError):
            logger.warning(f"Could not parse column_name from cell_uri: {cell_uri}")
            return None
    
    def create_dataset_resource(self, dataset_name: str) -> Resource:
        """Create a dataset resource."""
        dataset_uri = self.generate_dataset_uri(dataset_name)
        logger.debug(f"Creating dataset resource with URI: {dataset_uri}")
        
        try:
            dataset_resource, created = Resource.objects.get_or_create(
                uri=dataset_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": dataset_name,
                    "source": self.institution
                }
            )
            
            if created:
                self.statistics.increment_resources_created()
                logger.debug(f"Dataset resource created successfully: {dataset_uri}")
            else:
                logger.debug(f"Dataset resource already exists: {dataset_uri}")
            
            logger.debug(f"Current resources_created count: {self.statistics.current_metrics.resources_created}")
            return dataset_resource
            
        except Exception as e:
            logger.error(f"Failed to create dataset resource {dataset_uri}: {e}", exc_info=True)
            raise
    
    def create_column_resources(self, dataset_name: str, column_names: List[str]) -> Dict[str, Resource]:
        """Create column resources in bulk."""
        column_resources = {}
        
        for column_name in column_names:
            column_uri = self.generate_column_uri(dataset_name, column_name)
            column_resource, created = Resource.objects.get_or_create(
                uri=column_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": column_name,
                    "source": self.institution
                }
            )
            if created:
                self.statistics.increment_resources_created()
            column_resources[column_name] = column_resource
        
        return column_resources
    
    def create_row_resources(self, dataset_name: str, row_ids: Set[str]) -> Dict[str, Resource]:
        """Create row resources in bulk."""
        row_resources = {}
        
        for row_id in row_ids:
            row_uri = self.generate_row_uri(dataset_name, row_id)
            row_resource, created = Resource.objects.get_or_create(
                uri=row_uri,
                defaults={
                    "resource_type": ResourceType.IRI,
                    "name": f"Row {row_id}",
                    "source": self.institution
                }
            )
            if created:
                self.statistics.increment_resources_created()
            row_resources[row_id] = row_resource
        
        return row_resources
    
    def create_cell_resources_bulk(self, cell_data: List[Tuple[str, str, str]]) -> Dict[str, Resource]:
        """
        Create cell resources in bulk.
        
        Args:
            cell_data: List of (dataset_name, column_name, row_id) tuples
            
        Returns:
            Dictionary mapping cell URIs to resources
        """
        cell_resources_to_create = []
        cell_uri_map = {}
        
        for dataset_name, column_name, row_id in cell_data:
            cell_uri = self.generate_cell_uri(dataset_name, column_name, row_id)
            cell_resource = Resource(
                uri=cell_uri,
                resource_type=ResourceType.IRI,
                source=self.institution,
                name=f"{column_name} Cell"
            )
            cell_resources_to_create.append(cell_resource)
            cell_uri_map[cell_uri] = cell_resource
        
        if cell_resources_to_create:
            Resource.objects.bulk_create(
                cell_resources_to_create,
                ignore_conflicts=True,
                batch_size=500
            )
            self.statistics.increment_resources_created(len(cell_resources_to_create))
        
        # Fetch the created resources with their IDs
        created_resources = Resource.objects.filter(
            uri__in=[res.uri for res in cell_resources_to_create]
        )
        
        return {res.uri: res for res in created_resources}
    
    def create_value_resources_bulk(self, values: List[Tuple[str, str]]) -> Dict[str, Resource]:
        """
        Create literal value resources in bulk.
        
        Args:
            values: List of (value, datatype) tuples
            
        Returns:
            Dictionary mapping values to resources
        """
        value_resources_to_create = []
        value_map = {}
        
        for value, datatype in values:
            if not value or not value.strip():
                continue
                
            # Truncate if necessary
            truncated_value = self._truncate_value_if_needed(value)
            
            value_resource = Resource(
                value=truncated_value,
                resource_type=ResourceType.LITERAL,
                source=self.institution,
                name=truncated_value[:100] if len(truncated_value) > 100 else truncated_value,
                datatype=datatype
            )
            value_resources_to_create.append(value_resource)
            value_map[value] = value_resource
        
        if value_resources_to_create:
            Resource.objects.bulk_create(
                value_resources_to_create,
                ignore_conflicts=True,
                batch_size=500
            )
            self.statistics.increment_resources_created(len(value_resources_to_create))
        
        return value_map
    
    def _truncate_value_if_needed(self, value: str) -> str:
        """Truncate value if it exceeds the maximum size."""
        try:
            original_byte_size = len(value.encode('utf-8'))
            if original_byte_size > MAX_INDEXED_VALUE_SIZE:
                temp_val = value
                while len(temp_val.encode('utf-8')) > MAX_INDEXED_VALUE_SIZE:
                    temp_val = temp_val[:-1]
                truncated_value = temp_val + "..."
                self.statistics.current_metrics.values_truncated += 1
                logger.warning(
                    f"Value truncated: Original byte size: {original_byte_size}, "
                    f"new byte size: {len(truncated_value.encode('utf-8'))}"
                )
                return truncated_value
        except UnicodeEncodeError:
            logger.warning("Could not encode value to check size")
        
        return value
    
    def create_structural_triples_bulk(self, 
                                     dataset_resource: Resource,
                                     column_resources: Dict[str, Resource],
                                     row_resources: Optional[Dict[str, Resource]] = None) -> List[Triple]:
        """
        Create structural triples (dataset→column, dataset→row, etc.).
        
        Args:
            dataset_resource: The dataset resource
            column_resources: Dictionary of column resources
            row_resources: Optional dictionary of row resources
            
        Returns:
            List of created triples
        """
        structural_triples = []
        
        # Dataset → hasPart → Column
        for column_resource in column_resources.values():
            structural_triples.append(
                Triple(subject=dataset_resource, predicate=self.has_part_prop, object=column_resource)
            )
        
        # Dataset → hasPart → Row (if row topology is enabled)
        if row_resources:
            for row_resource in row_resources.values():
                structural_triples.append(
                    Triple(subject=dataset_resource, predicate=self.has_part_prop, object=row_resource)
                )
        
        if structural_triples:
            Triple.objects.bulk_create(structural_triples, ignore_conflicts=True)
            self.statistics.current_metrics.triples_created += len(structural_triples)
        
        return structural_triples
    
    def create_value_triples_bulk(self, cell_value_pairs: List[Tuple[Resource, Resource]]) -> List[Triple]:
        """
        Create value triples (cell→rdf:value→literal).
        
        Args:
            cell_value_pairs: List of (cell_resource, value_resource) tuples
            
        Returns:
            List of created triples
        """
        value_triples = [
            Triple(subject=cell_resource, predicate=self.rdf_value_prop, object=value_resource)
            for cell_resource, value_resource in cell_value_pairs
        ]
        
        if value_triples:
            Triple.objects.bulk_create(value_triples, ignore_conflicts=True)
            self.statistics.current_metrics.triples_created += len(value_triples)
            self.statistics.current_metrics.values_created += len(value_triples)
        
        return value_triples
    
    def get_existing_resources_bulk(self, uris: List[str]) -> Dict[str, Resource]:
        """Efficiently fetch existing resources for a list of URIs."""
        existing = Resource.objects.filter(uri__in=uris).select_related()
        return {resource.uri: resource for resource in existing} 