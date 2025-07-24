from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from arkumu.metadata.models import Mapping
from arkumu.importer.services.schema_service import SchemaService
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def convert_schema_data_to_blueprint(schema_data, schema_service):
    """Convert SchemaService visualization data to blueprint format for RDF generation."""
    blueprint = {
        'organization': 'arkumu',
        'entities': {},
        'relationships': {},
        'junctions': {}
    }
    
    # Convert nodes to entities
    for node in schema_data.get('nodes', []):
        entity_key = node['id']
        properties = {}
        
        # Get detailed property information for this dataset
        dataset_properties = schema_service.get_dataset_properties(entity_key)
        relationship_info = schema_service.get_relationship_info(entity_key)
        
        # Build properties from schema
        for prop_name in node.get('properties', []):
            prop_metadata = dataset_properties.get(prop_name, {})
            properties[prop_name] = {
                'property_uri': f"http://data.arkumu.org/arkumu/properties/{prop_name}",
                'source_column': prop_name,
                'data_type': prop_metadata.get('data_type', 'string'),
                'is_anchor': prop_metadata.get('is_anchor', False),
                'is_multi_value': prop_name in relationship_info.get('multi_value_columns', []),
                'external_ontology': prop_metadata.get('external_ontology')
            }
        
        blueprint['entities'][entity_key] = {
            'entity_type': node.get('entity_type', 'Entity'),
            'properties': properties,
            'anchor_columns': [p for p, meta in properties.items() if meta.get('is_anchor')],
            'is_junction': node.get('is_junction', False)
        }
    
    # Convert edges to relationships
    for edge in schema_data.get('edges', []):
        rel_key = f"{edge['source']}_to_{edge['target']}"
        blueprint['relationships'][rel_key] = {
            'source_entity': edge['source'],
            'target_entity': edge['target'],
            'relationship_type': edge.get('relationship_type', 'relatedTo'),
            'edge_type': edge.get('type', 'relationship')
        }
    
    # Handle junctions
    for entity_key, entity_info in blueprint['entities'].items():
        if entity_info.get('is_junction'):
            # Find junction relationships
            junction_edges = [e for e in schema_data.get('edges', []) if e['source'] == entity_key]
            if len(junction_edges) >= 2:
                blueprint['junctions'][entity_key] = {
                    'primary_entity': junction_edges[0]['target'],
                    'secondary_entity': junction_edges[1]['target'],
                    'context_attributes': [p for p in entity_info['properties'].keys() 
                                         if not entity_info['properties'][p].get('is_anchor')]
                }
    
    return blueprint


def generate_sample_rdf_triples(blueprint, sample_limit=5):
    """Generate sample RDF triples based on blueprint structure."""
    triples = []
    
    # Get organization from blueprint
    org_name = blueprint.get('organization', 'org')
    
    for entity_key, entity_config in blueprint.get('entities', {}).items():
        entity_type = entity_config.get('entity_type', 'Entity')
        properties = entity_config.get('properties', {})
        
        # Generate sample entity instances
        for i in range(min(sample_limit, 3)):  # Limit sample instances
            # Generate sample entity URI
            sample_id = f"sample_{i+1}"
            entity_uri = f"http://data.arkumu.org/{org_name}/entities/{entity_key}/{sample_id}"
            
            # Type triple
            triples.append({
                'subject': f"<{entity_uri}>",
                'predicate': 'rdf:type',
                'object': f"<{entity_type}>",
                'category': 'type'
            })
            
            # Property triples
            for prop_name, prop_config in properties.items():
                prop_uri = prop_config.get('property_uri', f"http://data.arkumu.org/{org_name}/properties/{prop_name}")
                
                # Generate sample values based on property type
                if 'external_ontology' in prop_config:
                    sample_value = f'"Sample {prop_name.title()} {i+1}"'
                elif prop_name.lower() in ['id', 'identifier']:
                    sample_value = f'"{sample_id}"'
                elif prop_name.lower() in ['name', 'title', 'label']:
                    sample_value = f'"Sample {entity_key} {i+1}"'
                elif prop_name.lower() in ['email']:
                    sample_value = f'"sample{i+1}@example.com"'
                elif prop_name.lower() in ['age', 'count', 'year']:
                    sample_value = f'"{20 + i*5}"^^xsd:integer'
                elif prop_name.lower() in ['date', 'created', 'updated']:
                    sample_value = f'"2024-01-{i+1:02d}"^^xsd:date'
                else:
                    sample_value = f'"Sample {prop_name} value {i+1}"'
                
                triples.append({
                    'subject': f"<{entity_uri}>",
                    'predicate': f"<{prop_uri}>",
                    'object': sample_value,
                    'category': 'property',
                    'source_column': prop_config.get('source_column', prop_name)
                })
    
    # Generate relationship triples
    relationships = blueprint.get('relationships', {})
    entity_keys = list(blueprint.get('entities', {}).keys())
    
    if len(entity_keys) >= 2:
        for rel_key, rel_config in relationships.items():
            source_entity = rel_config.get('source_entity')
            target_entity = rel_config.get('target_entity')
            relationship_type = rel_config.get('relationship_type', 'relatedTo')
            
            if source_entity and target_entity:
                # Generate sample relationship triples
                for i in range(min(sample_limit, 2)):
                    source_uri = f"http://data.arkumu.org/{org_name}/entities/{source_entity}/sample_{i+1}"
                    target_uri = f"http://data.arkumu.org/{org_name}/entities/{target_entity}/sample_{i+1}"
                    
                    triples.append({
                        'subject': f"<{source_uri}>",
                        'predicate': f"<http://data.arkumu.org/{org_name}/properties/{relationship_type}>",
                        'object': f"<{target_uri}>",
                        'category': 'relationship',
                        'relationship_type': relationship_type
                    })
    
    # Generate junction triples if present
    junctions = blueprint.get('junctions', {})
    for junction_key, junction_config in junctions.items():
        primary_entity = junction_config.get('primary_entity')
        secondary_entity = junction_config.get('secondary_entity')
        context_attributes = junction_config.get('context_attributes', [])
        
        if primary_entity and secondary_entity:
            # Generate sample junction entity
            junction_uri = f"http://data.arkumu.org/{org_name}/junctions/{junction_key}/sample_1"
            
            # Junction type triple
            triples.append({
                'subject': f"<{junction_uri}>",
                'predicate': 'rdf:type',
                'object': f"<http://data.arkumu.org/{org_name}/types/{junction_key}>",
                'category': 'junction_type'
            })
            
            # Junction relationship triples
            primary_uri = f"http://data.arkumu.org/{org_name}/entities/{primary_entity}/sample_1"
            secondary_uri = f"http://data.arkumu.org/{org_name}/entities/{secondary_entity}/sample_1"
            
            triples.append({
                'subject': f"<{junction_uri}>",
                'predicate': f"<http://data.arkumu.org/{org_name}/properties/primaryEntity>",
                'object': f"<{primary_uri}>",
                'category': 'junction_relationship'
            })
            
            triples.append({
                'subject': f"<{junction_uri}>",
                'predicate': f"<http://data.arkumu.org/{org_name}/properties/secondaryEntity>",
                'object': f"<{secondary_uri}>",
                'category': 'junction_relationship'
            })
            
            # Context attribute triples
            for attr in context_attributes:
                attr_uri = f"http://data.arkumu.org/{org_name}/properties/{attr}"
                triples.append({
                    'subject': f"<{junction_uri}>",
                    'predicate': f"<{attr_uri}>",
                    'object': f'"Sample {attr} value"',
                    'category': 'junction_context',
                    'context_attribute': attr
                })
    
    return triples


def generate_uri_patterns(blueprint):
    """Generate URI generation patterns from blueprint."""
    patterns = {}
    org_name = blueprint.get('organization', 'org')
    
    # Entity URI patterns
    patterns['entities'] = {}
    for entity_key, entity_config in blueprint.get('entities', {}).items():
        patterns['entities'][entity_key] = {
            'pattern': f"http://data.arkumu.org/{org_name}/entities/{entity_key}/{{anchor_value}}",
            'example': f"http://data.arkumu.org/{org_name}/entities/{entity_key}/john_doe_123",
            'anchor_columns': entity_config.get('anchor_columns', [])
        }
    
    # Property URI patterns
    patterns['properties'] = {}
    for entity_key, entity_config in blueprint.get('entities', {}).items():
        for prop_name, prop_config in entity_config.get('properties', {}).items():
            prop_uri = prop_config.get('property_uri', f"http://data.arkumu.org/{org_name}/properties/{prop_name}")
            patterns['properties'][prop_name] = {
                'uri': prop_uri,
                'source_column': prop_config.get('source_column', prop_name),
                'external_ontology': prop_config.get('external_ontology')
            }
    
    # Dataset URI patterns
    patterns['datasets'] = {}
    for entity_key in blueprint.get('entities', {}).keys():
        patterns['datasets'][entity_key] = f"http://data.arkumu.org/{org_name}/datasets/{entity_key}"
    
    # Junction URI patterns
    patterns['junctions'] = {}
    for junction_key, junction_config in blueprint.get('junctions', {}).items():
        primary_entity = junction_config.get('primary_entity')
        secondary_entity = junction_config.get('secondary_entity')
        patterns['junctions'][junction_key] = {
            'pattern': f"http://data.arkumu.org/{org_name}/junctions/{junction_key}/{{primary_id}}_{{secondary_id}}",
            'example': f"http://data.arkumu.org/{org_name}/junctions/{junction_key}/john_123_acme",
            'primary_entity': primary_entity,
            'secondary_entity': secondary_entity,
            'context_attributes': junction_config.get('context_attributes', [])
        }
    
    return patterns


def generate_property_mappings(blueprint):
    """Generate property mapping table from blueprint."""
    mappings = []
    
    for entity_key, entity_config in blueprint.get('entities', {}).items():
        for prop_name, prop_config in entity_config.get('properties', {}).items():
            mapping = {
                'entity': entity_key,
                'source_column': prop_config.get('source_column', prop_name),
                'rdf_property': prop_config.get('property_uri', f"arkumu:{prop_name}"),
                'data_type': prop_config.get('data_type', 'string'),
                'is_anchor': prop_config.get('is_anchor', False),
                'is_multi_value': prop_config.get('is_multi_value', False),
                'external_ontology': prop_config.get('external_ontology')
            }
            mappings.append(mapping)
    
    return mappings


@login_required
def rdf_preview_visualizer(request, mapping_id):
    """Display the RDF preview showing sample triples and URI patterns."""
    mapping = get_object_or_404(Mapping, pk=mapping_id)
    
    try:
        # Generate schema data using SchemaService
        schema_service = SchemaService(mapping_id=str(mapping.id))
        schema_data = schema_service.get_schema_visualization_data()
        
        # Convert schema data to blueprint format for our RDF generation
        blueprint = convert_schema_data_to_blueprint(schema_data, schema_service)
        
        # Generate RDF preview components
        sample_triples = generate_sample_rdf_triples(blueprint)
        uri_patterns = generate_uri_patterns(blueprint)
        property_mappings = generate_property_mappings(blueprint)
        
        # Organize triples by category for better display
        triples_by_category = {}
        for triple in sample_triples:
            category = triple.get('category', 'other')
            if category not in triples_by_category:
                triples_by_category[category] = []
            triples_by_category[category].append(triple)
        
        # Generate summary statistics
        stats = {
            'total_entities': len(schema_data.get('nodes', [])),
            'total_properties': sum(len(node.get('properties', [])) for node in schema_data.get('nodes', [])),
            'total_relationships': len(schema_data.get('edges', [])),
            'total_junctions': sum(1 for node in schema_data.get('nodes', []) if node.get('is_junction', False)),
            'total_triples': len(sample_triples)
        }
        
        context = {
            'mapping': mapping,
            'blueprint': blueprint,
            'sample_triples': sample_triples,
            'triples_by_category': triples_by_category,
            'uri_patterns': uri_patterns,
            'property_mappings': property_mappings,
            'stats': stats,
            'error': None
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating RDF preview: {e}")
        logger.error(traceback.format_exc())
        
        context = {
            'mapping': mapping,
            'blueprint': None,
            'sample_triples': [],
            'triples_by_category': {},
            'uri_patterns': {},
            'property_mappings': [],
            'stats': {},
            'error': f"Error generating RDF preview: {str(e)}"
        }
    
    return render(request, 'metadata/rdf_preview_visualizer.html', context)