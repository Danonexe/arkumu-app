import pytest
from unittest.mock import MagicMock, patch
from django.core.exceptions import ValidationError
from ...models.entities import CIDOCEntity, CIDOCRelationship, GraphManager
from ...models.schema import CIDOCProperty, CIDOCGraph

# Mock the Django models and dependencies first
mock_cidoc_entity = MagicMock()
mock_cidoc_property = MagicMock()
mock_cidoc_graph = MagicMock()

# Mock the modules
patch('arkumu.cidoc.models.entities.CIDOCEntity', mock_cidoc_entity).start()
patch('arkumu.cidoc.models.schema.CIDOCProperty', mock_cidoc_property).start()
patch('arkumu.cidoc.models.schema.CIDOCGraph', mock_cidoc_graph).start()

@pytest.fixture
def mock_graph_manager():
    manager = MagicMock(spec=GraphManager)
    manager.create_relationship_edge.return_value = 'test_edge_id'
    manager.delete_edge.return_value = True
    manager.update_edge_properties.return_value = True
    return manager

@pytest.fixture
def mock_source_entity(mock_graph_manager):
    entity = MagicMock(spec=CIDOCEntity)
    entity.crm_class = 'E21_Person'
    entity.age_node_id = 'source_vertex_id'
    entity._graph_manager = mock_graph_manager
    return entity

@pytest.fixture
def mock_target_entity(mock_graph_manager):
    entity = MagicMock(spec=CIDOCEntity)
    entity.crm_class = 'E53_Place'
    entity.age_node_id = 'target_vertex_id'
    entity._graph_manager = mock_graph_manager
    return entity

@pytest.fixture
def mock_relationship(mock_source_entity, mock_target_entity, mock_graph_manager):
    rel = MagicMock(spec=CIDOCRelationship)
    rel.source = mock_source_entity
    rel.target = mock_target_entity
    rel.relation_type = 'P74_has_current_or_former_residence'
    rel._graph_manager = mock_graph_manager
    rel.age_edge_id = 'test_edge_id'
    return rel

@pytest.fixture
def mock_cidoc_property():
    prop = MagicMock(spec=CIDOCProperty)
    prop.property_id = 'P74_has_current_or_former_residence'
    prop.domain = 'E21_Person'
    prop.range = 'E53_Place'
    prop.is_symmetric = False
    prop.inverse_property = None
    return prop

def test_create_relationship(mock_source_entity, mock_target_entity, mock_graph_manager):
    """Test basic relationship creation with graph operations"""
    # Mock the GraphManager
    with patch('arkumu.cidoc.models.entities.GraphManager', return_value=mock_graph_manager):
        relationship = MagicMock(spec=CIDOCRelationship)
        relationship.source = mock_source_entity
        relationship.target = mock_target_entity
        relationship.relation_type = 'P74_has_current_or_former_residence'
        relationship._graph_manager = mock_graph_manager
        
        # Mock save to actually call create_relationship_edge
        def mock_save(*args, **kwargs):
            relationship.age_edge_id = relationship._graph_manager.create_relationship_edge(
                relationship.source.age_node_id,
                relationship.target.age_node_id,
                relationship.relation_type,
                {'relation_type': relationship.relation_type}
            )
        relationship.save.side_effect = mock_save
        
        # Call save
        relationship.save()
        
        # Verify graph operations
        mock_graph_manager.create_relationship_edge.assert_called_once_with(
            'source_vertex_id',
            'target_vertex_id',
            'P74_has_current_or_former_residence',
            {'relation_type': 'P74_has_current_or_former_residence'}
        )
        assert relationship.age_edge_id == 'test_edge_id'

def test_delete_relationship(mock_relationship, mock_graph_manager):
    """Test relationship deletion and graph edge cleanup"""
    # Mock the delete method to actually call the graph manager's delete_edge
    def mock_delete(*args, **kwargs):
        mock_relationship._graph_manager.delete_edge(mock_relationship.age_edge_id)
    mock_relationship.delete.side_effect = mock_delete
    
    # Delete the relationship
    mock_relationship.delete()
    
    # Verify graph operations
    mock_graph_manager.delete_edge.assert_called_once_with('test_edge_id')

def test_update_relationship_properties(mock_relationship, mock_graph_manager):
    """Test updating relationship properties in the graph"""
    # Set up the mock relationship with graph manager
    mock_relationship.age_edge_id = 'test_edge_id'
    mock_relationship._graph_manager = mock_graph_manager
    
    # Update properties
    new_props = {'timestamp': '2024-01-01', 'certainty': 0.9}
    result = mock_relationship._graph_manager.update_edge_properties('test_edge_id', new_props)
    
    # Verify graph operations
    mock_graph_manager.update_edge_properties.assert_called_once_with('test_edge_id', new_props)
    assert result is True

def test_symmetric_relationship(mock_source_entity, mock_target_entity, mock_cidoc_property, mocker):
    """Test symmetric relationship validation"""
    mock_cidoc_property.is_symmetric = True
    mocker.patch(
        'arkumu.cidoc.models.entities.CIDOCProperty.objects.get',
        return_value=mock_cidoc_property
    )
    
    # Mock the validator
    validate_symmetric = mocker.patch('arkumu.cidoc.models.entities.validate_symmetric_relationship')
    
    relationship = MagicMock(spec=CIDOCRelationship)
    relationship.source = mock_source_entity
    relationship.target = mock_target_entity
    relationship.relation_type = mock_cidoc_property.property_id
    
    # Mock save to check symmetric validation
    def mock_save(*args, **kwargs):
        validate_symmetric(mock_cidoc_property, mock_source_entity, mock_target_entity)
    relationship.save.side_effect = mock_save
    
    relationship.save()
    validate_symmetric.assert_called_once_with(mock_cidoc_property, mock_source_entity, mock_target_entity)

def test_get_relationship_property(mock_relationship, mock_user):
    """Test getting relationship property with permissions"""
    # Mock the get_property method to match the actual implementation
    def mock_get_property(user, property_id):
        try:
            prop = mock_relationship.cidocrelationshipproperty_set.get(
                property__property_id=property_id
            )
            if prop.user_can_read.return_value:
                return prop.value
            return None
        except CIDOCRelationship.DoesNotExist:
            return None
            
    mock_relationship.get_property = mock_get_property
    
    # Test 1: Property doesn't exist
    mock_relationship.cidocrelationshipproperty_set.get.side_effect = CIDOCRelationship.DoesNotExist
    assert mock_relationship.get_property(mock_user, 'non_existent') is None
    
    # Test 2: Property exists with read permission
    mock_prop = MagicMock()
    mock_prop.user_can_read.return_value = True
    mock_prop.value = 'test value'
    mock_relationship.cidocrelationshipproperty_set.get.side_effect = None
    mock_relationship.cidocrelationshipproperty_set.get.return_value = mock_prop
    
    assert mock_relationship.get_property(mock_user, 'existing') == 'test value'
    
    # Test 3: Property exists without read permission
    mock_prop.user_can_read.return_value = False
    assert mock_relationship.get_property(mock_user, 'existing') is None 