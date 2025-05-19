import pytest
from django.core.exceptions import ValidationError
from arkumu.cidoc.models.resource import Resource, ResourceType

@pytest.mark.django_db
def test_create_resource(db):
    """Test creating a resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/1",
        source="test",
        source_field="original_id_123",
        resource_type=ResourceType.IRI
    )
    assert resource.id is not None
    assert resource.uri == "http://example.org/resource/1"
    assert resource.source == "test"
    assert resource.source_field == "original_id_123"
    assert resource.resource_type == ResourceType.IRI
    assert resource.literal_value is None
    
@pytest.mark.django_db
def test_create_literal_resource(db):
    """Test creating a literal resource."""
    resource = Resource.objects.create(
        source="test",
        source_field="original_value",
        resource_type=ResourceType.LITERAL,
        literal_value="Test Value",
        literal_datatype="xsd:string",
        literal_language="en"
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.LITERAL
    assert resource.source_field == "original_value"
    assert resource.literal_value == "Test Value"
    assert resource.literal_datatype == "xsd:string"
    assert resource.literal_language == "en"

@pytest.mark.django_db
def test_update_resource(db):
    """Test updating a resource."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/2",
        source="original",
        source_field="original_data",
        resource_type=ResourceType.IRI
    )
    
    resource.source = "updated"
    resource.source_field = "updated_data"
    resource.save()
    
    updated_resource = Resource.objects.get(id=resource.id)
    assert updated_resource.source == "updated"
    assert updated_resource.source_field == "updated_data"

@pytest.mark.django_db
def test_source_field(db):
    """Test the source_field attribute specifically."""
    resource = Resource.objects.create(
        uri="http://example.org/resource/source-field-test",
        source="FUK",
        source_field="Ereignistyp=Ausstellung",
        resource_type=ResourceType.IRI
    )
    
    assert resource.source_field == "Ereignistyp=Ausstellung"
    
    # Test updating just the source_field
    resource.source_field = "Ereignistyp=Performance"
    resource.save()
    
    updated = Resource.objects.get(id=resource.id)
    assert updated.source_field == "Ereignistyp=Performance"
    assert updated.source == "FUK"  # Original source shouldn't change

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
        literal_value="Simple Value"
    )
    assert str(resource) == '"Simple Value"'

@pytest.mark.django_db
def test_resource_str_literal_with_datatype(db):
    """Test string representation with datatype."""
    resource = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        literal_value="42",
        literal_datatype="xsd:integer"
    )
    assert str(resource) == '"42"^^xsd:integer'

@pytest.mark.django_db
def test_resource_str_literal_with_language(db):
    """Test string representation with language."""
    resource = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        literal_value="Bonjour",
        literal_language="fr"
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
        source_field="original_class",
        resource_type=ResourceType.CLASS
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.CLASS
    assert resource.uri == "http://example.org/class/Person"
    assert resource.source_field == "original_class"

@pytest.mark.django_db
def test_property_resource_creation(db):
    """Test creating a property resource."""
    resource = Resource.objects.create(
        uri="http://example.org/property/hasName",
        source="test",
        source_field="original_property",
        resource_type=ResourceType.PROPERTY
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.PROPERTY
    assert resource.uri == "http://example.org/property/hasName"
    assert resource.source_field == "original_property"

@pytest.mark.django_db
def test_resource_type_constraint_validation(db):
    """Test constraint validation for resource types."""
    # This should fail - LITERAL without literal_value
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
