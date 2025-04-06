import pytest
from django.core.exceptions import ValidationError
from ...models.entities import CIDOCEntityProperty

@pytest.mark.django_db
def test_create_property_real(real_entity, real_property, test_user):
    """Test basic property creation with real entities"""
    # Create a new property
    prop = CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Test Value',
        created_by=test_user,
        updated_by=test_user
    )
    
    # Verify property was created correctly
    assert prop.pk is not None, "Property was not created"
    assert prop.value == 'Test Value', "Property has incorrect value"
    
    # Verify we can retrieve it from the database
    saved_prop = CIDOCEntityProperty.objects.get(pk=prop.pk)
    assert saved_prop.value == 'Test Value', "Retrieved property has incorrect value"

@pytest.mark.django_db
def test_invalid_value_type_real(real_entity, loaded_cidoc_data):
    """Test validation of property value type with real entities"""
    # Find a number-type property
    number_property = None
    for prop in real_entity.get_valid_properties():
        if prop.range_class and prop.range_class.class_id.startswith('E60'):  # Number type
            number_property = prop
            break
    
    if not number_property:
        pytest.skip("No number properties available for testing")
    
    # Try to create property with invalid value
    prop = CIDOCEntityProperty(
        entity=real_entity,
        cidoc_property=number_property
    )
    
    # This should raise validation error
    with pytest.raises(ValidationError):
        prop.value = "not a number"
        prop.full_clean()

@pytest.mark.django_db
def test_clean_validation_real(real_entity, real_property):
    """Test clean method validations with real entities"""
    # Create property
    prop = CIDOCEntityProperty(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Should validate successfully
    prop.clean()
    
    # Test with invalid domain
    # Find a property not valid for this entity
    invalid_props = []
    all_valid_props = set(p.id for p in real_entity.get_valid_properties())
    
    # Get all properties using the validators method
    from ...validators import get_valid_properties
    all_props = set(p.id for p in real_property.__class__.objects.all())
    
    invalid_prop_ids = all_props - all_valid_props
    
    if invalid_prop_ids:
        from ...models.schema import CIDOCProperty
        invalid_props = CIDOCProperty.objects.filter(id__in=invalid_prop_ids)
    
    if invalid_props:
        invalid_prop = invalid_props[0]
        invalid_entity_prop = CIDOCEntityProperty(
            entity=real_entity,
            cidoc_property=invalid_prop,
            value_data='Test Value'
        )
        
        # Should raise validation error
        with pytest.raises(ValidationError):
            invalid_entity_prop.clean()

@pytest.mark.django_db
def test_permission_read_access_real(real_entity, real_property, test_user, test_group):
    """Test read permissions with real entities and users"""
    # Create property with no permissions
    prop = CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Initially user should not have access
    assert not prop.user_can_read(test_user), "User should not have read access without permissions"
    
    # Add group access
    test_user.groups.add(test_group)
    prop.readable_by_groups.add(test_group)
    
    # User should now have access through group
    assert prop.user_can_read(test_user), "User should have read access through group membership"
    
    # Remove group access
    prop.readable_by_groups.remove(test_group)
    
    # Add direct user access
    prop.readable_by_users.add(test_user)
    
    # User should have direct access
    assert prop.user_can_read(test_user), "User should have direct read access"

@pytest.mark.django_db
def test_permission_write_access_real(real_entity, real_property, test_user, test_group):
    """Test write permissions with real entities and users"""
    # Create property with no permissions
    prop = CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Initially user should not have access
    assert not prop.user_can_write(test_user), "User should not have write access without permissions"
    
    # Add group access
    test_user.groups.add(test_group)
    prop.writable_by_groups.add(test_group)
    
    # User should now have access through group
    assert prop.user_can_write(test_user), "User should have write access through group membership"
    
    # Remove group access
    prop.writable_by_groups.remove(test_group)
    
    # Add direct user access
    prop.writable_by_users.add(test_user)
    
    # User should have direct access
    assert prop.user_can_write(test_user), "User should have direct write access"

@pytest.mark.django_db
def test_superuser_permissions_real(real_entity_with_property, test_superuser):
    """Test that superuser has all permissions with real entities"""
    # Get the property
    prop = CIDOCEntityProperty.objects.filter(entity=real_entity_with_property).first()
    assert prop is not None, "Test entity should have a property"
    
    # Superuser should have all permissions
    assert prop.user_can_read(test_superuser), "Superuser should have read access"
    assert prop.user_can_write(test_superuser), "Superuser should have write access"
    
    # Even if we explicitly try to deny access (which we shouldn't do in practice)
    # Superuser should still have access
    prop.readable_by_users.clear()
    prop.writable_by_users.clear()
    prop.readable_by_groups.clear()
    prop.writable_by_groups.clear()
    
    assert prop.user_can_read(test_superuser), "Superuser should always have read access"
    assert prop.user_can_write(test_superuser), "Superuser should always have write access"

@pytest.mark.django_db
def test_property_value_retrieval(real_entity, real_property):
    """Test property value getter/setter with real entities"""
    # Create property
    prop = CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Initial Value'
    )
    
    # Test getter
    assert prop.value == 'Initial Value', "Property getter returned incorrect value"
    
    # Test setter
    prop.value = 'Updated Value'
    prop.save()
    
    # Verify update
    prop_reloaded = CIDOCEntityProperty.objects.get(pk=prop.pk)
    assert prop_reloaded.value == 'Updated Value', "Property update failed"

@pytest.mark.django_db
def test_property_nullability(real_entity, real_property):
    """Test that property values can be null"""
    # Create property with null value
    prop = CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data=None
    )
    
    # Verify null value
    assert prop.value is None, "Property value should be None"
    
    # Update to non-null and back to null
    prop.value = 'Temporary Value'
    prop.save()
    
    prop.value = None
    prop.save()
    
    # Verify null again
    prop_reloaded = CIDOCEntityProperty.objects.get(pk=prop.pk)
    assert prop_reloaded.value is None, "Property should allow null values"

@pytest.mark.django_db
def test_entity_node_id_not_required(real_entity_with_property):
    """Test that age_node_id is optional for property instances"""
    # Get the property
    prop = CIDOCEntityProperty.objects.filter(entity=real_entity_with_property).first()
    assert prop is not None, "Test entity should have a property"
    
    # Verify graph node ID is null (since we disabled graph operations)
    assert prop.age_node_id is None or prop.age_node_id == '', "Graph node ID should be null"
    
    # Should still work normally
    prop.value = "Updated through null node test"
    prop.save()
    
    # Verify update worked
    updated_prop = CIDOCEntityProperty.objects.get(pk=prop.pk)
    assert updated_prop.value == "Updated through null node test", "Property update should work without graph node ID" 