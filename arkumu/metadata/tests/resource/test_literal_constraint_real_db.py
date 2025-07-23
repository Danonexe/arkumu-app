import pytest
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.users.models import Organization


@pytest.mark.django_db(transaction=True)
def test_literal_constraint_with_real_db():
    """Test literal constraint using real database with transactions."""
    print("\n=== LITERAL CONSTRAINT TEST WITH REAL DB ===")
    
    # Create an organization for testing
    org = Organization.objects.create(
        name="Test Organization",
        code="TEST"
    )
    
    # Create first literal
    print("\n1. Creating first literal...")
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Constraint Value",
        datatype="xsd:string",
        language="en",
        organization=org
    )
    print(f"✓ Created literal1: {literal1.id}")
    print(f"  Value hash: {literal1.value_hash}")
    
    # Try to create exact duplicate - this should fail with IntegrityError
    print("\n2. Attempting to create exact duplicate...")
    try:
        with transaction.atomic():
            literal2 = Resource.objects.create(
                resource_type=ResourceType.LITERAL,
                value="Test Constraint Value",  # Same value
                datatype="xsd:string",  # Same datatype  
                language="en",  # Same language
                # name=None (same as literal1)
                organization=org
            )
            print(f"⚠️  PROBLEM: Duplicate created! ID: {literal2.id}")
            print(f"  This means the constraint is NOT working!")
            
            # Clean up the duplicate for next test
            literal2.delete()
            assert False, "Constraint failed - duplicate literal was created!"
            
    except (IntegrityError, ValidationError) as e:
        print(f"✓ Constraint working! Duplicate prevented: {type(e).__name__}: {e}")
    
    # Test that different values are allowed
    print("\n3. Testing that different values are allowed...")
    try:
        literal3 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Different Value",  # Different value
            datatype="xsd:string",
            language="en", 
            organization=org
        )
        print(f"✓ Different value allowed: {literal3.id}")
        
        # Clean up
        literal3.delete()
        
    except Exception as e:
        print(f"✗ Different value failed unexpectedly: {e}")
        assert False, "Different values should be allowed"
    
    # Clean up the first literal
    literal1.delete()
    org.delete()


@pytest.mark.django_db(transaction=True)
def test_constraint_components():
    """Test each component of the uniqueness constraint."""
    print("\n=== TESTING CONSTRAINT COMPONENTS ===")
    
    org = Organization.objects.create(name="Test Org", code="TEST2")
    
    # Create base literal
    base_literal = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Base Value",
        datatype="xsd:string",
        language="en",
        name="field1",
        organization=org
    )
    print(f"✓ Created base literal: {base_literal.id}")
    
    # Test variations that should be allowed
    variations = [
        {"value": "Base Value", "datatype": "xsd:integer", "language": "en", "name": "field1"},  # Different datatype
        {"value": "Base Value", "datatype": "xsd:string", "language": "fr", "name": "field1"},  # Different language  
        {"value": "Base Value", "datatype": "xsd:string", "language": "en", "name": "field2"},  # Different name
        {"value": "Base Value", "datatype": "xsd:string", "language": "en", "name": None},      # No name
    ]
    
    created_literals = []
    
    for i, variation in enumerate(variations, 1):
        print(f"\n  Testing variation {i}: {variation}")
        try:
            literal = Resource.objects.create(
                resource_type=ResourceType.LITERAL,
                organization=org,
                **variation
            )
            print(f"    ✓ Allowed: {literal.id}")
            created_literals.append(literal)
            
        except (IntegrityError, ValidationError) as e:
            print(f"    ✗ Unexpectedly blocked: {e}")
            assert False, f"Variation {i} should be allowed but was blocked"
    
    # Now test exact duplicate - should fail
    print(f"\n  Testing exact duplicate...")
    try:
        with transaction.atomic():
            duplicate = Resource.objects.create(
                resource_type=ResourceType.LITERAL,
                value="Base Value",  # Same as base
                datatype="xsd:string",  # Same as base
                language="en",  # Same as base
                name="field1",  # Same as base
                organization=org
            )
            print(f"    ⚠️  PROBLEM: Exact duplicate allowed! ID: {duplicate.id}")
            duplicate.delete()
            assert False, "Exact duplicate should have been prevented"
            
    except (IntegrityError, ValidationError):
        print(f"    ✓ Exact duplicate correctly prevented")
    
    # Cleanup
    for literal in created_literals + [base_literal]:
        literal.delete()
    org.delete()
    
    print(f"\n✓ All constraint component tests passed!")


@pytest.mark.django_db(transaction=True) 
def test_minimal_duplicate_prevention():
    """Minimal test for duplicate prevention."""
    print("\n=== MINIMAL DUPLICATE TEST ===")
    
    # Create literal with minimal fields
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Minimal Test"
    )
    print(f"✓ Created literal1: {literal1.id}")
    print(f"  Hash: {literal1.value_hash}")
    print(f"  Datatype: {literal1.datatype}")
    print(f"  Language: {literal1.language}")
    print(f"  Name: {literal1.name}")
    
    # Try exact duplicate
    try:
        with transaction.atomic():
            literal2 = Resource.objects.create(
                resource_type=ResourceType.LITERAL,
                value="Minimal Test"  # Exact same value, all other fields None
            )
            print(f"⚠️  CONSTRAINT NOT WORKING: Duplicate created with ID {literal2.id}")
            print(f"  Hash: {literal2.value_hash}")
            
            # Show both literals exist
            all_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL, value="Minimal Test")
            print(f"  Total literals with this value: {all_literals.count()}")
            
            # Cleanup
            literal2.delete()
            literal1.delete()
            
            assert False, "Minimal duplicate should have been prevented by constraint"
            
    except (IntegrityError, ValidationError) as e:
        print(f"✓ Constraint working: {type(e).__name__}: {e}")
        literal1.delete()  # Cleanup