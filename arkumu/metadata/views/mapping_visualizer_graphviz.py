from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from arkumu.metadata.models import Mapping
import graphviz
from django.utils.html import format_html


@login_required
def mapping_visualizer_graphviz(request, mapping_id):
    """Display the mapping structure using Graphviz (server-side rendering)."""
    mapping = get_object_or_404(Mapping, pk=mapping_id)
    
    # Create a directed graph
    dot = graphviz.Digraph(
        name='Mapping',
        comment=f'Mapping structure for {mapping.name}',
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
    
    # Extract datasets from mapping config
    workspace_datasets = mapping.mapping_config.get('workspace_datasets', [])
    workspace_columns = mapping.mapping_config.get('workspace_columns', {})
    relationship_contexts = mapping.mapping_config.get('relationship_contexts', {})
    
    # Color schemes for different entity types
    entity_colors = {
        'person': {'fillcolor': '#dbeafe', 'color': '#3b82f6', 'fontcolor': '#1e40af'},
        'document': {'fillcolor': '#ecfdf5', 'color': '#10b981', 'fontcolor': '#065f46'},
        'organization': {'fillcolor': '#fef3c7', 'color': '#f59e0b', 'fontcolor': '#92400e'},
        'default': {'fillcolor': '#dbeafe', 'color': '#3b82f6', 'fontcolor': '#1e40af'},
    }
    
    # Track node IDs for relationships and column information
    node_mapping = {}
    node_columns = {}  # Track columns for each dataset to help with FK targeting
    
    # Helper function to get relationship context info for a column
    def get_relationship_context_info(dataset_name, column_name, relationship_contexts):
        """Get relationship context info for a column if it exists."""
        for ctx_key, ctx_config in relationship_contexts.items():
            # Context key format: prefix::dataset::column
            key_parts = ctx_key.split('::')
            if len(key_parts) >= 3:
                ctx_dataset = key_parts[1]
                ctx_column = key_parts[2]
                if ctx_dataset == dataset_name and ctx_column == column_name:
                    return ctx_config.get('context_predicate', 'Context')
        return None
    
    for ds in workspace_datasets:
        if isinstance(ds, str):
            # Handle older format
            dataset_id = ds
            dataset_name = ds
            entity_type = 'Entity'
            
            # Extract columns
            columns = []
            prefix = None
            for col_key in workspace_columns.keys():
                if f"::{dataset_id}::" in col_key:
                    prefix = col_key.split("::")[0]
                    break
            
            if prefix:
                for col_key, col_config in workspace_columns.items():
                    if col_key.startswith(f"{prefix}::{dataset_id}::"):
                        col_name = col_key.split("::", 2)[2]
                        columns.append({
                            'name': col_name,
                            'type': col_config.get('type', 'text'),
                            'is_anchor': col_config.get('is_anchor', False),
                            'is_fk': col_config.get('is_fk', False),
                            'is_multi_value': col_config.get('is_multi_value', False),
                            'is_external_ontology': col_config.get('is_external_ontology', False),
                            'external_ontologies': col_config.get('external_ontologies', []),
                            'added_at': col_config.get('added_at', '0000-00-00T00:00:00'),
                        })
        else:
            # Handle newer format
            dataset_id = ds['id']
            dataset_name = ds['name']
            entity_type = ds.get('entity_type', 'Entity')
            
            if entity_type.startswith('http'):
                entity_type = entity_type.split('/')[-1]
            
            columns = []
            for col in ds.get('columns', []):
                columns.append({
                    'name': col['name'],
                    'type': col.get('arkumu_type', 'text'),
                    'is_anchor': col.get('anchor', False),
                    'is_fk': col.get('is_fk', False),
                    'is_multi_value': col.get('is_multi_value', False),
                    'is_external_ontology': col.get('is_external_ontology', False),
                    'external_ontologies': col.get('external_ontologies', []),
                    'added_at': col.get('added_at', '0000-00-00T00:00:00'),
                })
        
        # Create a simple node ID
        node_id = f"node_{len(node_mapping)}"
        node_mapping[dataset_id] = node_id
        
        # Store column information for FK targeting
        node_columns[dataset_id] = {
            'columns': columns,
            'anchor_column': next((col['name'] for col in columns if col.get('is_anchor')), None)
        }
        
        # Determine node style based on entity type
        entity_key = entity_type.lower()
        if entity_key in ['person', 'people', 'author', 'creator']:
            style = entity_colors['person']
        elif entity_key in ['document', 'file', 'paper', 'book']:
            style = entity_colors['document']
        elif entity_key in ['organization', 'institution', 'company']:
            style = entity_colors['organization']
        else:
            style = entity_colors['default']
        
        # Build node label with HTML-like formatting showing column details
        # Start with dataset name header
        rows = [f'<TR><TD COLSPAN="2" BGCOLOR="#f0f0f0"><B>{dataset_name}</B></TD></TR>']
        
        # Sort columns by their added_at timestamp to maintain mapping order
        sorted_columns = sorted(columns, key=lambda col: col.get('added_at', '0000-00-00T00:00:00'))
        
        # Add column details - show all columns with port identifiers
        for col in sorted_columns:
            col_name = col.get('name', '')
            attributes = []
            
            # Check column attributes
            if col.get('is_anchor'):
                attributes.append('⚓')
            if col.get('is_fk'):
                attributes.append('🔗')
            if col.get('is_multi_value'):
                attributes.append('📚')
            if col.get('is_external_ontology') or col.get('external_ontologies'):
                attributes.append('🌐')
            
            # Check for relationship context and add the context predicate name
            context_predicate = get_relationship_context_info(dataset_name, col_name, relationship_contexts)
            if context_predicate:
                attributes.append(f'📝{context_predicate}')
                
            # Format column row with port identifier for precise edge targeting
            attr_str = ' '.join(attributes) if attributes else ''
            # Create a safe port name by replacing all problematic characters
            port_name = ''.join(c if c.isalnum() else '_' for c in col_name)[:63]  # Limit to 63 chars and use only alphanumeric + underscore
            if not port_name or port_name[0].isdigit():  # Ensure it starts with letter or underscore
                port_name = f"col_{port_name}"
            rows.append(f'<TR><TD PORT="{port_name}" ALIGN="LEFT">{col_name}</TD><TD ALIGN="RIGHT">{attr_str}</TD></TR>')
        
        label = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="2">{''.join(rows)}</TABLE>>"""
        
        # Add node with styling
        dot.node(node_id, label, **style)
    
    # Get FK relationships data
    fk_relationships = mapping.mapping_config.get('fk_relationships', {})
    
    # Debug: Track relationship counts
    relationship_count = 0
    missing_source_count = 0
    missing_target_count = 0
    
    if isinstance(fk_relationships, dict):
        for rel_id, rel in fk_relationships.items():
            # Extract source dataset from the key format: prefix::source_dataset::column
            key_parts = rel_id.split('::')
            source_id = key_parts[1] if len(key_parts) >= 2 else rel.get('source_dataset', rel.get('source_dataset_id', ''))
            target_id = rel.get('target_dataset', rel.get('target_dataset_id', ''))
            source_column = key_parts[2] if len(key_parts) >= 3 else rel.get('source_column', 'relates to')
            
            # Get target column information
            target_columns = rel.get('target_columns', [])
            target_column = target_columns[0] if target_columns else None
            
            if source_id in node_mapping and target_id in node_mapping:
                # Create safe port names using same logic as node creation
                source_port = ''.join(c if c.isalnum() else '_' for c in source_column)[:63]
                if not source_port or source_port[0].isdigit():
                    source_port = f"col_{source_port}"
                
                # Build source and target node references with ports
                source_node = f"{node_mapping[source_id]}:{source_port}"
                target_node = node_mapping[target_id]
                
                # Determine target connection strategy
                connection_type = "node_to_node"  # Default
                edge_style = "dashed"  # Default for imprecise connections
                edge_color = "#16a34a"  # Green for imprecise FK connections
                
                if target_column:
                    # Precise column-to-column connection
                    target_port = ''.join(c if c.isalnum() else '_' for c in target_column)[:63]
                    if not target_port or target_port[0].isdigit():
                        target_port = f"col_{target_port}"
                    target_node = f"{node_mapping[target_id]}:{target_port}"
                    connection_type = "column_to_column"
                    edge_style = "solid"
                    edge_color = "#16a34a"  # Green for precise FK connections
                elif target_id in node_columns and node_columns[target_id]['anchor_column']:
                    # Fallback to anchor column
                    anchor_col = node_columns[target_id]['anchor_column']
                    target_port = ''.join(c if c.isalnum() else '_' for c in anchor_col)[:63]
                    if not target_port or target_port[0].isdigit():
                        target_port = f"col_{target_port}"
                    target_node = f"{node_mapping[target_id]}:{target_port}"
                    connection_type = "column_to_anchor"
                    edge_style = "dotted"
                    edge_color = "#16a34a"  # Green for anchor FK connections
                
                # Connection successful - using the determined strategy
                
                dot.edge(
                    source_node,
                    target_node,
                    label=f"{source_column}",
                    color=edge_color,
                    fontcolor='#475569',
                    style=edge_style,
                    arrowhead='normal',
                    penwidth='2'
                )
                relationship_count += 1
            else:
                if source_id not in node_mapping:
                    missing_source_count += 1
                if target_id not in node_mapping:
                    missing_target_count += 1
    else:
        # Handle list format
        for rel in fk_relationships:
            source_id = rel.get('source_dataset_id', rel.get('source_dataset', ''))
            target_id = rel.get('target_dataset_id', rel.get('target_dataset', ''))
            source_column = rel.get('source_column', 'relates to')
            
            # Get target column information
            target_columns = rel.get('target_columns', [])
            target_column = target_columns[0] if target_columns else None
            
            if source_id in node_mapping and target_id in node_mapping:
                # Create safe port names using same logic as node creation
                source_port = ''.join(c if c.isalnum() else '_' for c in source_column)[:63]
                if not source_port or source_port[0].isdigit():
                    source_port = f"col_{source_port}"
                
                # Build source and target node references with ports
                source_node = f"{node_mapping[source_id]}:{source_port}"
                target_node = node_mapping[target_id]
                
                # Determine target connection strategy
                connection_type = "node_to_node"  # Default
                edge_style = "dashed"  # Default for imprecise connections
                edge_color = "#16a34a"  # Green for imprecise FK connections
                
                if target_column:
                    # Precise column-to-column connection
                    target_port = ''.join(c if c.isalnum() else '_' for c in target_column)[:63]
                    if not target_port or target_port[0].isdigit():
                        target_port = f"col_{target_port}"
                    target_node = f"{node_mapping[target_id]}:{target_port}"
                    connection_type = "column_to_column"
                    edge_style = "solid"
                    edge_color = "#16a34a"  # Green for precise FK connections
                elif target_id in node_columns and node_columns[target_id]['anchor_column']:
                    # Fallback to anchor column
                    anchor_col = node_columns[target_id]['anchor_column']
                    target_port = ''.join(c if c.isalnum() else '_' for c in anchor_col)[:63]
                    if not target_port or target_port[0].isdigit():
                        target_port = f"col_{target_port}"
                    target_node = f"{node_mapping[target_id]}:{target_port}"
                    connection_type = "column_to_anchor"
                    edge_style = "dotted"
                    edge_color = "#16a34a"  # Green for anchor FK connections
                
                # Connection successful - using the determined strategy
                
                dot.edge(
                    source_node,
                    target_node,
                    label=f"{source_column}",
                    color=edge_color,
                    fontcolor='#475569',
                    style=edge_style,
                    arrowhead='normal',
                    penwidth='2'
                )
                relationship_count += 1
            else:
                if source_id not in node_mapping:
                    missing_source_count += 1
                if target_id not in node_mapping:
                    missing_target_count += 1
    
    # Add relationship context internal connections
    # These show how context columns connect to their FK columns within the same dataset
    context_connections_count = 0
    for ctx_key, ctx_config in relationship_contexts.items():
        # Parse context key: prefix::dataset::column
        key_parts = ctx_key.split('::')
        if len(key_parts) >= 3:
            dataset_id = key_parts[1]
            context_column = key_parts[2]
            
            # Get FK column information
            primary_fk_column = ctx_config.get('primary_fk_column')
            secondary_fk_column = ctx_config.get('secondary_fk_column')
            primary_fk_dataset = ctx_config.get('primary_fk_dataset')
            secondary_fk_dataset = ctx_config.get('secondary_fk_dataset')
            context_predicate = ctx_config.get('context_predicate', 'Context')
            
            # Only add internal connections if the FK columns are in the same dataset as the context column
            if dataset_id in node_mapping:
                node_id = node_mapping[dataset_id]
                
                # Create safe port names
                context_port = ''.join(c if c.isalnum() else '_' for c in context_column)[:63]
                if not context_port or context_port[0].isdigit():
                    context_port = f"col_{context_port}"
                
                # Add connection from context column to primary FK column (if in same dataset)
                if primary_fk_dataset == dataset_id and primary_fk_column:
                    primary_port = ''.join(c if c.isalnum() else '_' for c in primary_fk_column)[:63]
                    if not primary_port or primary_port[0].isdigit():
                        primary_port = f"col_{primary_port}"
                    
                    dot.edge(
                        f"{node_id}:{context_port}",
                        f"{node_id}:{primary_port}",
                        xlabel=f'→{primary_fk_column}',
                        color='#dc2626',  # Red color for context connections
                        fontcolor='#dc2626',
                        style='dotted',
                        arrowhead='vee',
                        penwidth='2',
                        constraint='false'  # Don't use this edge for layout
                    )
                    context_connections_count += 1
                
                # Add connection from context column to secondary FK column (if in same dataset)
                if secondary_fk_dataset == dataset_id and secondary_fk_column:
                    secondary_port = ''.join(c if c.isalnum() else '_' for c in secondary_fk_column)[:63]
                    if not secondary_port or secondary_port[0].isdigit():
                        secondary_port = f"col_{secondary_port}"
                    
                    dot.edge(
                        f"{node_id}:{context_port}",
                        f"{node_id}:{secondary_port}",
                        xlabel=f'→{secondary_fk_column}',
                        color='#dc2626',  # Red color for context connections
                        fontcolor='#dc2626',
                        style='dotted',
                        arrowhead='vee',
                        penwidth='2',
                        constraint='false'  # Don't use this edge for layout
                    )
                    context_connections_count += 1
    
    # Render to SVG
    try:
        svg_content = dot.pipe(format='svg').decode('utf-8')
        
        # Remove XML declaration to embed in HTML
        if svg_content.startswith('<?xml'):
            svg_content = svg_content.split('\n', 1)[1]
        
        # Add CSS for interactive features
        svg_with_style = f"""
        <style>
            .graph-container {{
                position: relative;
                width: 100%;
                height: 100%;
                overflow: auto;
                background: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                cursor: grab;
            }}
            .graph-container:active {{
                cursor: grabbing;
            }}
            .graph-container svg {{
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
        <div class="graph-container">
            {svg_content}
        </div>
        """
        
        graph_svg = svg_with_style
        error = None
        
        # Add debug info
        debug_info = f"Nodes: {len(node_mapping)}, Relationships added: {relationship_count}, Context connections: {context_connections_count}, Missing sources: {missing_source_count}, Missing targets: {missing_target_count}"
        print(f"DEBUG: {debug_info}")  # For server logs
        print(f"DEBUG: Sample node mappings: {list(node_mapping.items())[:5]}")  # Show first 5 mappings
    except Exception as e:
        import traceback
        graph_svg = None
        error = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
    
    # Get dataset details for sidebar
    datasets = []
    for ds in workspace_datasets:
        if isinstance(ds, str):
            dataset_info = {
                'id': ds,
                'name': ds,
                'entity_type': 'Entity',
                'columns': []
            }
        else:
            dataset_info = {
                'id': ds['id'],
                'name': ds['name'],
                'entity_type': ds.get('entity_type', 'Entity'),
                'columns': ds.get('columns', [])
            }
        datasets.append(dataset_info)
    
    # Pass debug info to template
    try:
        debug_info_dict = {
            'nodes': len(node_mapping),
            'relationships_added': relationship_count,
            'context_connections': context_connections_count,
            'missing_sources': missing_source_count,
            'missing_targets': missing_target_count,
            'total_fk_relationships': len(fk_relationships)
        }
    except:
        debug_info_dict = None
    
    context = {
        'mapping': mapping,
        'datasets': datasets,
        'graph_svg': graph_svg,
        'error': error,
        'debug_info': debug_info_dict,
    }
    
    return render(request, 'metadata/mapping_visualizer_graphviz.html', context)