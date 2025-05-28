"""
Tests for the bulk triple editor functionality using pytest.
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
import time

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

User = get_user_model()


@pytest.fixture
def client():
    """Create a test client."""
    return Client()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def authenticated_client(client, user):
    """Create an authenticated client."""
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def test_resources(db):
    """Create test resources for querying."""
    person = Resource.objects.create(
        uri="http://example.org/person1",
        resource_type=ResourceType.IRI,
        name="John Doe",
        source="TEST"
    )
    
    activity = Resource.objects.create(
        uri="http://example.org/activity1",
        resource_type=ResourceType.IRI,
        name="Test Activity",
        source="TEST"
    )
    
    predicate = Resource.objects.create(
        uri="http://www.cidoc-crm.org/cidoc-crm/P14_carried_out_by",
        resource_type=ResourceType.PROPERTY,
        name="carried out by",
        source="TEST"
    )
    
    triple = Triple.objects.create(
        subject=activity,
        predicate=predicate,
        object=person
    )
    
    return {
        'person': person,
        'activity': activity,
        'predicate': predicate,
        'triple': triple
    }


# View Tests

@pytest.mark.django_db
def test_bulk_triple_editor_view_accessible(authenticated_client):
    """Test that the bulk triple editor view is accessible."""
    url = reverse('metadata:bulk_triple_editor')
    response = authenticated_client.get(url)
    
    assert response.status_code == 200
    assert 'Bulk Triple Editor' in response.content.decode()
    assert 'Query Existing Relationships' in response.content.decode()
    assert 'Create Multiple Triples' in response.content.decode()


@pytest.mark.django_db
def test_bulk_triple_editor_requires_login(client):
    """Test that the bulk triple editor requires authentication."""
    url = reverse('metadata:bulk_triple_editor')
    response = client.get(url)
    
    # Should redirect to login
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_query_relationships_view_no_params(authenticated_client):
    """Test the query relationships functionality with no parameters."""
    url = reverse('metadata:query_relationships')
    response = authenticated_client.get(url)
    
    assert response.status_code == 200
    assert 'Enter search terms above' in response.content.decode()


@pytest.mark.django_db
def test_query_relationships_view_with_subject(authenticated_client, test_resources):
    """Test querying relationships by subject."""
    url = reverse('metadata:query_relationships')
    # The activity is the subject in our test triple
    response = authenticated_client.get(url, {'query-subject': 'Test Activity'})
    
    assert response.status_code == 200
    assert 'Test Activity' in response.content.decode()


@pytest.mark.django_db
def test_query_relationships_view_with_predicate(authenticated_client, test_resources):
    """Test querying relationships by predicate."""
    url = reverse('metadata:query_relationships')
    response = authenticated_client.get(url, {'query-predicate': 'carried'})
    
    assert response.status_code == 200
    assert 'carried out by' in response.content.decode()


@pytest.mark.django_db
def test_query_relationships_view_with_object(authenticated_client, test_resources):
    """Test querying relationships by object."""
    url = reverse('metadata:query_relationships')
    # The person is the object in our test triple
    response = authenticated_client.get(url, {'query-object': 'John'})
    
    assert response.status_code == 200
    assert 'John Doe' in response.content.decode()


@pytest.mark.django_db
def test_query_relationships_pagination(authenticated_client, test_resources):
    """Test pagination in query relationships."""
    # Create many triples to test pagination
    activity = test_resources['activity']
    predicate = test_resources['predicate']
    
    for i in range(15):
        # Use a different URI pattern to avoid conflicts with existing person1
        person = Resource.objects.create(
            uri=f"http://example.org/testperson{i}",
            resource_type=ResourceType.IRI,
            name=f"Test Person {i}",
            source="TEST"
        )
        Triple.objects.create(
            subject=activity,
            predicate=predicate,
            object=person
        )
    
    url = reverse('metadata:query_relationships')
    response = authenticated_client.get(url, {'query-predicate': 'carried'})
    
    assert response.status_code == 200
    assert 'Page 1 of' in response.content.decode()


# Bulk Creation Tests

@pytest.mark.django_db
def test_create_bulk_triples_requires_post(authenticated_client):
    """Test that create_bulk_triples only accepts POST requests."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.get(url)
    
    assert response.status_code == 405


@pytest.mark.django_db
def test_create_bulk_triples_empty_data(authenticated_client):
    """Test creating triples with empty data."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '',
        'institution': 'TEST',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'No triples provided for creation' in response.content.decode()


@pytest.mark.django_db
def test_create_bulk_triples_invalid_format(authenticated_client):
    """Test creating triples with invalid format."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': 'invalid|format\nonly-two-parts|missing-object\nvalid|triple|format',
        'institution': 'TEST',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    content = response.content.decode()
    assert 'Validation Errors Found' in content
    assert 'Expected 3 parts' in content


@pytest.mark.django_db
def test_create_bulk_triples_success(authenticated_client):
    """Test successful bulk triple creation."""
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:TestPerson1|dc:name|John Doe
new:TestPerson1|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E21_Person
new:TestActivity1|P14_carried_out_by|new:TestPerson1
new:TestDocument1|dc:title|Test Document
new:TestDocument1|dcterms:relation|new:TestActivity1''',
        'institution': 'TEST_BULK',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Check that resources and triples were created
    assert Resource.objects.count() > initial_resource_count
    assert Triple.objects.count() > initial_triple_count
    
    # Verify specific resources were created
    assert Resource.objects.filter(
        name="TestPerson1",
        source="TEST_BULK"
    ).exists()
    
    # Verify predicates were mapped correctly
    assert Resource.objects.filter(
        uri="http://purl.org/dc/terms/name",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    # Verify triples were created
    person_resource = Resource.objects.get(name="TestPerson1", source="TEST_BULK")
    name_predicate = Resource.objects.get(uri="http://purl.org/dc/terms/name")
    name_literal = Resource.objects.get(
        resource_type=ResourceType.LITERAL,
        value="John Doe",
        source="TEST_BULK"
    )
    
    assert Triple.objects.filter(
        subject=person_resource,
        predicate=name_predicate,
        object=name_literal
    ).exists()


@pytest.mark.django_db
def test_create_bulk_triples_with_existing_resources(authenticated_client):
    """Test creating triples with some existing resources."""
    # Create an existing person resource
    existing_person = Resource.objects.create(
        uri="http://arkumu.org/data/TEST_BULK/entities/testperson1",
        resource_type=ResourceType.IRI,
        name="TestPerson1",
        source="TEST_BULK"
    )
    
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': 'new:TestPerson1|dc:name|John Doe',
        'institution': 'TEST_BULK',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Should not create duplicate person resource
    assert Resource.objects.filter(
        name="TestPerson1",
        source="TEST_BULK"
    ).count() == 1


@pytest.mark.django_db
def test_create_bulk_triples_cidoc_predicates(authenticated_client):
    """Test creating triples with CIDOC-CRM predicates."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Activity1|P14_carried_out_by|new:Person1
new:Activity1|cidoc:P11_had_participant|new:Person2''',
        'institution': 'TEST_CIDOC',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify CIDOC predicates were created with correct URIs
    assert Resource.objects.filter(
        uri="http://www.cidoc-crm.org/cidoc-crm/P14_carried_out_by",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    assert Resource.objects.filter(
        uri="http://www.cidoc-crm.org/cidoc-crm/P11_had_participant",
        resource_type=ResourceType.PROPERTY
    ).exists()


@pytest.mark.django_db
def test_create_bulk_triples_literal_objects(authenticated_client):
    """Test creating triples with literal objects."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Person1|dc:name|John Doe
new:Person1|dc:birthDate|1990-01-01
new:Document1|dc:title|My Document''',
        'institution': 'TEST_LITERALS',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify literal values were created
    assert Resource.objects.filter(
        resource_type=ResourceType.LITERAL,
        value="John Doe",
        source="TEST_LITERALS"
    ).exists()
    
    assert Resource.objects.filter(
        resource_type=ResourceType.LITERAL,
        value="1990-01-01",
        source="TEST_LITERALS"
    ).exists()


@pytest.mark.django_db
def test_create_bulk_triples_existing_uri_objects(authenticated_client):
    """Test creating triples with existing URI objects."""
    # Create an existing resource
    existing_class = Resource.objects.create(
        uri="http://www.cidoc-crm.org/cidoc-crm/E21_Person",
        resource_type=ResourceType.CLASS,
        name="Person",
        source="CIDOC"
    )
    
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': 'new:Person1|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E21_Person',
        'institution': 'TEST_EXISTING',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify the triple was created with the existing class
    person_resource = Resource.objects.get(name="Person1", source="TEST_EXISTING")
    rdf_type = Resource.objects.get(uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    
    assert Triple.objects.filter(
        subject=person_resource,
        predicate=rdf_type,
        object=existing_class
    ).exists()


@pytest.mark.django_db
def test_create_bulk_triples_duplicate_prevention(authenticated_client):
    """Test that duplicate triples are not created."""
    triple_data = 'new:Person1|dc:name|John Doe'
    url = reverse('metadata:create_bulk_triples')
    
    # First creation
    response1 = authenticated_client.post(url, {
        'batch-triples': triple_data,
        'institution': 'TEST_DUPLICATE',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response1.status_code == 200
    assert 'Triples Created' in response1.content.decode()
    
    initial_triple_count = Triple.objects.count()
    
    # Second creation (should skip)
    response2 = authenticated_client.post(url, {
        'batch-triples': triple_data,
        'institution': 'TEST_DUPLICATE',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response2.status_code == 200
    assert 'Triples Skipped' in response2.content.decode()
    
    # Triple count should not increase
    assert Triple.objects.count() == initial_triple_count


# Integration Tests

@pytest.mark.django_db
def test_complete_workflow(authenticated_client):
    """Test the complete workflow from query to creation."""
    # Step 1: Access the bulk editor
    editor_url = reverse('metadata:bulk_triple_editor')
    response = authenticated_client.get(editor_url)
    assert response.status_code == 200
    
    # Step 2: Create some initial data
    create_url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(create_url, {
        'batch-triples': '''new:Artist1|dc:name|Pablo Picasso
new:Artwork1|dc:creator|new:Artist1
new:Artwork1|dc:title|Guernica''',
        'institution': 'INTEGRATION_TEST',
        'base-uri': 'http://arkumu.org/data'
    })
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Step 3: Query the created relationships
    query_url = reverse('metadata:query_relationships')
    response = authenticated_client.get(query_url, {
        'query-subject': 'Artist1'
    })
    assert response.status_code == 200
    assert 'Pablo Picasso' in response.content.decode()
    
    # Step 4: Query by predicate
    response = authenticated_client.get(query_url, {
        'query-predicate': 'creator'
    })
    assert response.status_code == 200
    assert 'Artwork1' in response.content.decode()
    
    # Step 5: Add more related triples
    response = authenticated_client.post(create_url, {
        'batch-triples': '''new:Artist1|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E21_Person
new:Artwork1|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E22_Man-Made_Object
new:Museum1|dcterms:hasPart|new:Artwork1''',
        'institution': 'INTEGRATION_TEST',
        'base-uri': 'http://arkumu.org/data'
    })
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify the final state
    artist = Resource.objects.get(name="Artist1", source="INTEGRATION_TEST")
    artwork = Resource.objects.get(name="Artwork1", source="INTEGRATION_TEST")
    
    # Check that all expected triples exist
    assert Triple.objects.filter(subject=artist).count() >= 2  # name + type
    assert Triple.objects.filter(subject=artwork).count() >= 3  # creator + title + type


# Performance Tests

@pytest.mark.django_db
def test_large_batch_creation_performance(authenticated_client):
    """Test creating a large batch of triples."""
    # Create a batch of 100 triples
    triples = []
    for i in range(100):
        triples.append(f'new:Person{i}|dc:name|Person {i}')
        triples.append(f'new:Person{i}|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E21_Person')
    
    batch_data = '\n'.join(triples)
    url = reverse('metadata:create_bulk_triples')
    
    start_time = time.time()
    
    response = authenticated_client.post(url, {
        'batch-triples': batch_data,
        'institution': 'PERF_TEST',
        'base-uri': 'http://arkumu.org/data'
    })
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Should complete in reasonable time (adjust threshold as needed)
    assert execution_time < 30  # 30 seconds threshold
    
    # Verify all resources were created
    assert Resource.objects.filter(source="PERF_TEST").count() >= 200  # 100 persons + literals + predicates
    
    print(f"Created 200 triples in {execution_time:.2f} seconds")


# Dublin Core Predicate Tests

@pytest.mark.django_db
def test_dublin_core_predicates(authenticated_client):
    """Test creating triples with Dublin Core predicates."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Document1|dc:title|My Document
new:Document1|dc:creator|John Author
new:Document1|dc:date|2024-01-01
new:Document1|dcterms:hasPart|new:Chapter1''',
        'institution': 'TEST_DC',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify Dublin Core predicates were mapped correctly
    assert Resource.objects.filter(
        uri="http://purl.org/dc/terms/title",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    assert Resource.objects.filter(
        uri="http://purl.org/dc/terms/creator",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    assert Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).exists()


@pytest.mark.django_db
def test_rdf_rdfs_predicates(authenticated_client):
    """Test creating triples with RDF/RDFS predicates."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Person1|rdf:type|http://www.cidoc-crm.org/cidoc-crm/E21_Person
new:Person1|rdfs:label|John Doe
new:Person1|rdfs:comment|A test person''',
        'institution': 'TEST_RDF',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify RDF/RDFS predicates were mapped correctly
    assert Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    assert Resource.objects.filter(
        uri="http://www.w3.org/2000/01/rdf-schema#label",
        resource_type=ResourceType.PROPERTY
    ).exists()
    
    assert Resource.objects.filter(
        uri="http://www.w3.org/2000/01/rdf-schema#comment",
        resource_type=ResourceType.PROPERTY
    ).exists()


@pytest.mark.django_db
def test_mixed_predicate_formats(authenticated_client):
    """Test creating triples with mixed predicate formats."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Person1|dc:name|John Doe
new:Person1|http://purl.org/dc/terms/birthDate|1990-01-01
new:Person1|P14_carried_out_by|new:Activity1
new:Person1|new:customProperty|Custom Value''',
        'institution': 'TEST_MIXED',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    assert 'Bulk Creation Successful!' in response.content.decode()
    
    # Verify all predicate formats were handled
    person = Resource.objects.get(name="Person1", source="TEST_MIXED")
    assert Triple.objects.filter(subject=person).count() == 4


@pytest.mark.django_db  
def test_error_handling_and_recovery(authenticated_client):
    """Test that errors in some lines don't prevent processing of valid lines."""
    url = reverse('metadata:create_bulk_triples')
    response = authenticated_client.post(url, {
        'batch-triples': '''new:Person1|dc:name|John Doe
invalid|line|with|too|many|parts
new:Person2|dc:name|Jane Doe
|empty|subject
new:Person3|dc:name|Bob Smith''',
        'institution': 'TEST_ERROR_RECOVERY',
        'base-uri': 'http://arkumu.org/data'
    })
    
    assert response.status_code == 200
    content = response.content.decode()
    assert 'Validation Errors Found' in content
    assert 'Expected 3 parts' in content
    
    # Valid triples should not be created due to validation errors
    assert not Resource.objects.filter(source="TEST_ERROR_RECOVERY").exists() 