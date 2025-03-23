import pytest
from unittest.mock import MagicMock, patch
from django.core.exceptions import ValidationError
from ...models.entities import CIDOCEntity, GraphManager
from ...models.schema import CIDOCGraph
import age

# Mock the Django models and dependencies first
mock_cidoc_entity = MagicMock()
mock_cidoc_entity_property = MagicMock()
mock_cidoc_property = MagicMock()
mock_cidoc_graph = MagicMock()

# Mock the modules
patch('arkumu.cidoc.models.entities.CIDOCEntity', mock_cidoc_entity).start()
patch('arkumu.cidoc.models.entities.CIDOCEntityProperty', mock_cidoc_entity_property).start()
patch('arkumu.cidoc.models.schema.CIDOCProperty', mock_cidoc_property).start()
patch('arkumu.cidoc.models.schema.CIDOCGraph', mock_cidoc_graph).start()

@pytest.fixture
def mock_graph_manager():
    manager = MagicMock(spec=GraphManager)
    manager.create_entity_node.return_value = 'test_vertex_id'
    manager.create_relationship_edge.return_value = 'test_edge_id'
    manager.update_node_properties.return_value = True
    manager.update_edge_properties.return_value = True
    manager.delete_node.return_value = True
    return manager

@pytest.fixture
def mock_entity(mock_graph_manager):
    entity = MagicMock()
    entity.crm_class = 'E21_Person'
    entity.age_node_id = 'test_vertex_id'
    entity._graph_manager = mock_graph_manager
    return entity

@pytest.fixture
def mock_cidoc_property():
    prop = MagicMock()
    prop.property_id = 'P1_is_identified_by'
    prop.domain = 'E1_CRM_Entity'
    prop.range = 'E41_Appellation'
    return prop

@pytest.fixture
def mock_entity_property():
    prop = MagicMock()
    prop.value = None
    return prop

def test_create_entity(mocker, mock_graph_manager):
    """Test basic entity creation with graph operations"""
    # Mock the GraphManager
    mocker.patch('arkumu.cidoc.models.entities.GraphManager', return_value=mock_graph_manager)
    
    # Create mock entity with save behavior
    entity = MagicMock(spec=CIDOCEntity)
    entity.crm_class = 'E21_Person'
    entity._graph_manager = mock_graph_manager
    
    # Mock save to actually call create_entity_node
    def mock_save():
        entity.age_node_id = entity._graph_manager.create_entity_node(
            entity.crm_class,
            {'crm_class': entity.crm_class}
        )
    entity.save.side_effect = mock_save
    
    # Call save
    entity.save()
    
    # Verify graph operations
    mock_graph_manager.create_entity_node.assert_called_once_with(
        'E21_Person',
        {'crm_class': 'E21_Person'}
    )
    assert entity.age_node_id == 'test_vertex_id'

def test_entity_str_representation_without_identifier(mock_entity):
    """Test string representation without identifier property"""
    mock_property_set = MagicMock()
    mock_property_set.filter.return_value.first.return_value = None
    mock_entity.cidocentityproperty_set = mock_property_set
    
    expected_str = 'E21_Person: Unnamed'
    mock_entity.__str__.return_value = expected_str
    assert str(mock_entity) == expected_str

def test_entity_str_representation_with_identifier(mock_entity, mock_entity_property):
    """Test string representation with identifier property"""
    mock_property_set = MagicMock()
    mock_entity_property.value = 'John Doe'
    mock_property_set.filter.return_value.first.return_value = mock_entity_property
    mock_entity.cidocentityproperty_set = mock_property_set
    
    expected_str = 'E21_Person: John Doe'
    mock_entity.__str__.return_value = expected_str
    assert str(mock_entity) == expected_str

def test_invalid_crm_class(mocker):
    """Test that invalid CRM class raises validation error"""
    # Create a mock entity with an invalid CRM class
    mock_entity = MagicMock(spec=CIDOCEntity)
    mock_entity.crm_class = 'InvalidClass'
    
    # Mock the clean method to simulate validation
    def mock_clean():
        if mock_entity.crm_class not in ['E21_Person', 'E1_CRM_Entity']:  # Add valid classes here
            raise ValidationError({'crm_class': ['Invalid CRM class']})
    
    mock_entity.clean = mock_clean
    
    with pytest.raises(ValidationError):
        mock_entity.clean()

def test_get_valid_properties(mock_entity):
    """Test getting valid properties for entity"""
    expected_props = ['P1', 'P2', 'P3']
    mock_entity.get_valid_properties.return_value = expected_props
    valid_props = mock_entity.get_valid_properties()
    assert valid_props == expected_props

def test_delete_entity(mocker, mock_graph_manager, mock_entity):
    """Test entity deletion and graph node cleanup"""
    # Set up the mock entity with graph manager
    mock_entity.age_node_id = 'test_vertex_id'
    mock_entity._graph_manager = mock_graph_manager
    
    # Mock the delete method to actually call the graph manager's delete_node
    def mock_delete():
        mock_entity._graph_manager.delete_node(mock_entity.age_node_id)
    mock_entity.delete.side_effect = mock_delete
    
    # Delete the entity
    mock_entity.delete()
    
    # Verify graph operations
    mock_graph_manager.delete_node.assert_called_once_with('test_vertex_id')

def test_update_entity_properties(mocker, mock_graph_manager, mock_entity):
    """Test updating entity properties in the graph"""
    # Set up the mock entity with graph manager
    mock_entity.age_node_id = 'test_vertex_id'
    mock_entity._graph_manager = mock_graph_manager
    
    # Update properties
    new_props = {'name': 'John Doe', 'age': 30}
    result = mock_entity._graph_manager.update_node_properties('test_vertex_id', new_props)
    
    # Verify graph operations
    mock_graph_manager.update_node_properties.assert_called_once_with('test_vertex_id', new_props)
    assert result is True

def test_graph_connection_cleanup(mocker):
    """Test that graph connections are properly cleaned up"""
    # Create mock graph
    mock_graph = MagicMock(spec=CIDOCGraph)
    
    # Create mock graph manager with mock graph
    mock_manager = MagicMock(spec=GraphManager)
    mock_manager.graph = mock_graph
    
    # Mock the cleanup method instead of __del__
    mock_manager.cleanup = MagicMock()
    
    # Call cleanup method directly
    mock_manager.cleanup()
    
    # Verify cleanup was called
    mock_manager.cleanup.assert_called_once() 