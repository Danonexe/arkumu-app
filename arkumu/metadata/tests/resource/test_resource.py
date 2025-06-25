import pytest
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType

@pytest.mark.django_db
def test_create_resource(db):
    """Test creating a resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/1",
        source="test",
        resource_type=ResourceType.IRI
    )
    assert resource.id is not None
    assert resource.uri == "http://example.org/resource/1"
    assert resource.source == "test"
    assert resource.resource_type == ResourceType.IRI
    assert resource.value is None
    
@pytest.mark.django_db
def test_create_literal_resource(db):
    """Test creating a literal resource."""
    resource = Resource.objects.create(
        source="test",
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        language="en"
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.LITERAL
    assert resource.value == "Test Value"
    assert resource.datatype == "xsd:string"
    assert resource.language == "en"

@pytest.mark.django_db
def test_update_resource(db):
    """Test updating a resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/2",
        source="original",
        resource_type=ResourceType.IRI
    )
    
    resource.source = "updated"
    resource.save()
    
    updated_resource = Resource.objects.get(id=resource.id)
    assert updated_resource.source == "updated"

@pytest.mark.django_db
def test_source_field_compatibility(db):
    """Test the compatibility with alternative field names."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/source-field-test",
        source="FUK",
        resource_type=ResourceType.IRI
    )
    
    assert resource.source == "FUK"
    
    # Test updating just the source
    resource.source = "Updated_FUK"
    resource.save()
    
    updated = Resource.objects.get(id=resource.id)
    assert updated.source == "Updated_FUK"

@pytest.mark.django_db
def test_delete_resource(db):
    """Test deleting a resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/3",
        source="test",
        resource_type=ResourceType.IRI
    )
    
    resource_id = resource.id
    resource.delete()
    
    with pytest.raises(Resource.DoesNotExist):
        Resource.objects.get(id=resource_id)

@pytest.mark.django_db
def test_resource_str_non_literal(db):
    """Test string representation of a non-literal resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/4",
        source="test",
        resource_type=ResourceType.IRI
    )
    assert str(resource) == "http://example.org/resource/4"

@pytest.mark.django_db
def test_resource_str_literal_simple(db):
    """Test string representation of a simple literal resource."""
    resource = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Simple Value"
    )
    assert str(resource) == '"Simple Value"'

@pytest.mark.django_db
def test_resource_str_literal_with_datatype(db):
    """Test string representation with datatype."""
    resource = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="42",
        datatype="xsd:integer"
    )
    assert str(resource) == '"42"^^xsd:integer'

@pytest.mark.django_db
def test_resource_str_literal_with_language(db):
    """Test string representation with language."""
    resource = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Bonjour",
        language="fr"
    )
    assert str(resource) == '"Bonjour"@fr'

@pytest.mark.django_db
def test_unique_uri_constraint(db):
    """Test that URIs must be unique."""
    Resource.objects.create(
        uri="http://example.org/resource/unique",
        source="test",
        resource_type=ResourceType.IRI
    )
    
    with pytest.raises(Exception):
        Resource.objects.create(
            uri="http://example.org/resource/unique",
            source="another test",
            resource_type=ResourceType.IRI
        )

@pytest.mark.django_db
def test_class_resource_creation(db):
    """Test creating a class resource."""
    resource = Resource.objects.create(
        uri="http://example.org/class/Person",
        source="test",
        resource_type=ResourceType.CLASS
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.CLASS
    assert resource.uri == "http://example.org/class/Person"

@pytest.mark.django_db
def test_property_resource_creation(db):
    """Test creating a property resource."""
    resource = Resource.objects.create(
        uri="http://example.org/property/hasName",
        source="test",
        resource_type=ResourceType.PROPERTY
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.PROPERTY
    assert resource.uri == "http://example.org/property/hasName"

@pytest.mark.django_db
def test_resource_type_constraint_validation(db):
    """Test constraint validation for resource types."""
    # This should fail - LITERAL without value
    with pytest.raises(Exception):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL
        )
    
    # This should fail - Non-LITERAL without URI
    with pytest.raises(Exception):
        Resource.objects.create(
            resource_type=ResourceType.IRI,
            uri=None
        )
