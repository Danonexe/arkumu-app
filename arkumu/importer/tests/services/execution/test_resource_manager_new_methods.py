"""
Tests for new ResourceManager methods
"""

import pytest
from unittest.mock import Mock
from arkumu.importer.services.execution.resource_manager import ResourceManager
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType


@pytest.fixture
def resource_manager():
    """ResourceManager instance for testing."""
    statistics = ExecutionStatistics()
    return ResourceManager(
        institution="test_institution",
        base_uri="http://test.example.com",
        statistics=statistics
    )


@pytest.fixture
def real_subject_resource(db):
    """Real subject resource for triple creation."""
    return Resource.objects.create(
        uri="http://test.example.com/entities/test/alice",
        resource_type=ResourceType.IRI,
        name="alice",
        source="test-institution"
    )


@pytest.fixture
def real_object_resource(db):
    """Real object resource for relationship creation."""
    return Resource.objects.create(
        uri="http://test.example.com/entities/test/bob",
        resource_type=ResourceType.IRI,
        name="bob",
        source="test-institution"
    )


class TestResourceManagerNewMethods:
    """Test new ResourceManager methods."""
    
    def test_generate_entity_uri(self, resource_manager):
        """Test entity URI generation."""
        result = resource_manager.generate_entity_uri("people", "alice_123")
        
        assert "test-institution" in result
        assert "entities" in result
        assert "people" in result
        assert "alice-123" in result
        assert result.startswith("http://test.example.com")
    
    def test_generate_entity_uri_with_special_characters(self, resource_manager):
        """Test entity URI generation with special characters."""
        result = resource_manager.generate_entity_uri("my dataset", "user@123 name")
        
        assert " " not in result
        assert "@" not in result
        assert "entities" in result
    
    def test_generate_junction_uri(self, resource_manager):
        """Test junction URI generation."""
        result = resource_manager.generate_junction_uri("assignments", "alice", "project_1")
        
        assert "junctions" in result
        assert "assignments" in result
        assert "alice" in result
        assert "project-1" in result
        assert "alice-project-1" in result  # Should combine primary and secondary values
    
    def test_generate_junction_uri_with_special_characters(self, resource_manager):
        """Test junction URI generation with special characters."""
        result = resource_manager.generate_junction_uri("my table", "user@123", "item#456")
        
        assert " " not in result
        assert "@" not in result
        assert "#" not in result
    
    @pytest.mark.django_db
    def test_create_entity_resource_new(self, resource_manager):
        """Test creating a new entity resource."""
        entity_uri = "http://test.example.com/entities/people/alice"
        
        result = resource_manager.create_entity_resource(entity_uri, "people")
        
        assert result is not None
        assert result.uri == entity_uri
        assert result.resource_type == ResourceType.IRI
        # Triple doesn't have a source field
        assert result.is_placeholder is False
        
        # Check statistics
        assert resource_manager.statistics.current_metrics.resources_created == 1
        assert resource_manager.statistics.current_metrics.stub_entities_created == 0
    
    @pytest.mark.django_db
    def test_create_entity_resource_stub(self, resource_manager):
        """Test creating a stub entity resource."""
        entity_uri = "http://test.example.com/entities/departments/engineering"
        
        result = resource_manager.create_entity_resource(entity_uri, "departments", is_stub=True)
        
        assert result is not None
        assert result.uri == entity_uri
        assert result.resource_type == ResourceType.IRI
        assert result.is_placeholder is True
        
        # Check statistics
        assert resource_manager.statistics.current_metrics.resources_created == 1
        assert resource_manager.statistics.current_metrics.stub_entities_created == 1
    
    @pytest.mark.django_db
    def test_create_entity_resource_existing(self, resource_manager):
        """Test getting an existing entity resource."""
        entity_uri = "http://test.example.com/entities/people/alice"
        
        # Create the resource first
        Resource.objects.create(
            uri=entity_uri,
            resource_type=ResourceType.IRI,
            name="alice",
            source="test-institution"
        )
        
        result = resource_manager.create_entity_resource(entity_uri, "people")
        
        assert result is not None
        assert result.uri == entity_uri
        
        # Statistics should not increment for existing resource
        assert resource_manager.statistics.current_metrics.resources_created == 0
    
    @pytest.mark.django_db
    def test_create_external_resource_new(self, resource_manager):
        """Test creating a new external resource."""
        external_uri = "https://orcid.org/0000-0000-0000-0000"
        
        result = resource_manager.create_external_resource(external_uri, "orcid")
        
        assert result is not None
        assert result.uri == external_uri
        assert result.resource_type == ResourceType.IRI
        assert result.source == "orcid"
        assert result.is_placeholder is False
        
        # Check statistics
        assert resource_manager.statistics.current_metrics.resources_created == 1
    
    @pytest.mark.django_db
    def test_create_external_resource_existing(self, resource_manager):
        """Test getting an existing external resource."""
        external_uri = "https://orcid.org/0000-0000-0000-0000"
        
        # Create the resource first
        Resource.objects.create(
            uri=external_uri,
            resource_type=ResourceType.IRI,
            name="0000-0000-0000-0000",
            source="orcid"
        )
        
        result = resource_manager.create_external_resource(external_uri, "orcid")
        
        assert result is not None
        assert result.uri == external_uri
        
        # Statistics should not increment for existing resource
        assert resource_manager.statistics.current_metrics.resources_created == 0
    
    @pytest.mark.django_db
    def test_create_property_triple(self, resource_manager, real_subject_resource):
        """Test creating a property triple."""
        property_uri = "http://test.example.com/properties/person_name"
        object_value = "Alice Smith"
        datatype = "http://www.w3.org/2001/XMLSchema#string"
        
        result = resource_manager.create_property_triple(
            real_subject_resource, property_uri, object_value, datatype
        )
        
        assert result is not None
        assert isinstance(result, Triple)
        assert result.subject == real_subject_resource
        # The object is a literal resource containing the value
        assert result.object.resource_type == ResourceType.LITERAL
        assert result.object.value == object_value
        assert result.object.datatype == datatype
        # Triple doesn't have a source field
        
        # Check that property and value resources were created
        property_resource = Resource.objects.filter(uri=property_uri).first()
        assert property_resource is not None
        assert property_resource.resource_type == ResourceType.PROPERTY
        
        # Check statistics
        assert resource_manager.statistics.current_metrics.triples_created == 1
    
    @pytest.mark.django_db
    def test_create_property_triple_with_long_value(self, resource_manager, real_subject_resource):
        """Test creating a property triple with a long value."""
        property_uri = "http://test.example.com/properties/description"
        object_value = "A" * 200  # Long value
        datatype = "http://www.w3.org/2001/XMLSchema#string"
        
        result = resource_manager.create_property_triple(
            real_subject_resource, property_uri, object_value, datatype
        )
        
        assert result is not None
        assert result.object.value == object_value  # Full value should be stored
        
        # Value resource name should be truncated to 100 chars
        value_resource = result.object
        assert len(value_resource.name) <= 100
    
    @pytest.mark.django_db
    def test_create_relationship_triple(self, resource_manager, real_subject_resource, real_object_resource):
        """Test creating a relationship triple."""
        property_uri = "http://test.example.com/properties/works_in"
        
        result = resource_manager.create_relationship_triple(
            real_subject_resource, property_uri, real_object_resource
        )
        
        assert result is not None
        assert isinstance(result, Triple)
        assert result.subject == real_subject_resource
        assert result.object == real_object_resource
        # Triple doesn't have a source field
        
        # Check that property resource was created
        property_resource = Resource.objects.filter(uri=property_uri).first()
        assert property_resource is not None
        assert property_resource.resource_type == ResourceType.PROPERTY
        
        # Check statistics
        assert resource_manager.statistics.current_metrics.triples_created == 1
        assert resource_manager.statistics.current_metrics.relationships_created == 1
    
    @pytest.mark.django_db
    def test_create_relationship_triple_existing_property(self, resource_manager, 
                                                         real_subject_resource, real_object_resource):
        """Test creating a relationship triple with existing property."""
        property_uri = "http://test.example.com/properties/works_in"
        
        # Create property resource first
        Resource.objects.create(
            uri=property_uri,
            resource_type=ResourceType.PROPERTY,
            name="works_in",
            source="test-institution"
        )
        
        result = resource_manager.create_relationship_triple(
            real_subject_resource, property_uri, real_object_resource
        )
        
        assert result is not None
        
        # Should only have one property resource (not create duplicate)
        property_resources = Resource.objects.filter(uri=property_uri)
        assert property_resources.count() == 1
    
    @pytest.mark.django_db 
    def test_create_triple_existing_relationship(self, resource_manager,
                                               real_subject_resource, real_object_resource):
        """Test creating an existing relationship triple."""
        property_uri = "http://test.example.com/properties/works_in"
        
        # Create property resource
        property_resource = Resource.objects.create(
            uri=property_uri,
            resource_type=ResourceType.PROPERTY,
            name="works_in",
            source="test-institution"
        )
        
        # Create the triple first
        Triple.objects.create(
            subject=real_subject_resource,
            predicate=property_resource,
            object=real_object_resource
        )
        
        # Try to create again
        result = resource_manager.create_relationship_triple(
            real_subject_resource, property_uri, real_object_resource
        )
        
        assert result is not None
        
        # Should only have one triple (not create duplicate)
        triples = Triple.objects.filter(
            subject=real_subject_resource,
            predicate=property_resource,
            object=real_object_resource
        )
        assert triples.count() == 1
        
        # Statistics should not increment for existing triple
        assert resource_manager.statistics.current_metrics.triples_created == 0


class TestResourceManagerIntegration:
    """Integration tests for ResourceManager new methods."""
    
    @pytest.mark.django_db
    def test_complete_entity_creation_workflow(self, resource_manager):
        """Test complete workflow of creating entity with properties and relationships."""
        # Generate entity URI
        entity_uri = resource_manager.generate_entity_uri("people", "alice")
        
        # Create entity
        entity = resource_manager.create_entity_resource(entity_uri, "people")
        
        # Add property
        property_triple = resource_manager.create_property_triple(
            entity, 
            "http://test.example.com/properties/name",
            "Alice Smith",
            "http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Create target entity for relationship
        target_uri = resource_manager.generate_entity_uri("departments", "engineering")
        target_entity = resource_manager.create_entity_resource(target_uri, "departments")
        
        # Add relationship
        relationship_triple = resource_manager.create_relationship_triple(
            entity,
            "http://test.example.com/properties/works_in", 
            target_entity
        )
        
        # Verify everything was created
        assert entity.uri == entity_uri
        assert property_triple.subject == entity
        assert property_triple.object.value == "Alice Smith"
        assert relationship_triple.subject == entity
        assert relationship_triple.object == target_entity
        
        # Check statistics
        metrics = resource_manager.statistics.current_metrics
        assert metrics.resources_created >= 2  # At least entity and target
        assert metrics.triples_created == 2
        assert metrics.relationships_created == 1
    
    @pytest.mark.django_db
    def test_junction_entity_creation(self, resource_manager):
        """Test creating junction entities with context."""
        # Generate junction URI
        junction_uri = resource_manager.generate_junction_uri("assignments", "alice", "project_1")
        
        # Create junction entity
        junction = resource_manager.create_entity_resource(junction_uri, "assignments")
        
        # Add context properties
        role_triple = resource_manager.create_property_triple(
            junction,
            "http://test.example.com/properties/role",
            "lead developer",
            "http://www.w3.org/2001/XMLSchema#string"
        )
        
        start_date_triple = resource_manager.create_property_triple(
            junction,
            "http://test.example.com/properties/start_date", 
            "2023-01-01",
            "http://www.w3.org/2001/XMLSchema#date"
        )
        
        # Verify junction creation
        assert junction.uri == junction_uri
        assert "junctions" in junction.uri
        assert "assignments" in junction.uri
        assert role_triple.object.value == "lead developer"
        assert start_date_triple.object.value == "2023-01-01"
        
        # Check statistics
        metrics = resource_manager.statistics.current_metrics
        assert metrics.resources_created >= 1
        assert metrics.triples_created == 2