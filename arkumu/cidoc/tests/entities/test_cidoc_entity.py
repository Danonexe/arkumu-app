import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.models.entities import CIDOCEntity, CIDOCEntityProperty, CIDOCRelationship
from arkumu.cidoc.validators import validate_cidoc_relationship
# PermissionError is a built-in Python exception

@pytest.mark.django_db
def test_entity_creation(loaded_cidoc_data, test_user):
    """Test basic entity creation with a valid CIDOC class"""
    # Find a valid CIDOC class
    valid_class = CIDOCClass.objects.first()
    assert valid_class is not None, "No CIDOC classes found in database"
    
    # Create entity with valid class
    entity = CIDOCEntity.objects.create(
        crm_class=valid_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Verify entity was created with correct class
    assert entity.pk is not None, "Entity was not created"
    assert entity.crm_class == valid_class.class_id, "Entity has incorrect class"
    assert entity.age_node_id is None, "Entity should not have a graph node ID when graph is disabled"
    
    # Clean up
    entity.delete()

@pytest.mark.django_db
def test_entity_with_invalid_class(loaded_cidoc_data):
    """Test that creating an entity with invalid class raises error"""
    # Try to create entity with invalid class
    with pytest.raises(ValidationError):
        entity = CIDOCEntity(
            crm_class='E999_NonExistentClass'
        )
        entity.full_clean()  # This should raise ValidationError

@pytest.mark.django_db
def test_entity_string_representation(real_entity):
    """Test entity string representation without properties"""
    # Default string representation
    entity_str = str(real_entity)
    assert real_entity.crm_class in entity_str, "Entity string does not include class ID"
    
    # Entity should have a representation even without properties
    assert "Unnamed" in entity_str or real_entity.crm_class in entity_str, "Entity string missing expected content"

@pytest.mark.django_db
def test_entity_with_identifier_property(loaded_cidoc_data, test_user):
    """Test entity with identifier property (P1)"""
    # Create an E1 entity which supports P1 property
    e1_class = CIDOCClass.objects.get(class_id='E1')
    
    entity = CIDOCEntity.objects.create(
        crm_class=e1_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Get the P1 property
    p1_property = CIDOCProperty.objects.get(property_id='P1')
    
    # Create entity property with P1
    entity_property = CIDOCEntityProperty.objects.create(
        entity=entity,
        cidoc_property=p1_property,
        value_data="Test Entity",
        created_by=test_user,
        updated_by=test_user
    )
    
    # Debug information
    print(f"Created property: {entity_property.id}")
    print(f"Property value_data: {entity_property.value_data}")
    print(f"Property cidoc_property_id: {entity_property.cidoc_property.property_id}")
    
    # Query to check if property exists
    props = entity.cidocentityproperty_set.all()
    print(f"Number of properties found: {props.count()}")
    for prop in props:
        print(f"Found property: {prop.cidoc_property.property_id}, value: {prop.value_data}")
    
    # Get property using the exact same query as in __str__
    name_prop = entity.cidocentityproperty_set.filter(
        cidoc_property__property_id='P1'
    ).first()
    print(f"name_prop using P1 filter: {name_prop}")
    print(f"name_prop value: {name_prop.value_data if name_prop else 'None'}")
    
    # Test string representation
    assert str(entity) == "E1: Test Entity", "Entity string representation should include property value"
    
    # Create an entity without the property
    entity2 = CIDOCEntity.objects.create(
        crm_class=e1_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Test string representation falls back to unnamed
    assert str(entity2) == "E1: Unnamed", "Entity string representation should fall back to 'Unnamed'"

@pytest.mark.django_db
def test_entity_valid_properties(real_entity):
    """Test getting valid properties for entity"""
    # Get valid properties for the entity
    valid_props = real_entity.get_valid_properties()
    
    # There should be at least one valid property
    assert len(valid_props) > 0, "Entity has no valid properties"
    
    # Valid properties should include some standard ones like P1 (identifier)
    property_ids = [p.property_id for p in valid_props]
    assert any(p.startswith('P') for p in property_ids), "No standard properties found"
    
    # Print some debug info
    print(f"\nEntity class: {real_entity.crm_class}")
    print(f"First few valid properties: {property_ids[:5]}")

@pytest.mark.django_db
def test_entity_property_creation(loaded_cidoc_data, test_user):
    """Test entity property creation and validation"""
    # Create an E1 entity which supports P1 property
    e1_class = CIDOCClass.objects.get(class_id='E1')
    
    entity = CIDOCEntity.objects.create(
        crm_class=e1_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Get the P1 property
    p1_property = CIDOCProperty.objects.get(property_id='P1')
    
    # Create entity property with P1
    entity_property = CIDOCEntityProperty.objects.create(
        entity=entity,
        cidoc_property=p1_property,
        value_data="Test Value",
        created_by=test_user,
        updated_by=test_user
    )
    
    # Verify property creation
    assert entity_property.value == "Test Value", "Property value does not match expected"
    
    # Test property retrieval via reverse relationship
    entity_properties = entity.cidocentityproperty_set.all()
    assert len(entity_properties) == 1, "Entity should have one property"
    assert entity_properties[0].value == "Test Value", "Retrieved property value should match"
    
    # Test unique constraint
    with pytest.raises(ValidationError):
        # Attempt to create duplicate property should fail
        duplicate_prop = CIDOCEntityProperty(
            entity=entity,
            cidoc_property=p1_property,
            value_data="Another Value", 
            created_by=test_user,
            updated_by=test_user
        )
        duplicate_prop.full_clean()  # This should raise the validation error

@pytest.mark.django_db
def test_entity_property_validation(real_entity, real_property):
    """Test validation of entity properties"""
    # Create an entity property
    entity_prop = CIDOCEntityProperty(
        entity=real_entity,
        cidoc_property=real_property
    )
    
    # Test validation only if the property has a defined range class
    if real_property.range_class:
        # Test with invalid value (assuming real_property is a string type)
        if real_property.range_class.class_id.startswith('E60'):  # Number type
            # Should raise validation error with non-numeric string
            with pytest.raises(ValidationError):
                entity_prop.value = "not a number"
                entity_prop.full_clean()
        
        # Test with valid value
        if real_property.range_class.class_id.startswith('E62'):  # String type
            entity_prop.value = "Valid string value"
            entity_prop.full_clean()  # Should not raise exception
            assert entity_prop.value == "Valid string value"
    else:
        # If range_class is None, it's likely a literal. Test with a string.
        entity_prop.value = "Literal Value"
        entity_prop.full_clean() # Should not raise validation error
        assert entity_prop.value == "Literal Value", "Validation failed for literal property"

@pytest.mark.django_db
def test_entity_relationship(loaded_cidoc_data, test_user):
    """Test creation of relationships between entities"""
    # Find valid classes for a specific relationship
    # P7 (took place at) typically connects E5 (Event) to E53 (Place)
    e5_class = CIDOCClass.objects.get(class_id='E5')  # Event
    e53_class = CIDOCClass.objects.get(class_id='E53')  # Place
    
    # Create source entity (Event)
    event_entity = CIDOCEntity.objects.create(
        crm_class=e5_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Create target entity (Place)
    place_entity = CIDOCEntity.objects.create(
        crm_class=e53_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Create the relationship - the inverse will be created automatically
    relationship = CIDOCRelationship.objects.create(
        source=event_entity,
        target=place_entity,
        relation_type='P7',
        created_by=test_user,
        updated_by=test_user
    )
    
    # Check that both relationships were created
    assert relationship.source == event_entity
    assert relationship.target == place_entity
    assert relationship.relation_type == 'P7'
    
    # Verify the inverse relationship was created
    inverse_relationship = place_entity.outgoing_relationships.get(relation_type='P7i')
    assert inverse_relationship.source == place_entity
    assert inverse_relationship.target == event_entity
    assert inverse_relationship.relation_type == 'P7i'
    
    # Test relationship string representation
    assert str(relationship) == f"{e5_class.class_id} --P7--> {e53_class.class_id}"
    
    # Test fetching relationships through related manager
    outgoing = event_entity.outgoing_relationships.all()
    incoming = place_entity.incoming_relationships.all()
    
    assert len(outgoing) == 1, "Event should have one outgoing relationship"
    assert len(incoming) == 1, "Place should have one incoming relationship"
    assert outgoing[0] == relationship, "Incorrect outgoing relationship"
    assert incoming[0] == relationship, "Incorrect incoming relationship"

@pytest.mark.django_db
def test_entity_deletion(loaded_cidoc_data, test_user):
    """Test entity deletion cascades properly"""
    # Find a valid CIDOC class for P1 property (should be E1)
    e1_class = CIDOCClass.objects.get(class_id='E1')
    
    # Create entity
    entity = CIDOCEntity.objects.create(
        crm_class=e1_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Add a property to the entity
    property = CIDOCProperty.objects.get(property_id='P1')
    entity_prop = CIDOCEntityProperty.objects.create(
        entity=entity,
        cidoc_property=property,
        value_data="Test Value",
        created_by=test_user,
        updated_by=test_user
    )
    
    # Delete the entity
    entity_id = entity.id
    entity.delete()
    
    # Verify entity was deleted
    assert not CIDOCEntity.objects.filter(id=entity_id).exists(), "Entity was not deleted"
    
    # Verify property was cascade deleted
    assert not CIDOCEntityProperty.objects.filter(entity_id=entity_id).exists(), "Entity property was not deleted"

@pytest.mark.django_db
def test_get_set_property_methods(loaded_cidoc_data, test_user, test_superuser):
    """Test get_property and set_property methods"""
    # Create an E1 entity which supports P1 property
    e1_class = CIDOCClass.objects.get(class_id='E1')
    
    entity = CIDOCEntity.objects.create(
        crm_class=e1_class.class_id,
        created_by=test_user,
        updated_by=test_user
    )
    
    # Use P1 property for testing
    p1_property = CIDOCProperty.objects.get(property_id='P1')
    
    # Set a property as superuser
    prop = entity.set_property(test_superuser, p1_property.property_id, "Test Value")
    
    # Verify property was set
    assert prop is not None, "Property was not set"
    assert prop.value == "Test Value", "Property has incorrect value"
    
    # Get the property as normal user (should fail without permissions)
    value = entity.get_property(test_user, p1_property.property_id)
    assert value is None, "User without permissions should not be able to read property"
    
    # Add read permission to the user
    prop.readable_by_users.add(test_user)
    
    # Now user should be able to read
    value = entity.get_property(test_user, p1_property.property_id)
    assert value == "Test Value", "User with permissions should be able to read property"
    
    # Try to set property as normal user (should fail without permissions)
    try:
        entity.set_property(test_user, p1_property.property_id, "New Value")
        assert False, "User without permissions should not be able to set property"
    except PermissionError:
        # Expected behavior
        pass
    
    # Add write permission to the user
    prop.writable_by_users.add(test_user)
    
    # Now user should be able to write
    new_prop = entity.set_property(test_user, p1_property.property_id, "New Value")
    assert new_prop.value == "New Value", "User with permissions should be able to set property" 