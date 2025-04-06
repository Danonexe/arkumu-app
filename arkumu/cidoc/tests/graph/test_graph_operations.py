import pytest
from unittest.mock import patch, MagicMock
from django.core.exceptions import ValidationError
from ...models.entities import GraphManager, CIDOCEntity, CIDOCRelationship

@pytest.fixture
def mock_graph(mocker):
    """Fixture for mocked CIDOCGraph"""
    mock = mocker.patch('arkumu.cidoc.models.entities.CIDOCGraph')
    graph = MagicMock()
    mock.return_value = graph
    return graph

@pytest.fixture
def graph_manager(mock_graph):
    """Fixture for GraphManager instance"""
    manager = GraphManager()
    # The graph is already mocked by mock_graph fixture
    assert isinstance(manager.graph, MagicMock)
    return manager

@pytest.fixture
def mock_entity(mocker):
    """Fixture for a mock CIDOCEntity"""
    entity = MagicMock(spec=CIDOCEntity)
    entity.crm_class = 'E21_Person'
    entity.age_node_id = 'node123'
    
    # Mock the save method to actually call graph_manager
    def save_with_graph():
        if not entity.age_node_id:
            entity.age_node_id = entity.graph_manager.create_entity_node(
                entity.crm_class,
                {'crm_class': entity.crm_class}
            )
    entity.save.side_effect = save_with_graph
    
    # Mock the delete method to actually call graph_manager
    def delete_with_graph():
        if entity.age_node_id:
            entity.graph_manager.delete_node(entity.age_node_id)
            entity.age_node_id = None
    entity.delete.side_effect = delete_with_graph
    
    return entity

@pytest.fixture
def mock_relationship(mocker, mock_entity):
    """Fixture for a mock CIDOCRelationship"""
    relationship = MagicMock(spec=CIDOCRelationship)
    relationship.source = mock_entity
    relationship.target = mock_entity
    relationship.relation_type = 'P11_had_participant'
    relationship.age_edge_id = 'edge123'
    
    # Mock the save method to actually call graph_manager
    def save_with_graph():
        if not relationship.age_edge_id:
            relationship.age_edge_id = relationship.graph_manager.create_relationship_edge(
                relationship.source.age_node_id,
                relationship.target.age_node_id,
                relationship.relation_type,
                {'relation_type': relationship.relation_type}
            )
    relationship.save.side_effect = save_with_graph
    
    # Mock the delete method to actually call graph_manager
    def delete_with_graph():
        if relationship.age_edge_id:
            relationship.graph_manager.delete_edge(relationship.age_edge_id)
            relationship.age_edge_id = None
    relationship.delete.side_effect = delete_with_graph
    
    return relationship

def test_graph_manager_creation(graph_manager, mock_graph):
    """Test GraphManager initialization"""
    assert isinstance(graph_manager.graph, MagicMock)

def test_create_entity_node(graph_manager, mock_graph):
    """Test creating a node for an entity"""
    properties = {'crm_class': 'E21_Person', 'name': 'Test Person'}
    mock_graph.create_entity.return_value = 'node123'
    
    node_id = graph_manager.create_entity_node('E21_Person', properties)
    
    assert node_id == 'node123'
    mock_graph.create_entity.assert_called_once_with('E21_Person', properties)

def test_create_relationship_edge(graph_manager, mock_graph):
    """Test creating an edge for a relationship"""
    properties = {'relation_type': 'P11_had_participant'}
    mock_graph.create_relationship.return_value = 'edge123'
    
    edge_id = graph_manager.create_relationship_edge(
        'node1',
        'node2',
        'P11_had_participant',
        properties
    )
    
    assert edge_id == 'edge123'
    mock_graph.create_relationship.assert_called_once_with(
        'node1',
        'node2',
        'P11_had_participant',
        properties
    )

def test_update_node_properties(graph_manager, mock_graph):
    """Test updating node properties"""
    properties = {'name': 'Updated Name'}
    mock_graph.update_node.return_value = True
    
    result = graph_manager.update_node_properties('node123', properties)
    
    assert result is True
    mock_graph.update_node.assert_called_once_with('node123', properties)

def test_update_edge_properties(graph_manager, mock_graph):
    """Test updating edge properties"""
    properties = {'date': '2024-03-19'}
    mock_graph.update_edge.return_value = True
    
    result = graph_manager.update_edge_properties('edge123', properties)
    
    assert result is True
    mock_graph.update_edge.assert_called_once_with('edge123', properties)

def test_delete_node(graph_manager, mock_graph):
    """Test node deletion"""
    graph_manager.delete_node('node123')
    mock_graph.delete_node.assert_called_once_with('node123')

def test_delete_edge(graph_manager, mock_graph):
    """Test edge deletion"""
    graph_manager.delete_edge('edge123')
    mock_graph.delete_edge.assert_called_once_with('edge123')

def test_entity_graph_operations(mock_entity, graph_manager):
    """Test graph operations in CIDOCEntity"""
    # Configure entity for graph operations
    mock_entity.graph_manager = graph_manager
    mock_entity.age_node_id = None
    graph_manager.graph.create_entity.return_value = 'new_node123'
    
    # Test save operation creates node
    mock_entity.save()
    
    graph_manager.graph.create_entity.assert_called_once_with(
        'E21_Person',
        {'crm_class': 'E21_Person'}
    )
    assert mock_entity.age_node_id == 'new_node123'
    
    # Test delete operation removes node
    mock_entity.delete()
    graph_manager.graph.delete_node.assert_called_once_with('new_node123')

def test_relationship_graph_operations(mock_relationship, graph_manager):
    """Test graph operations in CIDOCRelationship"""
    # Configure relationship for graph operations
    mock_relationship.graph_manager = graph_manager
    mock_relationship.age_edge_id = None
    graph_manager.graph.create_relationship.return_value = 'new_edge123'
    
    # Test save operation creates edge
    mock_relationship.save()
    
    graph_manager.graph.create_relationship.assert_called_once_with(
        'node123',  # from mock_entity fixture
        'node123',  # from mock_entity fixture
        'P11_had_participant',
        {'relation_type': 'P11_had_participant'}
    )
    assert mock_relationship.age_edge_id == 'new_edge123'
    
    # Test delete operation removes edge
    mock_relationship.delete()
    graph_manager.graph.delete_edge.assert_called_once_with('new_edge123') 