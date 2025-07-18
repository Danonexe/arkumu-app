import pytest
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.resource_relationship_service import ResourceRelationshipService
from arkumu.users.models import Organization

User = get_user_model()


@pytest.fixture
def relationship_service():
    """Create ResourceRelationshipService instance."""
    return ResourceRelationshipService()


@pytest.fixture
def sample_organization():
    """Create a sample organization for testing."""
    org = Organization.objects.create(
        code="testorg",
        name="Test Organization"
    )
    return org


@pytest.fixture
def sample_resources(sample_organization):
    """Create sample resources for testing."""
    resources = {}
    
    # Create test resources
    resources['resource1'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset1/rows/1",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 1",
        organization=sample_organization
    )
    
    resources['resource2'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset2/rows/2",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 2",
        organization=sample_organization
    )
    
    resources['resource3'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset3/rows/3",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 3",
        organization=sample_organization
    )
    
    # Create predicate resources
    resources['predicate1'] = Resource.objects.create(
        uri="http://purl.org/dc/terms/relation",
        resource_type=ResourceType.PROPERTY,
        source="testorg",
        name="relation"
    )
    
    resources['predicate2'] = Resource.objects.create(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY,
        source="testorg",
        name="hasPart"
    )
    
    return resources


@pytest.fixture
def sample_triples(sample_resources):
    """Create sample triples for testing."""
    triples = {}
    
    # Create relationships: resource1 -> resource2, resource2 -> resource3
    triples['triple1'] = Triple.objects.create(
        subject=sample_resources['resource1'],
        predicate=sample_resources['predicate1'],
        object=sample_resources['resource2']
    )
    
    triples['triple2'] = Triple.objects.create(
        subject=sample_resources['resource2'],
        predicate=sample_resources['predicate2'],
        object=sample_resources['resource3']
    )
    
    return triples


@pytest.fixture
def sample_mapping(sample_organization):
    """Create a sample mapping for testing."""
    mapping = Mapping.objects.create(
        name="Test Mapping",
        organization_id="testorg",
        mapping_config={
            "workspace_datasets": ["dataset1", "dataset2"],
            "fk_relationships": {
                "rel1": {
                    "source": "dataset1",
                    "target": "dataset2",
                    "type": "one_to_many"
                }
            }
        }
    )
    return mapping


@pytest.mark.django_db
class TestResourceRelationshipService:
    """Test suite for ResourceRelationshipService."""
    
    def test_get_related_resources_basic(self, relationship_service, sample_resources, sample_triples):
        """Test basic relationship discovery."""
        result = relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=1,
            organization="testorg"
        )
        
        assert 'resource' in result
        assert 'relationships' in result
        assert 'graph' in result
        
        # Check resource info
        assert result['resource']['uri'] == sample_resources['resource1'].uri
        assert result['resource']['name'] == "Test Resource 1"
        assert result['resource']['organization'] == "testorg"
        
        # Check relationships
        assert 'outgoing' in result['relationships']
        assert 'incoming' in result['relationships']
        assert len(result['relationships']['outgoing']) == 1
        assert result['relationships']['outgoing'][0]['target']['uri'] == sample_resources['resource2'].uri
    
    def test_get_related_resources_with_depth(self, relationship_service, sample_resources, sample_triples):
        """Test relationship discovery with depth > 1."""
        result = relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=2,
            organization="testorg"
        )
        
        # Should include nodes from both levels
        assert len(result['graph']['nodes']) >= 2
        assert len(result['graph']['edges']) >= 2
        
        # Check that we have the chain resource1 -> resource2 -> resource3
        node_uris = [node['uri'] for node in result['graph']['nodes']]
        assert sample_resources['resource1'].uri in node_uris
        assert sample_resources['resource2'].uri in node_uris
        assert sample_resources['resource3'].uri in node_uris
    
    def test_get_related_resources_organization_filtering(self, relationship_service, sample_resources, sample_triples):
        """Test that organization filtering works correctly."""
        # Create resource in different organization
        other_org = Organization.objects.create(code="otherorg", name="Other Organization")
        other_resource = Resource.objects.create(
            uri="http://test.org/data/otherorg/datasets/dataset1/rows/1",
            resource_type=ResourceType.IRI,
            source="otherorg",
            name="Other Org Resource",
            organization=other_org
        )
        
        result = relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=1,
            organization="testorg"
        )
        
        # Should not include resources from other organizations
        node_uris = [node['uri'] for node in result['graph']['nodes']]
        assert other_resource.uri not in node_uris
    
    def test_get_related_resources_nonexistent_resource(self, relationship_service):
        """Test behavior with invalid resource URI."""
        with pytest.raises(Resource.DoesNotExist):
            relationship_service.get_related_resources(
                "http://invalid.uri",
                organization="testorg"
            )
    
    def test_find_resources_by_relationship(self, relationship_service, sample_resources, sample_triples):
        """Test filtering by relationship type."""
        result = relationship_service.find_resources_by_relationship(
            sample_resources['resource1'].uri,
            relationship_type="relation",
            organization="testorg"
        )
        
        assert len(result) == 1
        assert result[0].uri == sample_resources['resource2'].uri
    
    def test_find_resources_by_relationship_type_not_found(self, relationship_service, sample_resources, sample_triples):
        """Test filtering by non-existent relationship type."""
        result = relationship_service.find_resources_by_relationship(
            sample_resources['resource1'].uri,
            relationship_type="nonexistent",
            organization="testorg"
        )
        
        assert len(result) == 0
    
    def test_get_bidirectional_relationships(self, relationship_service, sample_resources, sample_triples):
        """Test bidirectional relationship discovery."""
        result = relationship_service.get_bidirectional_relationships(
            sample_resources['resource2'].uri,
            organization="testorg"
        )
        
        assert 'outgoing' in result
        assert 'incoming' in result
        
        # resource2 should have incoming from resource1 and outgoing to resource3
        assert len(result['outgoing']) == 1
        assert len(result['incoming']) == 1
        assert result['outgoing'][0].uri == sample_resources['resource3'].uri
        assert result['incoming'][0].uri == sample_resources['resource1'].uri
    
    def test_get_relationship_chain(self, relationship_service, sample_resources, sample_triples):
        """Test relationship chain discovery."""
        result = relationship_service.get_relationship_chain(
            sample_resources['resource1'].uri,
            sample_resources['resource3'].uri,
            organization="testorg"
        )
        
        assert len(result) == 2  # Two steps in the chain
        assert result[0]['source'] == sample_resources['resource1'].uri
        assert result[0]['target'] == sample_resources['resource2'].uri
        assert result[1]['source'] == sample_resources['resource2'].uri
        assert result[1]['target'] == sample_resources['resource3'].uri
    
    def test_get_relationship_chain_no_path(self, relationship_service, sample_resources):
        """Test relationship chain when no path exists."""
        # Create isolated resource
        isolated_resource = Resource.objects.create(
            uri="http://test.org/data/testorg/datasets/isolated/rows/1",
            resource_type=ResourceType.IRI,
            source="testorg",
            name="Isolated Resource"
        )
        
        result = relationship_service.get_relationship_chain(
            sample_resources['resource1'].uri,
            isolated_resource.uri,
            organization="testorg"
        )
        
        assert len(result) == 0
    
    def test_get_mapping_relationships(self, relationship_service, sample_mapping):
        """Test mapping-specific relationship discovery."""
        result = relationship_service.get_mapping_relationships(str(sample_mapping.id))
        
        assert 'fk_relationships' in result
        assert 'rel1' in result['fk_relationships']
        assert result['fk_relationships']['rel1']['source'] == 'dataset1'
        assert result['fk_relationships']['rel1']['target'] == 'dataset2'
        assert result['mapping_name'] == "Test Mapping"
        assert result['organization'] == "testorg"
    
    def test_get_mapping_relationships_nonexistent(self, relationship_service):
        """Test behavior with invalid mapping ID."""
        import uuid
        with pytest.raises(Mapping.DoesNotExist):
            relationship_service.get_mapping_relationships(str(uuid.uuid4()))
    
    def test_get_organization_relationship_types(self, relationship_service, sample_resources, sample_triples):
        """Test getting relationship types for organization."""
        result = relationship_service.get_organization_relationship_types("testorg")
        
        assert isinstance(result, list)
        assert len(result) >= 2  # At least our two predicates
        assert "http://purl.org/dc/terms/relation" in result
        assert "http://purl.org/dc/terms/hasPart" in result
    
    def test_get_organization_relationship_types_empty(self, relationship_service):
        """Test getting relationship types for organization with no data."""
        result = relationship_service.get_organization_relationship_types("emptyorg")
        
        assert isinstance(result, list)
        assert len(result) == 0
    
    def test_get_relationship_type_extraction(self, relationship_service):
        """Test relationship type extraction from URIs."""
        # Test with hash fragment
        result = relationship_service._get_relationship_type("http://example.org/ont#hasRelation")
        assert result == "hasRelation"
        
        # Test with path
        result = relationship_service._get_relationship_type("http://purl.org/dc/terms/relation")
        assert result == "relation"
        
        # Test with simple string
        result = relationship_service._get_relationship_type("simpleRelation")
        assert result == "simpleRelation"
        
        # Test with empty string
        result = relationship_service._get_relationship_type("")
        assert result == "unknown"
    
    def test_empty_relationships(self, relationship_service):
        """Test behavior with resources that have no relationships."""
        # Create isolated resource
        isolated_resource = Resource.objects.create(
            uri="http://test.org/data/testorg/datasets/isolated/rows/1",
            resource_type=ResourceType.IRI,
            source="testorg",
            name="Isolated Resource"
        )
        
        result = relationship_service.get_related_resources(
            isolated_resource.uri,
            organization="testorg"
        )
        
        assert len(result['relationships']['outgoing']) == 0
        assert len(result['relationships']['incoming']) == 0
        assert len(result['graph']['nodes']) == 1  # Just the isolated resource
        assert len(result['graph']['edges']) == 0
    
    def test_cross_organization_isolation(self, relationship_service, sample_resources, sample_triples):
        """Test that organizations cannot access each other's data."""
        # Create resources in different organization
        other_org = Organization.objects.create(code="otherorg", name="Other Organization")
        other_resource = Resource.objects.create(
            uri="http://test.org/data/otherorg/datasets/dataset1/rows/1",
            resource_type=ResourceType.IRI,
            source="otherorg",
            name="Other Org Resource",
            organization=other_org
        )
        
        # Try to access testorg resource from otherorg context
        # This should raise DoesNotExist since resource1 doesn't belong to otherorg
        with pytest.raises(Resource.DoesNotExist):
            relationship_service.get_related_resources(
                sample_resources['resource1'].uri,
                organization="otherorg"
            )


@pytest.mark.django_db
class TestResourceRelationshipServiceCaching:
    """Test suite for ResourceRelationshipService caching functionality."""
    
    def test_cache_key_generation(self, relationship_service, sample_resources, sample_triples):
        """Test that cache keys are generated correctly."""
        with patch('django.core.cache.cache.set') as mock_set:
            relationship_service.get_related_resources(
                sample_resources['resource1'].uri,
                max_depth=2,
                organization="testorg"
            )
            
            # Verify cache was called
            mock_set.assert_called_once()
            call_args = mock_set.call_args
            cache_key = call_args[0][0]
            
            expected_key = f"resource_relationships:{sample_resources['resource1'].uri}:2:testorg"
            assert cache_key == expected_key
    
    def test_cache_hit(self, relationship_service, sample_resources, sample_triples):
        """Test that cached results are returned."""
        # Mock the cache to simulate caching behavior
        mock_cache = {}
        
        def mock_get(key):
            return mock_cache.get(key)
            
        def mock_set(key, value, timeout=None):
            mock_cache[key] = value
            
        def mock_clear():
            mock_cache.clear()
        
        with patch('django.core.cache.cache.get', side_effect=mock_get), \
             patch('django.core.cache.cache.set', side_effect=mock_set), \
             patch('django.core.cache.cache.clear', side_effect=mock_clear):
                
            # Clear cache first
            cache.clear()
            
            # First call - should cache the result
            result1 = relationship_service.get_related_resources(
                sample_resources['resource1'].uri,
                max_depth=1,
                organization="testorg"
            )
            
            # Verify cache is populated
            cache_key = f"resource_relationships:{sample_resources['resource1'].uri}:1:testorg"
            assert cache_key in mock_cache
            assert mock_cache[cache_key] == result1
            
            # Second call - should return cached result
            result2 = relationship_service.get_related_resources(
                sample_resources['resource1'].uri,
                max_depth=1,
                organization="testorg"
            )
            
            # Results should be identical
            assert result1 == result2
    
    def test_cache_invalidation(self, relationship_service, sample_resources, sample_triples):
        """Test cache invalidation functionality."""
        # Cache a result
        relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=1,
            organization="testorg"
        )
        
        # Test invalidation
        relationship_service.invalidate_cache(
            sample_resources['resource1'].uri,
            organization="testorg"
        )
        
        # Verify cache was cleared for the resource
        cache_key = f"resource_relationships:{sample_resources['resource1'].uri}:1:testorg"
        assert cache.get(cache_key) is None
    
    def test_cache_organization_isolation(self, relationship_service, sample_resources, sample_triples):
        """Test that cached results are isolated by organization."""
        # Clear cache first
        cache.clear()
        
        # Cache result for testorg
        relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=1,
            organization="testorg"
        )
        
        # Request for different organization should not use cache and should raise DoesNotExist
        # since the resource doesn't belong to otherorg
        with pytest.raises(Resource.DoesNotExist):
            relationship_service.get_related_resources(
                sample_resources['resource1'].uri,
                max_depth=1,
                organization="otherorg"
            )


@pytest.mark.django_db
class TestResourceRelationshipServicePerformance:
    """Test suite for ResourceRelationshipService performance considerations."""
    
    def test_depth_limiting(self, relationship_service, sample_resources, sample_triples):
        """Test that depth limiting prevents excessive traversal."""
        # Create a longer chain
        resources = [sample_resources['resource1'], sample_resources['resource2'], sample_resources['resource3']]
        
        # Add more resources to the chain
        for i in range(4, 8):
            resource = Resource.objects.create(
                uri=f"http://test.org/data/testorg/datasets/dataset{i}/rows/{i}",
                resource_type=ResourceType.IRI,
                source="testorg",
                name=f"Test Resource {i}"
            )
            resources.append(resource)
            
            # Link to previous resource
            predicate = Resource.objects.create(
                uri=f"http://purl.org/dc/terms/relation{i}",
                resource_type=ResourceType.PROPERTY,
                source="testorg",
                name=f"relation{i}"
            )
            
            Triple.objects.create(
                subject=resources[i-2],
                predicate=predicate,
                object=resources[i-1]
            )
        
        # Test with depth limit
        result = relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=2,
            organization="testorg"
        )
        
        # Should respect depth limit
        assert result['graph']['depth'] == 2
        node_depths = [node['depth'] for node in result['graph']['nodes']]
        assert max(node_depths) <= 2
    
    def test_large_dataset_handling(self, relationship_service, sample_resources):
        """Test handling of larger datasets."""
        # Create hub-and-spoke pattern with many connections
        hub_resource = sample_resources['resource1']
        predicate = sample_resources['predicate1']
        
        # Create 50 spoke resources
        spoke_resources = []
        for i in range(50):
            spoke = Resource.objects.create(
                uri=f"http://test.org/data/testorg/datasets/spoke{i}/rows/1",
                resource_type=ResourceType.IRI,
                source="testorg",
                name=f"Spoke Resource {i}"
            )
            spoke_resources.append(spoke)
            
            Triple.objects.create(
                subject=hub_resource,
                predicate=predicate,
                object=spoke
            )
        
        # Test that it can handle many relationships
        result = relationship_service.get_related_resources(
            hub_resource.uri,
            max_depth=1,
            organization="testorg"
        )
        
        # Should return all 50 connections
        assert len(result['relationships']['outgoing']) == 50
        assert len(result['graph']['edges']) == 50
    
    def test_circular_relationship_handling(self, relationship_service, sample_resources):
        """Test handling of circular relationships."""
        # Create circular relationship: resource1 -> resource2 -> resource1
        circular_predicate = Resource.objects.create(
            uri="http://purl.org/dc/terms/circular",
            resource_type=ResourceType.PROPERTY,
            source="testorg",
            name="circular"
        )
        
        Triple.objects.create(
            subject=sample_resources['resource2'],
            predicate=circular_predicate,
            object=sample_resources['resource1']
        )
        
        # Test that circular relationships don't cause infinite loops
        result = relationship_service.get_related_resources(
            sample_resources['resource1'].uri,
            max_depth=3,
            organization="testorg"
        )
        
        # Should complete without infinite loop
        assert 'graph' in result
        assert len(result['graph']['nodes']) > 0
        
        # Each resource should appear only once in the nodes
        node_uris = [node['uri'] for node in result['graph']['nodes']]
        assert len(node_uris) == len(set(node_uris))  # No duplicates