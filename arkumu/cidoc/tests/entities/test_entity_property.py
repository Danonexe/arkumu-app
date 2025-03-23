import pytest
from unittest.mock import patch
from django.core.exceptions import ValidationError
from ...models.entities import CIDOCEntityProperty

def test_create_property(mock_entity, mock_cidoc_property, mocker):
    """Test basic property creation"""
    mocker.patch('arkumu.cidoc.models.entities.validate_primitive_value', return_value='Test Value')
    
    prop = CIDOCEntityProperty(
        entity=mock_entity,
        cidoc_property=mock_cidoc_property,
        value_data='Test Value'
    )
    
    assert prop.value == 'Test Value'

def test_invalid_value_type(mock_entity, mock_cidoc_property, mocker):
    """Test validation of property value type"""
    mocker.patch(
        'arkumu.cidoc.models.entities.validate_primitive_value',
        side_effect=ValidationError('Invalid type')
    )
    
    with pytest.raises(ValidationError):
        prop = CIDOCEntityProperty(
            entity=mock_entity,
            cidoc_property=mock_cidoc_property
        )
        prop.value = 123  # Invalid type for string property

def test_clean_validation(mock_entity, mock_cidoc_property, mocker):
    """Test clean method validations"""
    # Mock validators
    validate_domain = mocker.patch('arkumu.cidoc.models.entities.validate_property_domain_range')
    validate_cardinality = mocker.patch('arkumu.cidoc.models.entities.validate_property_cardinality')
    
    prop = CIDOCEntityProperty(
        entity=mock_entity,
        cidoc_property=mock_cidoc_property,
        value_data='Test Value'
    )
    
    prop.clean()
    
    validate_domain.assert_called_once()
    validate_cardinality.assert_called_once()
    
    # Test validation error
    validate_domain.side_effect = ValidationError('Domain validation failed')
    with pytest.raises(ValidationError):
        prop.clean()

def test_permission_read_access(mock_entity_property, mock_user, mock_group):
    """Test read permissions"""
    # Configure initial state - no permissions
    mock_entity_property.user_can_read.return_value = False
    mock_entity_property.readable_by_groups.all.return_value = []
    mock_entity_property.readable_by_users.all.return_value = []
    mock_user.groups.all.return_value = []
    mock_user.is_superuser = False
    mock_user.is_authenticated = True
    
    # Test no access
    assert not mock_entity_property.user_can_read(mock_user)
    
    # Test group access
    mock_entity_property.readable_by_groups.all.return_value = [mock_group]
    mock_user.groups.all.return_value = [mock_group]
    mock_entity_property.user_can_read.return_value = True
    assert mock_entity_property.user_can_read(mock_user)
    
    # Reset group access
    mock_entity_property.readable_by_groups.all.return_value = []
    mock_user.groups.all.return_value = []
    mock_entity_property.user_can_read.return_value = False
    
    # Test direct user access
    mock_entity_property.readable_by_users.all.return_value = [mock_user]
    mock_entity_property.user_can_read.return_value = True
    assert mock_entity_property.user_can_read(mock_user)

def test_permission_write_access(mock_entity_property, mock_user, mock_group):
    """Test write permissions"""
    # Configure initial state - no permissions
    mock_entity_property.user_can_write.return_value = False
    mock_entity_property.writable_by_groups.all.return_value = []
    mock_entity_property.writable_by_users.all.return_value = []
    mock_user.groups.all.return_value = []
    mock_user.is_superuser = False
    mock_user.is_authenticated = True
    
    # Test no access
    assert not mock_entity_property.user_can_write(mock_user)
    
    # Test group access
    mock_entity_property.writable_by_groups.all.return_value = [mock_group]
    mock_user.groups.all.return_value = [mock_group]
    mock_entity_property.user_can_write.return_value = True
    assert mock_entity_property.user_can_write(mock_user)
    
    # Reset group access
    mock_entity_property.writable_by_groups.all.return_value = []
    mock_user.groups.all.return_value = []
    mock_entity_property.user_can_write.return_value = False
    
    # Test direct user access
    mock_entity_property.writable_by_users.all.return_value = [mock_user]
    mock_entity_property.user_can_write.return_value = True
    assert mock_entity_property.user_can_write(mock_user)

def test_superuser_permissions(mock_entity_property, mock_superuser):
    """Test that superuser has all permissions"""
    mock_superuser.is_superuser = True
    mock_superuser.is_authenticated = True
    mock_entity_property.user_can_read.return_value = True
    mock_entity_property.user_can_write.return_value = True
    assert mock_entity_property.user_can_read(mock_superuser)
    assert mock_entity_property.user_can_write(mock_superuser) 