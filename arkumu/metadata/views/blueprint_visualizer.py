from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from arkumu.metadata.models import Mapping


@login_required
def blueprint_visualizer(request, mapping_id):
    """Display the blueprint structure of a mapping in a visual format."""
    mapping = get_object_or_404(Mapping, pk=mapping_id)
    
    # Generate Mermaid graph definition
    graph_lines = ["graph LR;"]
    
    # Extract datasets from mapping config
    datasets = []
    workspace_datasets = mapping.mapping_config.get('workspace_datasets', [])
    
    for ds in workspace_datasets:
        # Add node for each dataset
        graph_lines.append(f'    {ds["id"]}["{ds["name"]}"];')
        
        # Extract column information
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
        
        datasets.append({
            'id': ds['id'],
            'name': ds['name'],
            'entity_type': entity_type,
            'columns': columns
        })
    
    # Add relationships to graph
    relationships = mapping.mapping_config.get('fk_relationships', [])
    for rel in relationships:
        source_id = rel['source_dataset_id']
        target_id = rel['target_dataset_id']
        label = f"{rel['source_column']}"
        graph_lines.append(f'    {source_id} -->|{label}| {target_id};')
    
    # Style the graph
    graph_lines.append('    classDef default fill:#f9f9f9,stroke:#333,stroke-width:2px;')
    
    mermaid_graph = '\n'.join(graph_lines)
    
    context = {
        'mapping': mapping,
        'datasets': datasets,
        'mermaid_graph': mermaid_graph
    }
    
    return render(request, 'metadata/mapping_blueprint_visualizer.html', context)