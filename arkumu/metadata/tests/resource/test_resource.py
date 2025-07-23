import pytest
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.users.models import Organization

@pytest.mark.django_db
def test_create_resource(db):
    """Test creating a resource."""
    test_org = Organization.objects.create(name="Test Org", code="test")
    resource = Resource.objects.create(
        uri="http://example.org/resource/1",
        organization=test_org,
        resource_type=ResourceType.IRI
    )
    assert resource.id is not None
    assert resource.uri == "http://example.org/resource/1"
    assert resource.organization.code == "test"
    assert resource.resource_type == ResourceType.IRI
    assert resource.value is None
    
@pytest.mark.django_db
def test_create_literal_resource(db):
    """Test creating a literal resource."""
    resource = Resource.objects.create(
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
    # Literals don't have organization since they get provenance from triples
    assert resource.organization is None

@pytest.mark.django_db
def test_update_resource(db):
    """Test updating a resource."""
    original_org = Organization.objects.create(name="Original Org", code="original")
    updated_org = Organization.objects.create(name="Updated Org", code="updated")
    resource = Resource.objects.create(
        uri="http://example.org/resource/2",
        organization=original_org,
        resource_type=ResourceType.IRI
    )
    
    resource.organization = updated_org
    resource.save()
    
    updated_resource = Resource.objects.get(id=resource.id)
    assert updated_resource.organization.code == "updated"

@pytest.mark.django_db
def test_organization_field(db):
    """Test the organization field functionality."""
    fuk_org = Organization.objects.create(name="Folkwang Universität der Künste", code="FUK")
    resource = Resource.objects.create(
        uri="http://example.org/resource/source-field-test",
        organization=fuk_org,
        resource_type=ResourceType.IRI
    )
    
    assert resource.organization.code == "FUK"
    
    # Test updating the organization
    updated_org = Organization.objects.create(name="Updated FUK", code="Updated_FUK")
    resource.organization = updated_org
    resource.save()
    
    updated = Resource.objects.get(id=resource.id)
    assert updated.organization.code == "Updated_FUK"

@pytest.mark.django_db
def test_delete_resource(db):
    """Test deleting a resource."""
    test_org = Organization.objects.create(name="Test Org", code="test")
    resource = Resource.objects.create(
        uri="http://example.org/resource/3",
        organization=test_org,
        resource_type=ResourceType.IRI
    )
    
    resource_id = resource.id
    resource.delete()
    
    with pytest.raises(Resource.DoesNotExist):
        Resource.objects.get(id=resource_id)

@pytest.mark.django_db
def test_resource_str_non_literal(db):
    """Test string representation of a non-literal resource."""
    test_org = Organization.objects.create(name="Test Org", code="test")
    resource = Resource.objects.create(
        uri="http://example.org/resource/4",
        organization=test_org,
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
    test_org = Organization.objects.create(name="Test Org", code="test")
    another_org = Organization.objects.create(name="Another Org", code="another")
    Resource.objects.create(
        uri="http://example.org/resource/unique",
        organization=test_org,
        resource_type=ResourceType.IRI
    )
    
    with pytest.raises(Exception):
        Resource.objects.create(
            uri="http://example.org/resource/unique",
            organization=another_org,
            resource_type=ResourceType.IRI
        )

@pytest.mark.django_db
def test_class_resource_creation(db):
    """Test creating a class resource."""
    test_org = Organization.objects.create(name="Test Org", code="test")
    resource = Resource.objects.create(
        uri="http://example.org/class/Person",
        organization=test_org,
        resource_type=ResourceType.CLASS
    )
    assert resource.id is not None
    assert resource.resource_type == ResourceType.CLASS
    assert resource.uri == "http://example.org/class/Person"

@pytest.mark.django_db
def test_property_resource_creation(db):
    """Test creating a property resource."""
    test_org = Organization.objects.create(name="Test Org", code="test")
    resource = Resource.objects.create(
        uri="http://example.org/property/hasName",
        organization=test_org,
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

@pytest.mark.django_db
def test_literal_deduplication_same_value_datatype_language(db):
    """Test that duplicate literals with same value, datatype, and language are prevented."""
    # Create first literal
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Hello World",
        datatype="xsd:string",
        language="en"
    )
    assert literal1.id is not None
    
    # Attempt to create duplicate literal - should raise IntegrityError
    with pytest.raises(Exception):  # Django will raise IntegrityError
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Hello World",
            datatype="xsd:string", 
            language="en"
        )

@pytest.mark.django_db
def test_literal_deduplication_different_language_allowed(db):
    """Test that literals with same value but different language are allowed."""
    # Create first literal in English
    literal_en = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Hello",
        datatype="xsd:string",
        language="en"
    )
    
    # Create second literal in French - should succeed
    literal_fr = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Hello", 
        datatype="xsd:string",
        language="fr"
    )
    
    assert literal_en.id != literal_fr.id
    assert literal_en.language == "en"
    assert literal_fr.language == "fr"
    assert literal_en.value == literal_fr.value

@pytest.mark.django_db
def test_literal_deduplication_different_datatype_allowed(db):
    """Test that literals with same value but different datatype are allowed."""
    # Create first literal as string
    literal_string = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="42",
        datatype="xsd:string"
    )
    
    # Create second literal as integer - should succeed
    literal_int = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="42",
        datatype="xsd:integer"
    )
    
    assert literal_string.id != literal_int.id
    assert literal_string.datatype == "xsd:string"
    assert literal_int.datatype == "xsd:integer"
    assert literal_string.value == literal_int.value

@pytest.mark.django_db
def test_literal_deduplication_different_name_allowed(db):
    """Test that literals with same value but different name are allowed."""
    # Create first literal with name
    literal_with_name1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Sample Text",
        datatype="xsd:string",
        name="field1"
    )
    
    # Create second literal with different name - should succeed
    literal_with_name2 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Sample Text",
        datatype="xsd:string", 
        name="field2"
    )
    
    assert literal_with_name1.id != literal_with_name2.id
    assert literal_with_name1.name == "field1"
    assert literal_with_name2.name == "field2"
    assert literal_with_name1.value == literal_with_name2.value

@pytest.mark.django_db
def test_literal_deduplication_no_name_vs_with_name_allowed(db):
    """Test that literals with same value but one without name are allowed."""
    # Create first literal without name
    literal_no_name = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string"
    )
    
    # Create second literal with name - should succeed
    literal_with_name = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Value",
        datatype="xsd:string",
        name="column_header"
    )
    
    assert literal_no_name.id != literal_with_name.id
    assert literal_no_name.name is None
    assert literal_with_name.name == "column_header"
    assert literal_no_name.value == literal_with_name.value

@pytest.mark.django_db
def test_literal_deduplication_exact_duplicate_prevented(db):
    """Test that exact duplicate literals are prevented across all identifying fields."""
    # Create first literal with all fields
    Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Complex Literal",
        datatype="xsd:string",
        language="en",
        name="test_field"
    )
    
    # Attempt exact duplicate - should fail
    with pytest.raises(Exception):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Complex Literal",
            datatype="xsd:string",
            language="en", 
            name="test_field"
        )

@pytest.mark.django_db  
def test_literal_value_hash_generation(db):
    """Test that value_hash is automatically generated for literals."""
    literal = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Hash Generation"
    )
    
    # Check that value_hash was generated
    assert literal.value_hash is not None
    assert len(literal.value_hash) == 64  # SHA-256 hex digest length
    
    # Check that same value generates same hash
    import hashlib
    expected_hash = hashlib.sha256("Test Hash Generation".encode('utf-8')).hexdigest()
    assert literal.value_hash == expected_hash

@pytest.mark.django_db
def test_literal_unicode_normalization(db):
    """Test that Unicode normalization prevents accidental duplicates."""
    # These should be considered the same after NFC normalization
    value_composed = "café"  # é as single character  
    value_decomposed = "café"  # e + combining acute accent
    
    # Create first literal
    literal1 = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value=value_composed,
        datatype="xsd:string"
    )
    
    # Attempt to create with decomposed form - should fail due to normalization
    with pytest.raises(Exception):
        Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value=value_decomposed,
            datatype="xsd:string"
        )

@pytest.mark.django_db
def test_literal_deduplication_allows_different_combinations(db):
    """Test comprehensive scenarios where literals should be treated as different."""
    base_value = "Shared Value"
    
    # Create multiple valid variations
    variations = [
        # Different languages
        {"value": base_value, "language": "en", "datatype": "xsd:string"},
        {"value": base_value, "language": "fr", "datatype": "xsd:string"},
        # Different datatypes  
        {"value": base_value, "language": None, "datatype": "xsd:string"},
        {"value": base_value, "language": None, "datatype": "custom:text"},
        # Different names
        {"value": base_value, "datatype": "xsd:string", "name": "field_a"},
        {"value": base_value, "datatype": "xsd:string", "name": "field_b"},
        # No name vs with name
        {"value": base_value, "datatype": "xsd:string", "name": None},
    ]
    
    created_literals = []
    for variation in variations:
        literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            **variation
        )
        created_literals.append(literal)
    
    # All should be different instances
    assert len(created_literals) == len(variations)
    all_ids = [lit.id for lit in created_literals]
    assert len(set(all_ids)) == len(all_ids)  # All IDs should be unique
