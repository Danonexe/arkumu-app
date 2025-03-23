import pytest
from unittest.mock import MagicMock, create_autospec
from django.contrib.auth.models import User, Group
from ...models.entities import (
    CIDOCEntity,
    CIDOCEntityProperty,
    CIDOCRelationship,
    CIDOCRelationshipProperty
)
from ...models.schema import CIDOCProperty, CIDOCClass
import age

@pytest.fixture
def mock_age_graph():
    """Mock AGE graph connection"""
    graph = MagicMock()
    graph.create_entity.return_value = MagicMock(id='new_node_id')
    graph.create_relationship.return_value = MagicMock(id='new_edge_id')
    return graph

@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.is_superuser = False
    user.groups = MagicMock()
    user.groups.all.return_value = []
    user._state = MagicMock()
    user._state.db = None
    return user

@pytest.fixture
def mock_superuser():
    user = MagicMock(spec=User)
    user.is_superuser = True
    user._state = MagicMock()
    user._state.db = None
    return user

@pytest.fixture
def mock_group():
    group = MagicMock(spec=Group)
    group._state = MagicMock()
    group._state.db = None
    return group

@pytest.fixture
def mock_cidoc_class():
    cls = MagicMock(spec=CIDOCClass)
    cls._state = MagicMock()
    cls._state.db = None
    return cls

@pytest.fixture
def mock_cidoc_property():
    prop = MagicMock(spec=CIDOCProperty)
    prop.property_id = 'P1_is_identified_by'
    prop.domain = 'E1_CRM_Entity'
    prop.range = 'E41_Appellation'
    prop.primitive_type = 'string'
    prop._state = MagicMock()
    prop._state.db = None
    return prop

@pytest.fixture
def mock_entity():
    entity = MagicMock(spec=CIDOCEntity)
    entity.crm_class = 'E21_Person'
    entity.age_node_id = 'node123'
    entity.cidocentityproperty_set = MagicMock()
    entity._state = MagicMock()
    entity._state.db = None
    return entity

@pytest.fixture
def mock_entity_property():
    prop = MagicMock(spec=CIDOCEntityProperty)
    prop.readable_by_groups = MagicMock()
    prop.readable_by_groups.all.return_value = []
    prop.writable_by_groups = MagicMock()
    prop.writable_by_groups.all.return_value = []
    prop.readable_by_users = MagicMock()
    prop.readable_by_users.all.return_value = []
    prop.writable_by_users = MagicMock()
    prop.writable_by_users.all.return_value = []
    prop._value = 'Test Value'
    prop._state = MagicMock()
    prop._state.db = None
    prop.user_can_read.return_value = False
    prop.user_can_write.return_value = False
    return prop

@pytest.fixture
def mock_relationship():
    rel = MagicMock(spec=CIDOCRelationship)
    rel.source = MagicMock(spec=CIDOCEntity)
    rel.target = MagicMock(spec=CIDOCEntity)
    rel.relation_type = 'P74_has_current_or_former_residence'
    rel.age_edge_id = 'edge123'
    rel.cidocrelationshipproperty_set = MagicMock()
    rel._state = MagicMock()
    rel._state.db = None
    # Add state to related entities
    rel.source._state = MagicMock()
    rel.source._state.db = None
    rel.target._state = MagicMock()
    rel.target._state.db = None
    return rel

@pytest.fixture
def mock_graph_manager():
    manager = MagicMock()
    manager.create_entity_node.return_value = 'new_node_id'
    manager.create_relationship_edge.return_value = 'new_edge_id'
    return manager 