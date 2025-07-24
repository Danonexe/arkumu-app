from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from arkumu.metadata.models import Mapping
import graphviz
from django.utils.html import format_html
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def convert_mapping_config_to_schema_data(workspace_datasets, workspace_columns, fk_relationships, relationship_contexts):
    """Convert mapping configuration to schema visualization format."""
    nodes = []
    edges = []
    
    # Process datasets to create nodes
    for ds in workspace_datasets:
        if isinstance(ds, str):
            # Handle older format
            dataset_id = ds
            dataset_name = ds
            entity_type = 'Entity'
            
            # Extract columns for this dataset
            columns = []
            anchor_columns = []
            multi_value_columns = []
            external_ontologies = []
            
            prefix = None
            for col_key in workspace_columns.keys():
                if f"::{dataset_id}::" in col_key:
                    prefix = col_key.split("::")[0]
                    break
            
            if prefix:
                for col_key, col_config in workspace_columns.items():
                    if col_key.startswith(f"{prefix}::{dataset_id}::"):
                        col_name = col_key.split("::", 2)[2]
                        columns.append(col_name)
                        
                        if col_config.get('is_anchor', False):
                            anchor_columns.append(col_name)
                        if col_config.get('is_multi_value', False):
                            multi_value_columns.append(col_name)
                        if col_config.get('is_external_ontology', False) or col_config.get('external_ontologies'):
                            external_ontologies.append(col_name)
        else:
            # Handle newer format
            dataset_id = ds['id']
            dataset_name = ds['name']
            entity_type = ds.get('entity_type', 'Entity')
            
            if entity_type.startswith('http'):
                entity_type = entity_type.split('/')[-1]
            
            columns = []
            anchor_columns = []
            multi_value_columns = []
            external_ontologies = []
            
            for col in ds.get('columns', []):
                col_name = col['name']
                columns.append(col_name)
                
                if col.get('anchor', False):
                    anchor_columns.append(col_name)
                if col.get('is_multi_value', False):
                    multi_value_columns.append(col_name)
                if col.get('is_external_ontology', False) or col.get('external_ontologies'):
                    external_ontologies.append(col_name)
        
        # Check if this is a junction table (has relationship context)
        is_junction = any(
            ctx_key.split('::')[1] == dataset_id if len(ctx_key.split('::')) >= 2 else False
            for ctx_key in relationship_contexts.keys()
        )
        
        node = {
            'id': dataset_id,
            'label': dataset_name,
            'type': 'dataset',
            'entity_type': entity_type,
            'properties': columns,
            'is_junction': is_junction,
            'anchor_columns': anchor_columns,
            'multi_value_columns': multi_value_columns,
            'external_ontologies': external_ontologies
        }
        nodes.append(node)
    
    # Process FK relationships to create edges
    if isinstance(fk_relationships, dict):
        for rel_id, rel in fk_relationships.items():
            key_parts = rel_id.split('::')
            source_id = key_parts[1] if len(key_parts) >= 2 else rel.get('source_dataset', rel.get('source_dataset_id', ''))
            target_id = rel.get('target_dataset', rel.get('target_dataset_id', ''))
            source_column = key_parts[2] if len(key_parts) >= 3 else rel.get('source_column', 'relates to')
            
            target_columns = rel.get('target_columns', [])
            target_column = target_columns[0] if target_columns else None
            
            edge = {
                'source': source_id,
                'target': target_id,
                'relationship_type': 'foreign_key',
                'source_column': source_column,
                'target_column': target_column,
                'type': 'foreign_key'
            }
            edges.append(edge)
    else:
        # Handle list format
        for rel in fk_relationships:
            source_id = rel.get('source_dataset_id', rel.get('source_dataset', ''))
            target_id = rel.get('target_dataset_id', rel.get('target_dataset', ''))
            source_column = rel.get('source_column', 'relates to')
            
            target_columns = rel.get('target_columns', [])
            target_column = target_columns[0] if target_columns else None
            
            edge = {
                'source': source_id,
                'target': target_id,
                'relationship_type': 'foreign_key',
                'source_column': source_column,
                'target_column': target_column,
                'type': 'foreign_key'
            }
            edges.append(edge)
    
    # Process relationship contexts for junction relationships
    for ctx_key, ctx_config in relationship_contexts.items():
        key_parts = ctx_key.split('::')
        if len(key_parts) >= 3:
            dataset_id = key_parts[1]
            context_column = key_parts[2]
            
            primary_fk_dataset = ctx_config.get('primary_fk_dataset')
            secondary_fk_dataset = ctx_config.get('secondary_fk_dataset')
            primary_fk_column = ctx_config.get('primary_fk_column')
            secondary_fk_column = ctx_config.get('secondary_fk_column')
            
            # Add junction edges
            if primary_fk_dataset:
                edges.append({
                    'source': dataset_id,
                    'target': primary_fk_dataset,
                    'relationship_type': 'junction_primary',
                    'source_column': primary_fk_column,
                    'type': 'junction'
                })
            
            if secondary_fk_dataset:
                edges.append({
                    'source': dataset_id,
                    'target': secondary_fk_dataset,
                    'relationship_type': 'junction_secondary',
                    'source_column': secondary_fk_column,
                    'type': 'junction'
                })
    
    return {
        'nodes': nodes,
        'edges': edges,
        'metadata': {
            'total_datasets': len(nodes),
            'total_relationships': len(edges),
            'junction_tables': sum(1 for n in nodes if n['is_junction']),
            'generated_at': datetime.now().isoformat()
        }
    }


@login_required
def blueprint_visualizer_graphviz(request, mapping_id):
    """Display the blueprint/schema structure using Graphviz (server-side rendering)."""
    mapping = get_object_or_404(Mapping, pk=mapping_id)
    
    try:
        # Extract schema information directly from mapping_config
        mapping_config = mapping.mapping_config
        workspace_datasets = mapping_config.get('workspace_datasets', [])
        workspace_columns = mapping_config.get('workspace_columns', {})
        fk_relationships = mapping_config.get('fk_relationships', {})
        relationship_contexts = mapping_config.get('relationship_contexts', {})
        
        # Convert mapping config to schema visualization format
        schema_data = convert_mapping_config_to_schema_data(
            workspace_datasets, workspace_columns, fk_relationships, relationship_contexts
        )
        
        # Create a directed graph
        dot = graphviz.Digraph(
            name='Blueprint',
            comment=f'Blueprint/Schema structure for {mapping.name}',
            engine='dot',  # Use hierarchical layout
            format='svg',
            graph_attr={
                'rankdir': 'TB',  # Top to bottom
                'splines': 'ortho',  # Right-angle edges
                'nodesep': '0.8',
                'ranksep': '1.2',
                'bgcolor': 'transparent',
                'fontname': 'Arial',
            },
            node_attr={
                'fontname': 'Arial',
                'fontsize': '12', 
                'style': 'filled,rounded',
                'shape': 'box',
                'margin': '0.3,0.1',
            },
            edge_attr={
                'fontname': 'Arial',
                'fontsize': '10',
                'arrowsize': '0.8',
            }
        )
        
        # Color schemes for different node types
        colors = {
            'dataset': {'fillcolor': '#e0f2fe', 'color': '#0369a1', 'fontcolor': '#0c4a6e'},
            'junction': {'fillcolor': '#fef3c7', 'color': '#d97706', 'fontcolor': '#92400e'},
            'entity': {'fillcolor': '#dcfce7', 'color': '#16a34a', 'fontcolor': '#15803d'},
        }
        
        # Create nodes for each dataset/entity
        for node in schema_data.get('nodes', []):
            dataset_name = node['id']
            entity_type = node.get('entity_type', 'Entity')
            properties = node.get('properties', [])
            is_junction = node.get('is_junction', False)
            anchor_columns = node.get('anchor_columns', [])
            multi_value_columns = node.get('multi_value_columns', [])
            external_ontologies = node.get('external_ontologies', [])
            
            # Determine node style
            if is_junction:
                style = colors['junction']
            else:
                style = colors['dataset']
            
            # Build node label with HTML-like formatting
            rows = []
            
            # Header with dataset name and entity type
            rows.append(f'<TR><TD COLSPAN="2" BGCOLOR="#f8fafc"><B>{dataset_name}</B><BR/><FONT POINT-SIZE="10">{entity_type}</FONT></TD></TR>')
            
            # Add properties/columns
            if properties:
                for prop in sorted(properties):
                    attributes = []
                    
                    # Mark special column types
                    if prop in anchor_columns:
                        attributes.append('⚓')  # Anchor
                    if prop in multi_value_columns:
                        attributes.append('📚')  # Multi-value
                    if prop in external_ontologies:
                        attributes.append('🌐')  # External ontology
                    
                    attr_str = ' '.join(attributes) if attributes else ''
                    port_name = ''.join(c if c.isalnum() else '_' for c in prop)[:63]
                    if not port_name or port_name[0].isdigit():
                        port_name = f"prop_{port_name}"
                    
                    rows.append(f'<TR><TD PORT="{port_name}" ALIGN="LEFT">{prop}</TD><TD ALIGN="RIGHT">{attr_str}</TD></TR>')
            else:
                rows.append('<TR><TD COLSPAN="2"><I>No properties</I></TD></TR>')
            
            label = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="2">{''.join(rows)}</TABLE>>"""
            
            # Add node with styling
            dot.node(dataset_name, label, **style)
        
        # Create edges for relationships
        for edge in schema_data.get('edges', []):
            source = edge['source']
            target = edge['target']
            edge_type = edge.get('type', 'relationship')
            relationship_type = edge.get('relationship_type', '')
            source_column = edge.get('source_column', '')
            target_column = edge.get('target_column', '')
            
            # Style edges based on type
            if edge_type == 'foreign_key':
                edge_style = 'solid'
                edge_color = '#059669'  # Green for FK relationships
                label = f"{source_column} → {target_column}" if target_column else source_column
            elif edge_type == 'junction':
                edge_style = 'dashed'
                edge_color = '#dc2626'  # Red for junction relationships
                label = f"{relationship_type}: {source_column}"
            else:
                edge_style = 'dotted'
                edge_color = '#6b7280'  # Gray for other relationships
                label = relationship_type
            
            # Create safe port names for precise connections
            source_port = None
            target_port = None
            
            if source_column:
                source_port = ''.join(c if c.isalnum() else '_' for c in source_column)[:63]
                if not source_port or source_port[0].isdigit():
                    source_port = f"prop_{source_port}"
            
            if target_column:
                target_port = ''.join(c if c.isalnum() else '_' for c in target_column)[:63]
                if not target_port or target_port[0].isdigit():
                    target_port = f"prop_{target_port}"
            
            # Build source and target node references
            source_node = f"{source}:{source_port}" if source_port else source
            target_node = f"{target}:{target_port}" if target_port else target
            
            dot.edge(
                source_node,
                target_node,
                label=label,
                color=edge_color,
                fontcolor='#475569',
                style=edge_style,
                arrowhead='normal',
                penwidth='2'
            )
        
        # Render to SVG
        svg_content = dot.pipe(format='svg').decode('utf-8')
        
        # Remove XML declaration to embed in HTML
        if svg_content.startswith('<?xml'):
            svg_content = svg_content.split('\n', 1)[1]
        
        # Add CSS for interactive features
        svg_with_style = f"""
        <style>
            .blueprint-container {{
                position: relative;
                width: 100%;
                height: 100%;
                overflow: auto;
                background: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                cursor: grab;
            }}
            .blueprint-container:active {{
                cursor: grabbing;
            }}
            .blueprint-container svg {{
                width: 100%;
                height: 100%;
                object-fit: contain;
                max-width: none !important;
                max-height: none !important;
            }}
            .node {{
                cursor: pointer;
                transition: opacity 0.2s;
            }}
            .node:hover {{
                opacity: 0.8;
            }}
        </style>
        <div class="blueprint-container">
            {svg_content}
        </div>
        """
        
        graph_svg = svg_with_style
        error = None
        
        # Debug info
        metadata = schema_data.get('metadata', {})
        debug_info = {
            'total_datasets': metadata.get('total_datasets', 0),
            'total_relationships': metadata.get('total_relationships', 0),
            'junction_tables': metadata.get('junction_tables', 0),
            'generated_at': metadata.get('generated_at', 'Unknown')
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating blueprint visualization: {e}")
        logger.error(traceback.format_exc())
        graph_svg = None
        error = f"Error generating blueprint visualization: {str(e)}"
        debug_info = None
    
    context = {
        'mapping': mapping,
        'graph_svg': graph_svg,
        'error': error,
        'debug_info': debug_info,
    }
    
    return render(request, 'metadata/blueprint_visualizer_graphviz.html', context)