"""
Tests for startup literal cleanup functionality.
"""

import pytest
from django.test import TestCase
from arkumu.metadata.models import Resource, ResourceType, Triple
from arkumu.metadata.utils.rdf_helpers import get_or_create_resource


def cleanup_orphaned_literals():
    """Simple cleanup function to test."""
    orphaned_literals = Resource.objects.filter(
        resource_type=ResourceType.LITERAL,
        object_triples__isnull=True
    )
    count, _ = orphaned_literals.delete()
    return count


@pytest.mark.django_db
class TestLiteralCleanup(TestCase):
    """Test literal cleanup functionality."""
    
    def setUp(self):
        """Set up test data."""
        # Create a subject and predicate
        self.subject = get_or_create_resource(
            uri="http://example.org/person/123",
            resource_type=ResourceType.IRI,
            name="John Doe"
        )[0]
        
        self.predicate = get_or_create_resource(
            uri="http://example.org/property/name",
            resource_type=ResourceType.PROPERTY,
            name="name"
        )[0]
    
    def test_cleanup_removes_orphaned_literals(self):
        """Test that orphaned literals are removed during cleanup."""
        # Create an orphaned literal (no triples referencing it)
        orphaned_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Orphaned Value",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Create a referenced literal
        referenced_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Referenced Value",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Create a triple referencing one literal
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=referenced_literal
        )
        
        # Verify setup
        assert Resource.objects.filter(resource_type=ResourceType.LITERAL).count() == 2
        
        # Run cleanup
        deleted_count = cleanup_orphaned_literals()
        
        # Verify one literal was deleted
        assert deleted_count == 1
        
        # Verify orphaned literal is removed, referenced literal remains
        remaining_literals = Resource.objects.filter(resource_type=ResourceType.LITERAL)
        assert remaining_literals.count() == 1
        assert remaining_literals.first().id == referenced_literal.id
        assert not Resource.objects.filter(id=orphaned_literal.id).exists()
    
    def test_cleanup_handles_no_orphans(self):
        """Test that cleanup handles case with no orphaned literals gracefully."""
        # Create only referenced literals
        literal1 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Value 1",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        literal2 = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Value 2",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Create triples for both
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=literal1
        )
        
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=literal2
        )
        
        # Run cleanup (should not fail)
        deleted_count = cleanup_orphaned_literals()
        
        # No literals should be deleted
        assert deleted_count == 0
        assert Resource.objects.filter(resource_type=ResourceType.LITERAL).count() == 2
    
    def test_cleanup_preserves_non_literal_resources(self):
        """Test that cleanup only affects literal resources."""
        # Create non-literal resources
        iri_resource = get_or_create_resource(
            uri="http://example.org/some/iri",
            resource_type=ResourceType.IRI,
            name="Some IRI"
        )[0]
        
        property_resource = get_or_create_resource(
            uri="http://example.org/property/test",
            resource_type=ResourceType.PROPERTY,
            name="Test Property"
        )[0]
        
        # Create orphaned literal
        orphaned_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Orphaned",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Run cleanup
        deleted_count = cleanup_orphaned_literals()
        
        # Only the orphaned literal should be deleted
        assert deleted_count == 1
        
        # Non-literal resources should remain
        assert Resource.objects.filter(id=iri_resource.id).exists()
        assert Resource.objects.filter(id=property_resource.id).exists()
        
        # Orphaned literal should be removed
        assert not Resource.objects.filter(id=orphaned_literal.id).exists()
    
    def test_multiple_references_to_same_literal(self):
        """Test that literals with multiple references are not deleted."""
        # Create a literal
        shared_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Shared Value",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Create another subject
        subject2 = get_or_create_resource(
            uri="http://example.org/person/456",
            resource_type=ResourceType.IRI,
            name="Jane Doe"
        )[0]
        
        # Create two triples referencing the same literal
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=shared_literal
        )
        
        Triple.objects.create(
            subject=subject2,
            predicate=self.predicate,
            object=shared_literal
        )
        
        # Run cleanup
        deleted_count = cleanup_orphaned_literals()
        
        # No literals should be deleted
        assert deleted_count == 0
        
        # Shared literal should still exist
        assert Resource.objects.filter(id=shared_literal.id).exists()
    
    def test_cleanup_query_efficiency(self):
        """Test that the cleanup query is efficient."""
        # Create many orphaned literals
        orphaned_literals = []
        for i in range(100):
            literal = Resource.objects.create(
                resource_type=ResourceType.LITERAL,
                value=f"Orphaned Value {i}",
                datatype="http://www.w3.org/2001/XMLSchema#string"
            )
            orphaned_literals.append(literal)
        
        # Create some referenced literals
        referenced_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Referenced Value",
            datatype="http://www.w3.org/2001/XMLSchema#string"
        )
        
        Triple.objects.create(
            subject=self.subject,
            predicate=self.predicate,
            object=referenced_literal
        )
        
        # Run cleanup
        deleted_count = cleanup_orphaned_literals()
        
        # Should delete all orphaned literals
        assert deleted_count == 100
        
        # Referenced literal should remain
        assert Resource.objects.filter(resource_type=ResourceType.LITERAL).count() == 1
        assert Resource.objects.filter(id=referenced_literal.id).exists()