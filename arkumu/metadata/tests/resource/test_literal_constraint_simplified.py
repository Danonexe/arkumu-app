import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType


@pytest.mark.django_db
def test_literal_constraint_exact_duplicate():
    """Test that exact duplicates are prevented."""
    # Create a literal
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string", 
        language="en",
        name="field1"
    )
    
    # Try exact duplicate - should fail
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",  # Same
            datatype="xsd:string",  # Same
            language="en",  # Same
            name="field1"  # Same
        )


@pytest.mark.django_db
def test_literal_constraint_different_name_prevented():
    """Test that different name but same hash/language/datatype is prevented."""
    # Create a literal
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en", 
        name="field1"
    )
    
    # Try with different name - should fail (constraint doesn't include name)
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",  # Same hash
            datatype="xsd:string",  # Same
            language="en",  # Same
            name="field2"  # Different, but shouldn't matter!
        )


@pytest.mark.django_db
def test_literal_constraint_different_language_allowed():
    """Test that different language is allowed."""
    # Create first literal
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en",
        name="field1"
    )
    
    # Different language should succeed
    literal2 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",  # Same hash
        datatype="xsd:string",  # Same
        language="fr",  # Different!
        name="field1"
    )
    
    assert literal1.id != literal2.id
    assert literal1.language == "en"
    assert literal2.language == "fr"


@pytest.mark.django_db
def test_literal_constraint_different_datatype_allowed():
    """Test that different datatype is allowed."""
    # Create first literal
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en",
        name="field1"
    )
    
    # Different datatype should succeed
    literal2 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",  # Same hash
        datatype="custom:text",  # Different!
        language="en",  # Same
        name="field1"
    )
    
    assert literal1.id != literal2.id
    assert literal1.datatype == "xsd:string"
    assert literal2.datatype == "custom:text"


@pytest.mark.django_db
def test_constraint_covers_hash_language_datatype():
    """Test that the constraint specifically covers (value_hash, language, datatype)."""
    
    # Create base literal
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Base Value",
        datatype="xsd:string",
        language=None,
        name="original_name"
    )
    
    # Same hash, language, datatype but different name -> should fail
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Base Value",  # Same hash
            datatype="xsd:string",  # Same
            language=None,  # Same  
            name="different_name"  # Different (but constraint ignores this)
        )
    
    # Different hash -> should succeed
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Different Value",  # Different hash
        datatype="xsd:string", 
        language=None,
        name="original_name"  # Even with same name as first
    )
    
    # Different language -> should succeed
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Base Value",  # Same hash as first
        datatype="xsd:string",
        language="en",  # Different language
        name="original_name"
    )
    
    # Different datatype -> should succeed  
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Base Value",  # Same hash as first
        datatype="custom:string",  # Different datatype
        language=None,
        name="original_name"
    )
    
    # Should have exactly 4 literals total
    count = Resource.objects.filter(resource_type=ResourceType.LITERAL).count()
    assert count == 4


@pytest.mark.django_db 
def test_constraint_exists_in_database():
    """Verify that the constraint actually exists in the test database."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check specifically for our constraint
        cursor.execute("""
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint 
            WHERE conname = 'unique_literal_value_hash'
        """)
        result = cursor.fetchone()
        
        assert result is not None, "Constraint 'unique_literal_value_hash' not found in database!"
        
        name, definition = result
        assert name == 'unique_literal_value_hash'
        
        # Check that the constraint covers the right fields
        assert 'value_hash' in definition
        assert 'language' in definition  
        assert 'datatype' in definition
        # Should NOT include 'name' in the new simplified constraint
        assert 'name' not in definition or definition.count('name') == 0
        
        print(f"✓ Constraint found: {name}")
        print(f"  Definition: {definition}")