from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from arkumu.metadata.models import Mapping
from arkumu.common.uri_utils import slugify_uri_part


@login_required
def blueprint_visualizer(request, mapping_id):
    """Display the blueprint structure of a mapping in a visual format."""
    mapping = get_object_or_404(Mapping, pk=mapping_id)
    
    # Generate Mermaid graph definition with compatible syntax
    graph_lines = ["flowchart TD"]
    
    # Extract datasets from mapping config
    datasets = []
    workspace_datasets = mapping.mapping_config.get('workspace_datasets', [])
    workspace_columns = mapping.mapping_config.get('workspace_columns', {})
    
    # Helper function to create Mermaid-safe node IDs
    def make_mermaid_safe(dataset_id):
        """Convert dataset ID to Mermaid-safe format."""
        safe_id = slugify_uri_part(dataset_id).replace('-', '_')
        # Ensure it doesn't start with a number for Mermaid
        if safe_id and safe_id[0].isdigit():
            safe_id = f"ds_{safe_id}"
        return safe_id
    
    for ds in workspace_datasets:
        if isinstance(ds, str):
            # Handle older format: workspace_datasets is list of strings
            original_dataset_id = ds
            dataset_name = ds
            
            # Extract columns from workspace_columns for this dataset
            columns = []
            
            # First, detect the prefix by examining column keys
            prefix = None
            for col_key in workspace_columns.keys():
                if f"::{original_dataset_id}::" in col_key:
                    prefix = col_key.split("::")[0]
                    break
            
            # If no prefix found, try without namespace
            if prefix is None:
                for col_key in workspace_columns.keys():
                    if original_dataset_id in col_key and "::" in col_key:
                        prefix = col_key.split("::")[0]
                        break
            
            # Extract columns using detected prefix
            for col_key, col_config in workspace_columns.items():
                if prefix and col_key.startswith(f"{prefix}::{original_dataset_id}::"):
                    col_name = col_key.split("::", 2)[2]  # Split on :: and take the 3rd part
                    column_info = {
                        'name': col_name,
                        'arkumu_type': col_config.get('type', 'text'),  # Fixed: use 'type' not 'arkumu_type'
                        'is_anchor': col_config.get('is_anchor', False),  # Fixed: use 'is_anchor' not 'anchor'
                        'property': col_config.get('property', '')
                    }
                    columns.append(column_info)
            
            entity_type = 'Entity'
            
        else:
            # Handle newer format: workspace_datasets is list of dicts
            original_dataset_id = ds['id']
            dataset_name = ds['name']
            
            # Extract column information from dataset config
            columns = []
            for col in ds.get('columns', []):
                column_info = {
                    'name': col['name'],
                    'arkumu_type': col.get('arkumu_type', 'text'),
                    'is_anchor': col.get('anchor', False),
                    'property': col.get('property', '')
                }
                columns.append(column_info)
            
            # Get entity type from the dataset config
            entity_type = ds.get('entity_type', 'Entity')
            if entity_type.startswith('http'):
                # Extract the last part of the URI for display
                entity_type = entity_type.split('/')[-1]
        
        # Get safe node ID from centralized mapper
        dataset_id = make_mermaid_safe(original_dataset_id)
        
        # Add enhanced node for each dataset with shape and metadata
        dataset_shape = "rect"  # Default rectangular shape
        if entity_type.lower() in ['person', 'people', 'author', 'creator']:
            dataset_shape = "rounded"
        elif entity_type.lower() in ['document', 'file', 'paper', 'book']:
            dataset_shape = "doc"
        elif entity_type.lower() in ['organization', 'institution', 'company']:
            dataset_shape = "hexagon"
        
        # Enhanced node definition with entity type and column count
        column_count = len(columns)
        anchor_columns = [col for col in columns if col.get('is_anchor')]
        anchor_info = f" ⚓{len(anchor_columns)}" if anchor_columns else ""
        
        # Clean node label - escape any special characters and use simple text
        clean_dataset_name = dataset_name.replace('"', "'").replace('\n', ' ')
        clean_entity_type = entity_type.replace('"', "'").replace('\n', ' ')
        anchor_display = f" ({len(anchor_columns)} anchors)" if anchor_columns else ""
        
        # Create multi-line label using proper HTML format
        node_label = f"{clean_dataset_name}<br>{clean_entity_type}<br>{column_count} columns{anchor_display}"
        
        # Use traditional Mermaid syntax for maximum compatibility
        if dataset_shape == "rounded":
            graph_lines.append(f'    {dataset_id}("{node_label}")')
        elif dataset_shape == "hexagon":
            graph_lines.append(f'    {dataset_id}{{{{{node_label}}}}}')
        else:
            # Use standard rectangle for all other cases including documents
            graph_lines.append(f'    {dataset_id}[{node_label}]')
        
        datasets.append({
            'id': dataset_id,
            'name': dataset_name,
            'entity_type': entity_type,
            'columns': columns
        })
    
    # Add relationships to graph
    fk_relationships = mapping.mapping_config.get('fk_relationships', {})
    
    if isinstance(fk_relationships, dict):
        # Handle dictionary format: {rel_id: {source_dataset: ..., target_dataset: ...}}
        for rel_id, rel in fk_relationships.items():
            orig_source_id = rel.get('source_dataset', rel.get('source_dataset_id', ''))
            orig_target_id = rel.get('target_dataset', rel.get('target_dataset_id', ''))
            
            # Map to safe IDs using centralized mapper
            safe_source_id = make_mermaid_safe(orig_source_id)
            safe_target_id = make_mermaid_safe(orig_target_id)
            
            label = rel.get('source_column', '')
            if safe_source_id and safe_target_id:
                relationship_label = f"{label}" if label else "relates to"
                graph_lines.append(f'    {safe_source_id} -->|"{relationship_label}"| {safe_target_id}')
    else:
        # Handle list format: [{source_dataset_id: ..., target_dataset_id: ...}, ...]
        for rel in fk_relationships:
            orig_source_id = rel.get('source_dataset_id', rel.get('source_dataset', ''))
            orig_target_id = rel.get('target_dataset_id', rel.get('target_dataset', ''))
            
            # Map to safe IDs using centralized mapper
            safe_source_id = make_mermaid_safe(orig_source_id)
            safe_target_id = make_mermaid_safe(orig_target_id)
            
            label = rel.get('source_column', '')
            if safe_source_id and safe_target_id:
                relationship_label = f"{label}" if label else "relates to"
                graph_lines.append(f'    {safe_source_id} -->|"{relationship_label}"| {safe_target_id}')
    
    # Enhanced styling with semantic classes
    graph_lines.extend([
        '',
        '    %% Enhanced styling for different entity types',
        '    classDef default fill:#f8fafc,stroke:#64748b,stroke-width:2px,color:#334155;',
        '    classDef person fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e40af;',
        '    classDef document fill:#ecfdf5,stroke:#10b981,stroke-width:2px,color:#065f46;',
        '    classDef organization fill:#fef3c7,stroke:#f59e0b,stroke-width:2px,color:#92400e;',
        '    classDef entity fill:#f3e8ff,stroke:#8b5cf6,stroke-width:2px,color:#5b21b6;'
    ])
    
    # Apply semantic classes to nodes based on entity types
    for dataset in datasets:
        dataset_id = dataset['id']
        entity_type = dataset['entity_type'].lower()
        
        if entity_type in ['person', 'people', 'author', 'creator']:
            graph_lines.append(f'    class {dataset_id} person;')
        elif entity_type in ['document', 'file', 'paper', 'book']:
            graph_lines.append(f'    class {dataset_id} document;')
        elif entity_type in ['organization', 'institution', 'company']:
            graph_lines.append(f'    class {dataset_id} organization;')
        else:
            graph_lines.append(f'    class {dataset_id} entity;')
    
    mermaid_graph = '\n'.join(graph_lines)
    
    context = {
        'mapping': mapping,
        'datasets': datasets,
        'mermaid_graph': mermaid_graph
    }
    
    return render(request, 'metadata/mapping_blueprint_visualizer.html', context)