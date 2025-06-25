import pytest
from django.core.exceptions import ValidationError
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

@pytest.fixture
def common_resources(db):
    """Fixture to create common resources for triple tests."""
    subject_iri = Resource.objects.create(
        uri="http://example.org/subject/1",
        resource_type=ResourceType.IRI,
        source="test_triples"
    )
    predicate_prop = Resource.objects.create(
        uri="http://example.org/property/hasName",
        resource_type=ResourceType.PROPERTY,
        source="test_triples"
    )
    object_literal = Resource.objects.create(
        resource_type=ResourceType.LITERAL,
        value="Test Name",
        source="test_triples"
    )
    object_iri = Resource.objects.create(
        uri="http://example.org/object/1",
        resource_type=ResourceType.IRI,
        source="test_triples"
    )
    literal_subject_attempt = Resource.objects.create( # For testing invalid subject
        resource_type=ResourceType.LITERAL,
        value="Invalid Subject",
        source="test_triples"
    )
    non_property_predicate = Resource.objects.create( # For testing invalid predicate
        uri="http://example.org/class/SomeClass", # Using a class as a predicate
        resource_type=ResourceType.CLASS,
        source="test_triples"
    )
    return {
        "subject_iri": subject_iri,
        "predicate_prop": predicate_prop,
        "object_literal": object_literal,
        "object_iri": object_iri,
        "literal_subject_attempt": literal_subject_attempt,
        "non_property_predicate": non_property_predicate,
    }

@pytest.mark.django_db
def test_create_valid_triple_with_literal_object(db, common_resources):
    """Test creating a valid triple with a literal object."""
    triple = Triple.objects.create(
        subject=common_resources["subject_iri"],
        predicate=common_resources["predicate_prop"],
        object=common_resources["object_literal"]
    )
    assert triple.id is not None
    assert triple.subject == common_resources["subject_iri"]
    assert triple.predicate == common_resources["predicate_prop"]
    assert triple.object == common_resources["object_literal"]
    expected_str = f'{common_resources["subject_iri"]} —{common_resources["predicate_prop"]}→ {common_resources["object_literal"]}'
    assert str(triple) == expected_str

@pytest.mark.django_db
def test_create_valid_triple_with_iri_object(db, common_resources):
    """Test creating a valid triple with an IRI object."""
    triple = Triple.objects.create(
        subject=common_resources["subject_iri"],
        predicate=common_resources["predicate_prop"],
        object=common_resources["object_iri"]
    )
    assert triple.id is not None
    assert triple.subject == common_resources["subject_iri"]
    assert triple.predicate == common_resources["predicate_prop"]
    assert triple.object == common_resources["object_iri"]

@pytest.mark.django_db
def test_invalid_triple_literal_subject(db, common_resources):
    """Test that a triple cannot have a literal as a subject."""
    with pytest.raises(ValidationError, match="Subject cannot be a literal resource"):
        Triple.objects.create(
            subject=common_resources["literal_subject_attempt"],
            predicate=common_resources["predicate_prop"],
            object=common_resources["object_literal"]
        )

@pytest.mark.django_db
def test_invalid_triple_non_property_predicate(db, common_resources):
    """Test that a triple predicate must be a PROPERTY resource type."""
    with pytest.raises(ValidationError, match="Predicate must be a property resource"):
        Triple.objects.create(
            subject=common_resources["subject_iri"],
            predicate=common_resources["non_property_predicate"], # Using a CLASS as predicate
            object=common_resources["object_literal"]
        ) 