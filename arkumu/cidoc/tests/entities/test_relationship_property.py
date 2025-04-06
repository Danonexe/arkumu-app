import pytest
from django.core.exceptions import ValidationError
from ...models.entities import CIDOCRelationshipProperty
from ...models.schema import CIDOCProperty

@pytest.mark.django_db
def test_create_property_real(real_relationship, real_property):
    """Test basic property creation with real entities"""
    # Create a relationship property
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Verify property was created correctly
    assert prop.pk is not None, "Relationship property was not created"
    assert prop.value == 'Test Value', "Relationship property has incorrect value"
    
    # Verify we can retrieve it from the database
    saved_prop = CIDOCRelationshipProperty.objects.get(pk=prop.pk)
    assert saved_prop.value == 'Test Value', "Retrieved property has incorrect value"

@pytest.mark.django_db
def test_invalid_value_type_real(real_relationship, loaded_cidoc_data):
    """Test validation of property value type with real entities"""
    # Find a number-type property
    number_property = CIDOCProperty.objects.filter(
        range_class__class_id__startswith='E60'  # Number type
    ).first()
    
    if not number_property:
        pytest.skip("No number properties available for testing")
    
    # Try to create property with invalid value
    prop = CIDOCRelationshipProperty(
        relationship=real_relationship,
        cidoc_property=number_property
    )
    
    # This should raise validation error
    with pytest.raises(ValidationError):
        prop.value = "not a number"
        prop.full_clean()

@pytest.mark.django_db
def test_clean_validation_real(real_relationship, real_property):
    """Test clean method validations with real entities"""
    # Create property
    prop = CIDOCRelationshipProperty(
        relationship=real_relationship,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Should validate successfully
    prop.clean()
    
    # Test with invalid domain
    # Find a property not valid for this relationship
    source_class = real_relationship.source.crm_class
    target_class = real_relationship.target.crm_class
    
    invalid_props = CIDOCProperty.objects.filter(
        domain_class__isnull=False,
        range_class__isnull=False
    ).exclude(
        domain_class__class_id=source_class
    ).exclude(
        domain_class__parent_classes__class_id=source_class
    )
    
    if invalid_props.exists():
        invalid_prop = invalid_props.first()
        invalid_rel_prop = CIDOCRelationshipProperty(
            relationship=real_relationship,
            cidoc_property=invalid_prop,
            value_data='Test Value'
        )
        
        # Should raise validation error
        with pytest.raises(ValidationError):
            invalid_rel_prop.clean()

@pytest.mark.django_db
def test_permission_read_access_real(real_relationship, real_property, test_user, test_group):
    """Test read permissions with real entities and users"""
    # Create property with no permissions
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
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
def test_permission_write_access_real(real_relationship, real_property, test_user, test_group):
    """Test write permissions with real entities and users"""
    # Create property with no permissions
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
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
def test_superuser_permissions_real(real_relationship, real_property, test_superuser):
    """Test that superuser has all permissions with real entities"""
    # Create a property
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
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
def test_property_value_retrieval_real(real_relationship, real_property):
    """Test property value getter/setter with real entities"""
    # Create property
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
        cidoc_property=real_property,
        value_data='Initial Value'
    )
    
    # Test getter
    assert prop.value == 'Initial Value', "Property getter returned incorrect value"
    
    # Test setter
    prop.value = 'Updated Value'
    prop.save()
    
    # Verify update
    prop_reloaded = CIDOCRelationshipProperty.objects.get(pk=prop.pk)
    assert prop_reloaded.value == 'Updated Value', "Property update failed"

@pytest.mark.django_db
def test_property_nullability_real(real_relationship, real_property):
    """Test that property values can be null"""
    # Create property with null value
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
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
    prop_reloaded = CIDOCRelationshipProperty.objects.get(pk=prop.pk)
    assert prop_reloaded.value is None, "Property should allow null values"

@pytest.mark.django_db
def test_relationship_property_cascade_delete(real_relationship, real_property):
    """Test that relationship properties are deleted when relationship is deleted"""
    # Create property
    prop = CIDOCRelationshipProperty.objects.create(
        relationship=real_relationship,
        cidoc_property=real_property,
        value_data='Test Value'
    )
    
    # Verify property exists
    property_id = prop.id
    relationship_id = real_relationship.id
    assert CIDOCRelationshipProperty.objects.filter(id=property_id).exists(), "Property should exist"
    
    # Delete relationship
    real_relationship.delete()
    
    # Verify property was cascade deleted
    assert not CIDOCRelationshipProperty.objects.filter(id=property_id).exists(), "Property should be deleted with relationship" 