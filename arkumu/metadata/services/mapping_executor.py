"""
Mapping Executor Service

Transforms CSV data to RDF triples based on mapping definitions.
Focuses on entity-level triples rather than cell-level for efficiency.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from django.db import transaction
from django.utils import timezone

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

logger = logging.getLogger(__name__)


class MappingExecutionStats:
    """Statistics for mapping execution."""
    def __init__(self):
        self.entities_created = 0
        self.entities_updated = 0
        self.triples_created = 0
        self.lookups_resolved = 0
        self.vocabulary_matches = 0
        self.errors = 0
        self.rows_processed = 0
    
    def merge(self, other: 'MappingExecutionStats'):
        """Merge another stats object into this one"""
        self.entities_created += other.entities_created
        self.entities_updated += other.entities_updated
        self.triples_created += other.triples_created
        self.lookups_resolved += other.lookups_resolved
        self.vocabulary_matches += other.vocabulary_matches
        self.errors += other.errors
        self.rows_processed += other.rows_processed


class MappingExecutor:
    """
    Executes mapping definitions to create RDF triples from CSV data.
    """
    
    def __init__(self, base_uri: str = "http://arkumu.org/data"):
        self.base_uri = base_uri
        
    def execute_mapping(self, mapping: Mapping, csv_data: List[Dict[str, Any]]) -> MappingExecutionStats:
        """
        Execute a mapping definition on CSV data.
        
        Args:
            mapping: The mapping definition to execute
            csv_data: List of row dictionaries from CSV
            
        Returns:
            Execution statistics
        """
        if not mapping.is_ready_for_execution():
            raise ValueError(f"Mapping {mapping.name} is not ready for execution")
        
        stats = MappingExecutionStats()
        
        try:
            with transaction.atomic():
                # Execute based on mapping configuration structure
                config = mapping.mapping_config
                
                # Check for entity mapping configuration
                if config.get('subject_column') and config.get('predicate_mappings'):
                    stats = self._execute_entity_mapping(mapping, csv_data)
                
                # Check for lookup mapping configuration  
                if config.get('lookup_config'):
                    lookup_stats = self._execute_lookup_mapping(mapping, csv_data)
                    stats.merge(lookup_stats)
                
                # Check for vocabulary mapping configuration
                if config.get('vocabulary_mappings'):
                    vocab_stats = self._execute_vocabulary_mapping(mapping, csv_data)
                    stats.merge(vocab_stats)
                
                # Check for junction mapping configuration
                if config.get('junction_config'):
                    junction_stats = self._execute_junction_mapping(mapping, csv_data)
                    stats.merge(junction_stats)
                
                # Update mapping execution stats
                mapping.last_executed = timezone.now()
                mapping.execution_stats = {
                    'entities_created': stats.entities_created,
                    'entities_updated': stats.entities_updated,
                    'triples_created': stats.triples_created,
                    'rows_processed': stats.rows_processed,
                    'errors': stats.errors,
                    'executed_at': timezone.now().isoformat()
                }
                mapping.save()
                
        except Exception as e:
            logger.error(f"Error executing mapping {mapping.name}: {e}", exc_info=True)
            stats.errors += 1
            raise
        
        return stats
    
    def _execute_entity_mapping(self, mapping: Mapping, csv_data: List[Dict[str, Any]]) -> MappingExecutionStats:
        """
        Execute Entity Mapping: row cells → entity properties
        
        Creates one entity per row with properties based on column mappings.
        Example:
        Row: {ID: "ART_001", Title: "Mona Lisa", Artist: "Da Vinci"}
        → Entity: <ART_001> dc:title "Mona Lisa"; dc:creator "Da Vinci"
        """
        stats = MappingExecutionStats()
        config = mapping.mapping_config
        
        subject_column = config.get('subject_column')
        predicate_mappings = config.get('predicate_mappings', {})
        base_uri_template = config.get('base_uri_template', '{base_uri}/{organization}/{dataset}/entities/{subject}')
        
        if not subject_column:
            raise ValueError("Entity mapping requires subject_column configuration")
        
        # Get or create properties
        properties = self._get_or_create_properties(predicate_mappings, mapping.organization_id)
        
        for row_num, row in enumerate(csv_data):
            try:
                subject_value = row.get(subject_column)
                if not subject_value:
                    logger.warning(f"No subject value found in row {row_num} for column {subject_column}")
                    continue
                
                # Create entity URI
                # Get primary dataset from source_datasets
                primary_dataset = mapping.source_datasets[0] if mapping.source_datasets else 'unknown'
                
                entity_uri = base_uri_template.format(
                    base_uri=self.base_uri,
                    organization=mapping.organization_id,
                    dataset=primary_dataset,
                    subject=slugify_uri_part(str(subject_value))
                )
                
                # Get or create entity resource
                entity, created = Resource.objects.get_or_create(
                    uri=entity_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'name': str(subject_value),
                        'source': mapping.organization_id
                    }
                )
                
                if created:
                    stats.entities_created += 1
                else:
                    stats.entities_updated += 1
                
                # Create triples for each mapped column
                for column_name, predicate_uri in predicate_mappings.items():
                    if column_name in row and row[column_name]:
                        value = str(row[column_name]).strip()
                        if value:
                            # Create literal resource
                            literal, _ = Resource.objects.get_or_create(
                                resource_type=ResourceType.LITERAL,
                                value=value,
                                datatype="http://www.w3.org/2001/XMLSchema#string",
                                defaults={
                                    'source': mapping.organization_id,
                                    'name': column_name
                                }
                            )
                            
                            # Create triple
                            property_resource = properties.get(predicate_uri)
                            if property_resource:
                                triple, created = Triple.objects.get_or_create(
                                    subject=entity,
                                    predicate=property_resource,
                                    object=literal
                                )
                                if created:
                                    stats.triples_created += 1
                
                # Add provenance triple linking to mapping
                mapping_uri = f"{self.base_uri}/mappings/{mapping.id}"
                mapping_resource, _ = Resource.objects.get_or_create(
                    uri=mapping_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'name': f"Mapping: {mapping.name}",
                        'source': mapping.organization_id
                    }
                )
                
                provenance_prop, _ = Resource.objects.get_or_create(
                    uri="http://www.w3.org/ns/prov#wasGeneratedBy",
                    defaults={
                        'resource_type': ResourceType.PROPERTY,
                        'name': "wasGeneratedBy",
                        'source': mapping.organization_id
                    }
                )
                
                Triple.objects.get_or_create(
                    subject=entity,
                    predicate=provenance_prop,
                    object=mapping_resource
                )
                
                stats.rows_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing row {row_num} in entity mapping: {e}")
                stats.errors += 1
        
        return stats
    
    def _execute_lookup_mapping(self, mapping: Mapping, csv_data: List[Dict[str, Any]]) -> MappingExecutionStats:
        """
        Execute Lookup Mapping: FK values → entity references
        
        Example from 02_Kreuz_Projekte_Personen.csv:
        Row: {AS_Pers_ID: "417", AS_Proj_ID: "2265", AS_Taetigkeit: "AutorIn"}
        → <Person_417> <hasRoleInProject> <Project_2265>
        → <Project_2265> <hasParticipant> <Person_417>
        """
        stats = MappingExecutionStats()
        config = mapping.mapping_config.get('lookup_config', {})
        
        source_column = config.get('source_column')  # e.g., "AS_Pers_ID"
        target_column = config.get('target_column')  # e.g., "AS_Proj_ID"
        source_dataset = config.get('source_dataset')  # e.g., "Personen"
        target_dataset = config.get('target_dataset')  # e.g., "Projekte"
        relationship_property = config.get('relationship_property')  # e.g., "hasParticipant"
        
        if not all([source_column, target_column, source_dataset, target_dataset, relationship_property]):
            raise ValueError("Lookup mapping requires complete configuration")
        
        # Get or create relationship property
        prop_resource, _ = Resource.objects.get_or_create(
            uri=relationship_property,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'name': relationship_property.split('/')[-1] if '/' in relationship_property else relationship_property,
                'source': mapping.organization_id
            }
        )
        
        for row_num, row in enumerate(csv_data):
            try:
                source_id = row.get(source_column)
                target_id = row.get(target_column)
                
                if not source_id or not target_id:
                    continue
                
                # Create URIs for referenced entities
                source_uri = f"{self.base_uri}/{mapping.organization_id}/{source_dataset}/entities/{slugify_uri_part(str(source_id))}"
                target_uri = f"{self.base_uri}/{mapping.organization_id}/{target_dataset}/entities/{slugify_uri_part(str(target_id))}"
                
                # Get or create entity resources (they should exist from entity mappings)
                source_entity, _ = Resource.objects.get_or_create(
                    uri=source_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'name': f"{source_dataset}_{source_id}",
                        'source': mapping.organization_id
                    }
                )
                
                target_entity, _ = Resource.objects.get_or_create(
                    uri=target_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'name': f"{target_dataset}_{target_id}",
                        'source': mapping.organization_id
                    }
                )
                
                # Create relationship triple
                triple, created = Triple.objects.get_or_create(
                    subject=target_entity,
                    predicate=prop_resource,
                    object=source_entity
                )
                
                if created:
                    stats.triples_created += 1
                    stats.lookups_resolved += 1
                
                stats.rows_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing row {row_num} in lookup mapping: {e}")
                stats.errors += 1
        
        return stats
    
    def _execute_vocabulary_mapping(self, mapping: Mapping, csv_data: List[Dict[str, Any]]) -> MappingExecutionStats:
        """
        Execute Vocabulary Mapping: multi-value fields → controlled terms
        
        Example:
        Cell: "archaeology, history, art" 
        → Split to ["archaeology", "history", "art"]
        → Match each to vocabulary terms
        → Create triples linking to vocabulary URIs
        """
        stats = MappingExecutionStats()
        # TODO: Implement vocabulary mapping
        return stats
    
    def _execute_junction_mapping(self, mapping: Mapping, csv_data: List[Dict[str, Any]]) -> MappingExecutionStats:
        """
        Execute Junction Mapping: junction tables → relationships with attributes
        
        Similar to lookup but can include role/attribute information
        """
        stats = MappingExecutionStats()
        # TODO: Implement junction mapping (extension of lookup mapping)
        return stats
    
    def _get_or_create_properties(self, predicate_mappings: Dict[str, str], organization_id: str) -> Dict[str, Resource]:
        """Get or create property resources for predicate mappings."""
        properties = {}
        
        for column_name, predicate_uri in predicate_mappings.items():
            prop_resource, _ = Resource.objects.get_or_create(
                uri=predicate_uri,
                defaults={
                    'resource_type': ResourceType.PROPERTY,
                    'name': predicate_uri.split('/')[-1] if '/' in predicate_uri else predicate_uri,
                    'source': organization_id
                }
            )
            properties[predicate_uri] = prop_resource
        
        return properties 