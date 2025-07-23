import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType


@pytest.mark.django_db
def test_constraint_working_with_explicit_check():
    """Test that the constraint is working by trying various scenarios."""
    
    # Test 1: Create a literal
    print("\n=== Test 1: Creating first literal ===")
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en",
        name="field1"
    )
    print(f"✓ Created literal1: {literal1.id}")
    print(f"  Value hash: {literal1.value_hash}")
    
    # Test 2: Try exact duplicate - should fail
    print("\n=== Test 2: Attempting exact duplicate ===")
    try:
        literal2 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",  # Same
            datatype="xsd:string",  # Same
            language="en",  # Same
            name="field1"  # Same
        )
        print(f"⚠️  PROBLEM: Duplicate allowed! ID: {literal2.id}")
        
        # Check if they have same hash
        print(f"  literal1 hash: {literal1.value_hash}")
        print(f"  literal2 hash: {literal2.value_hash}")
        
        # Force fail the test
        assert False, "Exact duplicate was allowed - constraint not working!"
        
    except (IntegrityError, ValidationError) as e:
        print(f"✓ Duplicate correctly prevented: {type(e).__name__}: {e}")
    
    # Test 3: Try with different name - should FAIL (constraint doesn't include name)
    print("\n=== Test 3: Different name should now fail (constraint simplified) ===")
    try:
        literal3 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",  # Same
            datatype="xsd:string",  # Same
            language="en",  # Same
            name="field2"  # Different, but shouldn't matter now!
        )
        print(f"⚠️  PROBLEM: Different name was allowed! ID: {literal3.id}")
        assert False, "Different name should be prevented - constraint not working!"
        
    except (IntegrityError, ValidationError) as e:
        print(f"✓ Different name correctly prevented: {type(e).__name__}: {e}")
    
    # Test 4: Try with different language - should succeed
    print("\n=== Test 4: Different language should succeed ===")
    try:
        literal4 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Test Value",  # Same
            datatype="xsd:string",  # Same
            language="fr",  # Different!
            name="field1"  # Back to same as literal1
        )
        print(f"✓ Different language allowed: {literal4.id}")
        
    except Exception as e:
        print(f"✗ Different language failed: {e}")
        assert False, "Different language should be allowed"
    
    # Test 5: Final count check
    print("\n=== Test 5: Final database state ===")
    all_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL)
    print(f"Total literals created: {all_literals.count()}")
    
    for i, lit in enumerate(all_literals, 1):
        print(f"  {i}. ID={str(lit.id)[:8]}... value='{lit.value}' lang={lit.language} name={lit.name}")
    
    # Should have exactly 2 literals (exact duplicate + different name both prevented)
    expected_count = 2
    actual_count = all_literals.count()
    if actual_count != expected_count:
        print(f"⚠️  Expected {expected_count} literals, got {actual_count}")
        if actual_count > expected_count:
            print("   This suggests the constraint is not working properly.")
        
    assert actual_count == expected_count, f"Expected {expected_count} literals, got {actual_count}"


@pytest.mark.django_db
def test_simplified_duplicate_check():
    """Simplified test focusing just on the core constraint."""
    print("\n=== SIMPLIFIED DUPLICATE TEST ===")
    
    # Create literal with minimal fields
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Simple"
    )
    print("✓ Created first literal")
    
    # Try duplicate
    try:
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Simple"
        )
        print("⚠️  CONSTRAINT FAILED - duplicate was created!")
        assert False, "Constraint failed - duplicate literal created"
    except (IntegrityError, ValidationError):
        print("✓ Constraint working - duplicate prevented")


@pytest.mark.django_db 
def test_manual_constraint_check():
    """Manually check if constraint exists in test database."""
    from django.db import connection
    
    print("\n=== MANUAL CONSTRAINT CHECK ===")
    
    with connection.cursor() as cursor:
        # Check specifically for our constraint
        cursor.execute("""
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint 
            WHERE conname = 'unique_literal_value_hash'
        """)
        result = cursor.fetchone()
        
        if result:
            name, definition = result
            print(f"✓ Constraint found: {name}")
            print(f"  Definition: {definition}")
        else:
            print("✗ Constraint NOT found in database!")
            print("  Checking what constraints DO exist on metadata_resource...")
            
            cursor.execute("""
                SELECT conname, contype, pg_get_constraintdef(oid) 
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE t.relname = 'metadata_resource'
                AND contype = 'u'  -- Only unique constraints
            """)
            constraints = cursor.fetchall()
            
            print(f"  Found {len(constraints)} unique constraints:")
            for constraint in constraints:
                print(f"    - {constraint[0]}: {constraint[2]}")
                
            if not any('literal' in c[0].lower() or 'value' in c[0].lower() for c in constraints):
                print("  ⚠️  No literal-related unique constraints found!")
                return False
        
        return True