import pytest
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from unittest.mock import patch, MagicMock

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.models.mappings import Mapping
from arkumu.users.models import Organization

User = get_user_model()


@pytest.fixture
def test_client():
    """Create Django test client for testing."""
    return Client()


@pytest.fixture
def test_organization():
    """Create test organization."""
    return Organization.objects.create(
        code="testorg",
        name="Test Organization"
    )


@pytest.fixture
def other_organization():
    """Create another test organization."""
    return Organization.objects.create(
        code="otherorg",
        name="Other Organization"
    )


@pytest.fixture
def test_user(test_organization):
    """Create test user."""
    user = User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
    user.organization = test_organization
    user.save()
    return user


@pytest.fixture
def other_user(other_organization):
    """Create user from different organization."""
    user = User.objects.create_user(
        username='otheruser',
        email='other@example.com',
        password='testpass123'
    )
    user.organization = other_organization
    user.save()
    return user


@pytest.fixture
def system_admin_user():
    """Create system admin user."""
    user = User.objects.create_user(
        username='admin',
        email='admin@example.com',
        password='testpass123'
    )
    user.role = 'system_admin'
    user.save()
    return user


@pytest.fixture
def test_resources(test_organization):
    """Create test resources."""
    resources = {}
    
    resources['resource1'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset1/rows/1",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 1",
        organization=test_organization
    )
    
    resources['resource2'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset2/rows/2",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 2",
        organization=test_organization
    )
    
    resources['resource3'] = Resource.objects.create(
        uri="http://test.org/data/testorg/datasets/dataset3/rows/3",
        resource_type=ResourceType.IRI,
        source="testorg",
        name="Test Resource 3",
        organization=test_organization
    )
    
    # Create predicate
    resources['predicate'] = Resource.objects.create(
        uri="http://purl.org/dc/terms/relation",
        resource_type=ResourceType.PROPERTY,
        source="testorg",
        name="relation"
    )
    
    return resources


@pytest.fixture
def test_triples(test_resources):
    """Create test triples."""
    triples = {}
    
    triples['triple1'] = Triple.objects.create(
        subject=test_resources['resource1'],
        predicate=test_resources['predicate'],
        object=test_resources['resource2']
    )
    
    triples['triple2'] = Triple.objects.create(
        subject=test_resources['resource2'],
        predicate=test_resources['predicate'],
        object=test_resources['resource3']
    )
    
    return triples


@pytest.fixture
def test_mapping(test_organization):
    """Create test mapping."""
    return Mapping.objects.create(
        name="Test Mapping",
        organization_id="testorg",
        mapping_config={
            "fk_relationships": {
                "rel1": {"source": "dataset1", "target": "dataset2"}
            }
        }
    )


@pytest.mark.django_db
class TestResourceRelationshipView:
    """Test suite for ResourceRelationshipView."""
    
    def test_get_resource_relationships_success(self, test_client, test_user, test_resources, test_triples):
        """Test successful retrieval of resource relationships."""
        test_client.force_login(test_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = test_client.get(url)
        
        assert response.status_code == 200
        
        # Check that the template was rendered correctly
        assert 'metadata/relationships/explorer.html' in [t.name for t in response.templates]
        
        # Check context data
        context = response.context
        assert 'resource' in context
        assert 'relationships' in context
        
        # Check resource info
        resource = context['resource']
        assert resource['uri'] == test_resources['resource1'].uri
        assert resource['name'] == "Test Resource 1"
        assert resource['organization'] == "testorg"
    
    def test_get_resource_relationships_with_depth(self, test_client, test_user, test_resources, test_triples):
        """Test relationships with custom depth parameter."""
        test_client.force_login(test_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = test_client.get(url, {'depth': 2})
        
        assert response.status_code == 200
        
        # Check context data
        context = response.context
        assert 'graph' in context
        assert context['graph']['depth'] == 2
        assert len(context['graph']['nodes']) >= 2
    
    def test_get_resource_relationships_unauthorized(self, test_client, test_resources):
        """Test unauthorized access to resource relationships."""
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = test_client.get(url)
        
        # Should redirect to login since we use LoginRequiredMixin
        assert response.status_code == 302
    
    def test_get_resource_relationships_cross_organization_denied(self, test_client, other_user, test_resources, test_triples):
        """Test that users cannot access other organization's resources."""
        test_client.force_login(other_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = test_client.get(url)
        
        assert response.status_code == 403
    
    def test_get_resource_relationships_system_admin_access(self, api_client, system_admin_user, test_resources, test_triples):
        """Test that system admin can access any resource."""
        api_client.force_authenticate(user=system_admin_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_resource_relationships_nonexistent_resource(self, api_client, test_user):
        """Test 404 response for nonexistent resource."""
        api_client.force_authenticate(user=test_user)
        
        import uuid
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': uuid.uuid4()})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_resource_relationships_depth_limit(self, api_client, test_user, test_resources, test_triples):
        """Test that depth is limited to prevent abuse."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url, {'depth': 10})  # Try to set very high depth
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        # Should be limited to max 5
        assert data['graph']['depth'] <= 5


@pytest.mark.django_db
class TestRelatedResourcesView:
    """Test suite for RelatedResourcesView."""
    
    def test_get_related_resources_success(self, api_client, test_user, test_resources, test_triples):
        """Test successful retrieval of related resources."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:related_resources', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'related_resources' in data
        assert 'pagination' in data
        assert len(data['related_resources']) >= 1
        
        # Check resource structure
        resource = data['related_resources'][0]
        assert 'id' in resource
        assert 'uri' in resource
        assert 'name' in resource
        assert 'type' in resource
        assert 'organization' in resource
    
    def test_get_related_resources_with_relationship_type(self, api_client, test_user, test_resources, test_triples):
        """Test filtering by relationship type."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:related_resources', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url, {'relationship_type': 'relation'})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'related_resources' in data
        assert len(data['related_resources']) >= 1
    
    def test_get_related_resources_pagination(self, api_client, test_user, test_resources, test_triples):
        """Test pagination of related resources."""
        # Create many related resources
        predicate = test_resources['predicate']
        for i in range(25):
            resource = Resource.objects.create(
                uri=f"http://test.org/data/testorg/datasets/dataset{i}/rows/{i}",
                resource_type=ResourceType.IRI,
                source="testorg",
                name=f"Test Resource {i}",
                organization=test_user.organization
            )
            
            Triple.objects.create(
                subject=test_resources['resource1'],
                predicate=predicate,
                object=resource
            )
        
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:related_resources', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url, {'page': 1, 'page_size': 10})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'pagination' in data
        assert len(data['related_resources']) == 10
        assert data['pagination']['page'] == 1
        assert data['pagination']['total_count'] > 20


@pytest.mark.django_db
class TestResourceGraphView:
    """Test suite for ResourceGraphView."""
    
    def test_get_resource_graph_success(self, api_client, test_user, test_resources, test_triples):
        """Test successful retrieval of resource graph."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_graph_api', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'graph' in data
        assert 'resource' in data
        
        # Check graph structure
        graph = data['graph']
        assert 'nodes' in graph
        assert 'edges' in graph
        assert 'depth' in graph
        assert len(graph['nodes']) > 0
        
        # Check resource info
        resource = data['resource']
        assert resource['uri'] == test_resources['resource1'].uri
        assert resource['name'] == "Test Resource 1"
    
    def test_get_resource_graph_with_depth(self, api_client, test_user, test_resources, test_triples):
        """Test graph with custom depth."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_graph_api', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url, {'depth': 2})
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert data['graph']['depth'] == 2
    
    def test_get_resource_graph_depth_limit(self, api_client, test_user, test_resources, test_triples):
        """Test that graph depth is limited."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_graph_api', kwargs={'resource_id': test_resources['resource1'].id})
        response = api_client.get(url, {'depth': 10})  # Try very high depth
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        # Should be limited to max 3
        assert data['graph']['depth'] <= 3


@pytest.mark.django_db
class TestRelationshipChainView:
    """Test suite for RelationshipChainView."""
    
    def test_get_relationship_chain_success(self, api_client, test_user, test_resources, test_triples):
        """Test successful retrieval of relationship chain."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:relationship_chain', kwargs={
            'resource_id': test_resources['resource1'].id,
            'target_id': test_resources['resource3'].id
        })
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'chain' in data
        assert 'source' in data
        assert 'target' in data
        
        # Check chain structure
        assert len(data['chain']) > 0
        
        # Check source and target info
        assert data['source']['uri'] == test_resources['resource1'].uri
        assert data['target']['uri'] == test_resources['resource3'].uri
    
    def test_get_relationship_chain_no_path(self, api_client, test_user, test_resources):
        """Test chain between unconnected resources."""
        # Create isolated resource
        isolated_resource = Resource.objects.create(
            uri="http://test.org/data/testorg/datasets/isolated/rows/1",
            resource_type=ResourceType.IRI,
            source="testorg",
            name="Isolated Resource",
            organization=test_user.organization
        )
        
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:relationship_chain', kwargs={
            'resource_id': test_resources['resource1'].id,
            'target_id': isolated_resource.id
        })
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'chain' in data
        assert len(data['chain']) == 0  # No path found
    
    def test_get_relationship_chain_cross_organization_denied(self, api_client, other_user, test_resources, test_triples):
        """Test that users cannot access chain between other organization's resources."""
        api_client.force_authenticate(user=other_user)
        
        url = reverse('metadata:relationship_chain', kwargs={
            'resource_id': test_resources['resource1'].id,
            'target_id': test_resources['resource3'].id
        })
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestMappingRelationshipsView:
    """Test suite for MappingRelationshipsView."""
    
    def test_get_mapping_relationships_success(self, api_client, test_user, test_mapping):
        """Test successful retrieval of mapping relationships."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:mapping_relationships', kwargs={'mapping_id': test_mapping.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'fk_relationships' in data
        assert 'mapping_name' in data
        assert 'organization' in data
        
        # Check mapping info
        assert data['mapping_name'] == "Test Mapping"
        assert data['organization'] == "testorg"
        assert 'rel1' in data['fk_relationships']
    
    def test_get_mapping_relationships_cross_organization_denied(self, api_client, other_user, test_mapping):
        """Test that users cannot access other organization's mappings."""
        api_client.force_authenticate(user=other_user)
        
        url = reverse('metadata:mapping_relationships', kwargs={'mapping_id': test_mapping.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_mapping_relationships_nonexistent(self, api_client, test_user):
        """Test 404 response for nonexistent mapping."""
        api_client.force_authenticate(user=test_user)
        
        import uuid
        url = reverse('metadata:mapping_relationships', kwargs={'mapping_id': uuid.uuid4()})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestOrganizationRelationshipTypesView:
    """Test suite for OrganizationRelationshipTypesView."""
    
    def test_get_organization_relationship_types_success(self, api_client, test_user, test_resources, test_triples):
        """Test successful retrieval of organization relationship types."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:org_relationship_types', kwargs={'org_code': 'testorg'})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert 'organization' in data
        assert 'relationship_types' in data
        
        # Check organization info
        assert data['organization'] == 'testorg'
        assert isinstance(data['relationship_types'], list)
    
    def test_get_organization_relationship_types_cross_organization_denied(self, api_client, other_user):
        """Test that users cannot access other organization's relationship types."""
        api_client.force_authenticate(user=other_user)
        
        url = reverse('metadata:org_relationship_types', kwargs={'org_code': 'testorg'})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_organization_relationship_types_own_organization(self, api_client, test_user, test_resources, test_triples):
        """Test that users can access their own organization's relationship types."""
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:org_relationship_types', kwargs={'org_code': test_user.organization.code})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert data['organization'] == test_user.organization.code
        assert isinstance(data['relationship_types'], list)


@pytest.mark.django_db
class TestResourceRelationshipViewsErrorHandling:
    """Test suite for error handling in resource relationship views."""
    
    def test_server_error_handling(self, api_client, test_user, test_resources):
        """Test that server errors are handled gracefully."""
        api_client.force_authenticate(user=test_user)
        
        # Mock service to raise exception
        with patch('arkumu.metadata.services.resource_relationship_service.ResourceRelationshipService.get_related_resources') as mock_service:
            mock_service.side_effect = Exception("Database error")
            
            url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
            response = api_client.get(url)
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.data
            assert 'error' in data
            assert data['error'] == 'Internal server error'
    
    def test_invalid_uuid_handling(self, api_client, test_user):
        """Test handling of invalid UUID in URL."""
        api_client.force_authenticate(user=test_user)
        
        # This should be handled by Django's URL routing
        url = '/metadata/resources/invalid-uuid/relationships/'
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_permission_denied_handling(self, api_client, test_user, test_resources):
        """Test that permission denied errors are handled properly."""
        api_client.force_authenticate(user=test_user)
        
        # Mock permission check to return False
        with patch('arkumu.metadata.views.resource_relationship_views.ResourceRelationshipView._can_access_resource') as mock_permission:
            mock_permission.return_value = False
            
            url = reverse('metadata:resource_relationships', kwargs={'resource_id': test_resources['resource1'].id})
            response = api_client.get(url)
            
            assert response.status_code == status.HTTP_403_FORBIDDEN
            data = response.data
            assert 'error' in data


@pytest.mark.django_db
class TestResourceRelationshipViewsPublicAccess:
    """Test suite for public access to resource relationship views."""
    
    def test_public_resource_access(self, api_client, test_user, test_organization):
        """Test access to public resources."""
        # Create public resource
        public_resource = Resource.objects.create(
            uri="http://test.org/data/testorg/datasets/public/rows/1",
            resource_type=ResourceType.IRI,
            source="testorg",
            name="Public Resource",
            organization=test_organization,
            public_access_level='public',
            is_public_approved=True
        )
        
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': public_resource.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_restricted_resource_access(self, api_client, test_user, test_organization):
        """Test access to restricted resources."""
        # Create restricted resource
        restricted_resource = Resource.objects.create(
            uri="http://test.org/data/testorg/datasets/restricted/rows/1",
            resource_type=ResourceType.IRI,
            source="testorg",
            name="Restricted Resource",
            organization=test_organization,
            public_access_level='restricted',
            is_public_approved=True
        )
        
        api_client.force_authenticate(user=test_user)
        
        url = reverse('metadata:resource_relationships', kwargs={'resource_id': restricted_resource.id})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK