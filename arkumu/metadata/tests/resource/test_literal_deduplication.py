import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType
import hashlib


@pytest.mark.django_db
def test_literal_deduplication_investigation():
    """Investigate whether literal deduplication is working as expected."""
    print("\n=== LITERAL DEDUPLICATION INVESTIGATION ===")
    
    # Create first literal
    print("\n1. Creating first literal...")
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Hello World",
        datatype="xsd:string",
        language="en"
    )
    print(f"   ✓ Created literal1: ID={literal1.id}")
    print(f"   Value: '{literal1.value}'")
    print(f"   Value Hash: {literal1.value_hash}")
    print(f"   Datatype: {literal1.datatype}")
    print(f"   Language: {literal1.language}")
    print(f"   Name: {literal1.name}")
    
    # Check what's in database
    all_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL)
    print(f"\n   Database state: {all_literals.count()} literals")
    
    # Attempt to create duplicate
    print("\n2. Attempting to create duplicate literal...")
    try:
        literal2 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Hello World",
            datatype="xsd:string", 
            language="en"
        )
        print(f"   ⚠️  PROBLEM: Created literal2: ID={literal2.id} (DUPLICATE WAS ALLOWED!)")
        print(f"   Value: '{literal2.value}'")
        print(f"   Value Hash: {literal2.value_hash}")
        print(f"   Datatype: {literal2.datatype}")
        print(f"   Language: {literal2.language}")
        print(f"   Name: {literal2.name}")
        
        # Check final database state
        all_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL)
        print(f"\n   Final database state: {all_literals.count()} literals")
        for i, lit in enumerate(all_literals, 1):
            print(f"   Literal {i}: ID={lit.id}, Value='{lit.value}', Hash={lit.value_hash}")
            
        # This should not happen if deduplication is working
        assert False, "Duplicate literal was created when it should have been prevented!"
        
    except (IntegrityError, ValidationError) as e:
        print(f"   ✓ Duplicate correctly prevented: {e}")
        
        # Check final database state 
        all_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL)
        print(f"\n   Final database state: {all_literals.count()} literals")
        assert all_literals.count() == 1


@pytest.mark.django_db
def test_exact_duplicate_fields():
    """Test that duplicate literals with identical fields are prevented."""
    # Create first literal with all identifying fields
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en",
        name="test_field"
    )
    
    # Attempt exact duplicate - should fail
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",
            datatype="xsd:string",
            language="en",
            name="test_field"
        )


@pytest.mark.django_db 
def test_hash_based_deduplication():
    """Test that the hash-based constraint is working."""
    value = "Hash Test Value"
    expected_hash = hashlib.sha256(value.encode('utf-8')).hexdigest()
    
    # Create first literal
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value=value,
        datatype="xsd:string"
    )
    
    assert literal1.value_hash == expected_hash
    
    # Attempt duplicate with same hash combination - should fail
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value=value,  # Same value = same hash
            datatype="xsd:string"  # Same datatype
            # Same language (None) and name (None)
        )


@pytest.mark.django_db
def test_unique_constraint_components():
    """Test each component of the uniqueness constraint: value_hash, language, datatype, name."""
    base_value = "Constraint Test"
    
    # These should all be allowed (different in at least one constraint field)
    variations = [
        # Different datatypes
        {"value": base_value, "datatype": "xsd:string", "language": None, "name": None},
        {"value": base_value, "datatype": "xsd:integer", "language": None, "name": None},
        
        # Different languages  
        {"value": base_value, "datatype": "xsd:string", "language": "en", "name": None},
        {"value": base_value, "datatype": "xsd:string", "language": "fr", "name": None},
        
        # Different names
        {"value": base_value, "datatype": "xsd:string", "language": None, "name": "field1"},
        {"value": base_value, "datatype": "xsd:string", "language": None, "name": "field2"},
    ]
    
    created_literals = []
    for i, variation in enumerate(variations):
        print(f"\nCreating variation {i+1}: {variation}")
        literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            **variation
        )
        created_literals.append(literal)
        print(f"   ✓ Created ID={literal.id}")
    
    # All should be unique
    assert len(created_literals) == len(variations)
    all_ids = [lit.id for lit in created_literals]
    assert len(set(all_ids)) == len(all_ids)
    
    print(f"\n✓ Successfully created {len(variations)} different literals")


@pytest.mark.django_db
def test_simple_duplicate_prevention():
    """Simplest possible test for duplicate prevention."""
    # Create one literal
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Simple Test"
    )
    
    # Try to create exact duplicate
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Simple Test"
        )


@pytest.mark.django_db
def test_database_constraint_exists():
    """Test that the database constraint actually exists."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check for the unique constraint
        cursor.execute("""
            SELECT conname, contype 
            FROM pg_constraint 
            WHERE conname = 'unique_literal_value_hash'
        """)
        constraints = cursor.fetchall()
        
        print(f"\nFound constraints: {constraints}")
        assert len(constraints) > 0, "unique_literal_value_hash constraint not found in database!"
        
        constraint_name, constraint_type = constraints[0]
        assert constraint_name == 'unique_literal_value_hash'
        assert constraint_type == 'u'  # 'u' for unique constraint


@pytest.mark.django_db
def test_null_handling_in_constraint():
    """Test how NULL values are handled in the uniqueness constraint."""
    # Create literal with minimal fields (name and language will be NULL)
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="NULL Test",
        datatype="xsd:string"
        # name=None, language=None (implicit)
    )
    
    print(f"\nCreated literal1: name={literal1.name}, language={literal1.language}")
    
    # Try to create another with same value, datatype, but NULL name/language
    # This should fail if constraint handles NULLs correctly
    with pytest.raises((IntegrityError, ValidationError)):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="NULL Test",
            datatype="xsd:string"
            # name=None, language=None (implicit)
        )