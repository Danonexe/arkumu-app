import pytest
from django.test import TestCase
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.models import IngestSession
from arkumu.users.models import Organization, User


@pytest.mark.django_db
class TestTripleProvenance(TestCase):
    """Test triple-level provenance tracking."""
    
    def setUp(self):
        """Set up test data."""
        # Create test organization and user
        self.org = Organization.objects.create(
            code='TEST_ORG',
            name='Test Organization'
        )
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user.organization = self.org
        self.user.save()
        
        # Create test ingest session
        self.session = IngestSession.objects.create(
            user=self.user,
            organization=self.org,
            dataset_name='test_dataset',
            status='completed'
        )
        
        # Create test resources
        self.subject = Resource.objects.create(
            uri='http://example.org/entity/1',
            resource_type=ResourceType.IRI,
            name='Entity 1'
        )
        
        self.predicate = Resource.objects.create(
            uri='http://example.org/property/name',
            resource_type=ResourceType.PROPERTY,
            name='name'
        )
        
        self.literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value='Test Value',
            datatype='http://www.w3.org/2001/XMLSchema#string',
            # Note: source should be null for literals
            source=None
        )
    
    def test_create_archival_triple_with_source(self):
        """Test creating a triple from an archive import."""
        triple = Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=self.org,
            is_derived=False
        )
        
        self.assertEqual(triple.source, self.org)
        self.assertFalse(triple.is_derived)
    
    def test_create_derived_triple_without_source(self):
        """Test creating a system-generated triple."""
        triple = Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=None,
            is_derived=True
        )
        
        self.assertIsNone(triple.source)
        self.assertTrue(triple.is_derived)
    
    def test_literal_resources_have_no_source(self):
        """Test that literal resources have no source tracking."""
        self.assertIsNone(self.literal.source)
        self.assertIsNone(self.literal.organization)
    
    def test_triple_manager_for_user(self):
        """Test triple access control based on user."""
        # Create triples with different access levels
        
        # Organization's own triple
        org_triple = Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=self.org,
            is_derived=False
        )
        
        # Derived triple (should be visible to all)
        derived_triple = Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.subject,  # Different object to avoid unique constraint
            source=None,
            is_derived=True
        )
        
        # Test authenticated user from same org
        user_triples = Triple.objects.for_user(self.user)
        self.assertIn(org_triple, user_triples)
        self.assertIn(derived_triple, user_triples)
    
    def test_unique_constraints(self):
        """Test that unique constraints work as expected."""
        # Create first triple
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=self.org,
            is_derived=False
        )
        
        # Same triple from different source should work
        org2 = Organization.objects.create(
            code='TEST_ORG_2',
            name='Test Organization 2'
        )
        
        triple2 = Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=org2,
            is_derived=False
        )
        
        self.assertIsNotNone(triple2)
        
        # Derived triple must be unique
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=self.literal,
            source=None,
            is_derived=True
        )
        
        # Second derived triple with same S-P-O should fail
        with self.assertRaises(Exception):
            Triple.objects.create(
                subject=self.subject,
                predicate=self.predicate,
                object=self.literal,
                source=None,
                is_derived=True
            )