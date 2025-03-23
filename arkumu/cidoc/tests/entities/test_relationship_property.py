import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from django.core.exceptions import ValidationError
from django.db.models.fields.related_descriptors import ManyToManyDescriptor, ForwardManyToOneDescriptor
from arkumu.cidoc.models.entities import CIDOCRelationshipProperty

@pytest.fixture
def mock_relationship_property(mock_relationship, mock_cidoc_property, mocker):
    # Create the property instance
    prop = CIDOCRelationshipProperty(
        relationship=mock_relationship,
        cidoc_property=mock_cidoc_property,
        value_data='Test Value'
    )
    
    # Mock the state to prevent DB access
    prop._state = MagicMock()
    prop._state.db = None
    
    # Create mock manager for M2M fields
    def create_mock_manager():
        manager = MagicMock()
        manager.all.return_value = []
        manager.set = MagicMock()
        return manager
    
    # Mock the M2M descriptors
    for field in ['readable_by_groups', 'readable_by_users', 'writable_by_groups', 'writable_by_users']:
        manager = create_mock_manager()
        descriptor = MagicMock(spec=ManyToManyDescriptor)
        descriptor.__get__ = MagicMock(return_value=manager)
        setattr(type(prop), field, descriptor)
        setattr(prop, f'_{field}_cache', manager)
    
    # Mock save method
    prop.save = MagicMock()
    
    return prop

def test_create_property(mock_relationship, mock_cidoc_property):
    """Test basic property creation"""
    with patch('arkumu.cidoc.models.entities.validate_primitive_value') as validate_mock:
        validate_mock.return_value = 'Test Value'
        
        # Create property instance
        prop = CIDOCRelationshipProperty(
            relationship=mock_relationship,
            cidoc_property=mock_cidoc_property,
            value_data='Test Value'
        )
        
        # Mock field descriptors
        prop._state = MagicMock()
        prop._state.db = None
        
        # Set up field descriptors and cache
        fields_cache = {}
        fields_cache[mock_cidoc_property] = mock_cidoc_property
        prop._fields_cache = fields_cache
        
        # Mock relationship field descriptor
        relationship_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        relationship_descriptor.__get__ = MagicMock(return_value=mock_relationship)
        type(prop).relationship = relationship_descriptor
        
        # Mock cidoc_property field descriptor
        property_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        property_descriptor.__get__ = MagicMock(return_value=mock_cidoc_property)
        type(prop).cidoc_property = property_descriptor
        
        # Test value getter
        assert prop.value == 'Test Value'
        
        # Test value setter
        prop.value = 'New Test Value'
        validate_mock.assert_called_with(mock_cidoc_property, 'New Test Value')

def test_invalid_value_type(mock_relationship, mock_cidoc_property):
    """Test validation of property value type"""
    with patch('arkumu.cidoc.models.entities.validate_primitive_value') as validate_mock:
        validate_mock.side_effect = ValidationError('Invalid type')
        
        prop = CIDOCRelationshipProperty(
            relationship=mock_relationship,
            cidoc_property=mock_cidoc_property
        )
        
        # Mock field descriptors
        prop._state = MagicMock()
        prop._state.db = None
        
        # Set up field descriptors and cache
        fields_cache = {}
        fields_cache[mock_cidoc_property] = mock_cidoc_property
        prop._fields_cache = fields_cache
        
        # Mock relationship field descriptor
        relationship_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        relationship_descriptor.__get__ = MagicMock(return_value=mock_relationship)
        type(prop).relationship = relationship_descriptor
        
        # Mock cidoc_property field descriptor
        property_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        property_descriptor.__get__ = MagicMock(return_value=mock_cidoc_property)
        type(prop).cidoc_property = property_descriptor
        
        with pytest.raises(ValidationError):
            prop.value = 123  # Should raise ValidationError
        
        validate_mock.assert_called_once_with(mock_cidoc_property, 123)

def test_clean_validation(mock_relationship, mock_cidoc_property):
    """Test clean method validations"""
    with patch('arkumu.cidoc.models.entities.validate_property_domain_range') as validate_domain, \
         patch('arkumu.cidoc.models.entities.validate_property_cardinality') as validate_cardinality:
        
        # Set up mock property with proper domain class
        mock_cidoc_property.domain_class = MagicMock()
        mock_cidoc_property.domain_class.class_id = 'E21_Person'
        mock_cidoc_property.property_id = 'P1_test_property'
        
        # Set up mock relationship with proper classes
        source_class = MagicMock()
        source_class.class_id = 'E21_Person'
        source_class.parent_classes = MagicMock()
        source_class.parent_classes.all.return_value = []
        
        target_class = MagicMock()
        target_class.class_id = 'E53_Place'
        target_class.parent_classes = MagicMock()
        target_class.parent_classes.all.return_value = []
        
        mock_relationship.source.crm_class = source_class
        mock_relationship.target.crm_class = target_class
        
        # Set up mock parent classes
        parent_classes = MagicMock()
        parent_classes.all.return_value = []
        mock_cidoc_property.domain_class.parent_classes = parent_classes
        
        prop = CIDOCRelationshipProperty(
            relationship=mock_relationship,
            cidoc_property=mock_cidoc_property,
            value_data='Test Value'
        )
        
        # Mock field descriptors
        prop._state = MagicMock()
        prop._state.db = None
        
        # Set up field descriptors and cache
        fields_cache = {}
        fields_cache[mock_cidoc_property] = mock_cidoc_property
        prop._fields_cache = fields_cache
        
        # Mock relationship field descriptor
        relationship_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        relationship_descriptor.__get__ = MagicMock(return_value=mock_relationship)
        type(prop).relationship = relationship_descriptor
        
        # Mock cidoc_property field descriptor
        property_descriptor = MagicMock(spec=ForwardManyToOneDescriptor)
        property_descriptor.__get__ = MagicMock(return_value=mock_cidoc_property)
        type(prop).cidoc_property = property_descriptor
        
        # Test successful validation
        validate_domain.return_value = None
        validate_cardinality.return_value = None
        prop.clean()
        
        validate_domain.assert_called_once_with(
            mock_cidoc_property,
            source_class,
            target_class,
            'Test Value'
        )
        validate_cardinality.assert_called_once_with(
            mock_cidoc_property,
            mock_relationship,
            'Test Value'
        )
        
        # Test validation error
        validate_domain.reset_mock()
        validate_domain.side_effect = ValidationError('Domain validation failed')
        with pytest.raises(ValidationError):
            prop.clean()

def test_permission_read_access(mock_relationship_property, mock_user, mock_group):
    """Test read permissions"""
    prop = mock_relationship_property
    
    # Test no access
    prop.readable_by_groups.all.return_value = []
    prop.readable_by_users.all.return_value = []
    mock_user.groups.all.return_value = []
    assert not prop.user_can_read(mock_user)
    
    # Test group access
    prop.readable_by_groups.all.return_value = [mock_group]
    mock_user.groups.all.return_value = [mock_group]
    assert prop.user_can_read(mock_user)
    
    # Test direct user access
    prop.readable_by_groups.all.return_value = []
    mock_user.groups.all.return_value = []
    prop.readable_by_users.all.return_value = [mock_user]
    assert prop.user_can_read(mock_user)

def test_permission_write_access(mock_relationship_property, mock_user, mock_group):
    """Test write permissions"""
    prop = mock_relationship_property
    
    # Test no access
    prop.writable_by_groups.all.return_value = []
    prop.writable_by_users.all.return_value = []
    mock_user.groups.all.return_value = []
    assert not prop.user_can_write(mock_user)
    
    # Test group access
    prop.writable_by_groups.all.return_value = [mock_group]
    mock_user.groups.all.return_value = [mock_group]
    assert prop.user_can_write(mock_user)
    
    # Test direct user access
    prop.writable_by_groups.all.return_value = []
    mock_user.groups.all.return_value = []
    prop.writable_by_users.all.return_value = [mock_user]
    assert prop.user_can_write(mock_user)

def test_superuser_permissions(mock_relationship_property, mock_superuser):
    """Test that superuser has all permissions"""
    prop = mock_relationship_property
    
    assert prop.user_can_read(mock_superuser)
    assert prop.user_can_write(mock_superuser) 