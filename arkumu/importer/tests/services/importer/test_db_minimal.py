
from arkumu.metadata.models.resource import Resource, ResourceType

import pytest

@pytest.mark.django_db

def test_simple_resource_creation():
    print("Testing simple resource creation...")
    
    try:
        print("1. Testing Resource.objects.create()...")
        resource = Resource.objects.create(
            uri="http://test.example.com/test1",
            resource_type=ResourceType.PROPERTY,
            name="test_property",
            source="TEST",
            is_placeholder=False
        )
        print(f"   ✅ Created resource with ID: {resource.id}")
        
        print("2. Testing Resource.objects.get_or_create()...")
        resource2, created = Resource.objects.get_or_create(
            uri="http://test.example.com/test2",
            defaults={
                "resource_type": ResourceType.PROPERTY,
                "name": "test_property2",
                "source": "TEST",
                "is_placeholder": False
            }
        )
        print(f"   ✅ get_or_create result: created={created}, ID={resource2.id}")
        
        print("3. Testing Resource.objects.update_or_create()...")
        resource3, created = Resource.objects.update_or_create(
            uri="http://test.example.com/test3",
            defaults={
                "resource_type": ResourceType.PROPERTY,
                "name": "test_property3",
                "source": "TEST",
                "is_placeholder": False
            }
        )
        print(f"   ✅ update_or_create result: created={created}, ID={resource3.id}")
        
        print("✅ All database operations completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_resource_creation() 