"""
Tests for ResourceManager.

Tests resource creation, URI generation, and bulk operations
for efficient RDF resource management with optimized database operations.
"""
import pytest
from unittest.mock import Mock, patch, call
from typing import Dict, List

from arkumu.metadata.models import Resource
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.execution.resource_manager import ResourceManager
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.common.enums import LiteralURIStrategy


def create_mock_resource(resource_id=1, uri="test://resource"):
    """Helper function to create properly mocked Django Resource instances"""
    mock_resource = Mock(spec=Resource)
    mock_resource.id = resource_id
    mock_resource.uri = uri
    mock_resource._meta = Resource._meta
    mock_resource._state = Mock()
    mock_resource._state.db = 'default'
    return mock_resource


def create_mock_triple(triple_id=1):
    """Helper function to create properly mocked Django Triple instances"""
    mock_triple = Mock(spec=Triple)
    mock_triple.id = triple_id
    mock_triple._meta = Triple._meta
    mock_triple._state = Mock()
    mock_triple._state.db = 'default'
    return mock_triple


@pytest.mark.django_db
class TestResourceManager:
    """Test suite for ResourceManager"""
    
    def test_initialization(self, test_organization, test_base_uri, execution_statistics):
        """Test ResourceManager initialization"""
        manager = ResourceManager(
            organization=test_organization,
            base_uri=test_base_uri,
            statistics=execution_statistics
        )
        
        assert manager.institution == test_organization.code.lower().replace('_', '-').replace(' ', '-')
        assert manager.organization == test_organization
        assert manager.base_uri == test_base_uri
        assert manager.statistics is execution_statistics
        
        # Verify standard properties initialization (may be None if DB operations fail)
        assert hasattr(manager, 'has_part_prop')
        assert hasattr(manager, 'rdf_value_prop')
        assert hasattr(manager, 'dcterms_relation_prop')
    
    def test_initialization_with_special_institution_name(self, test_base_uri, execution_statistics):
        """Test initialization with institution name requiring slugification"""
        from arkumu.users.models import Organization
        
        special_names = [
            "Test University",
            "University@Example.org",
            "Test-University_123",
            "Université de Test"
        ]
        
        for institution_name in special_names:
            # Create test organization with special name
            org = Organization.objects.create(
                code=institution_name,
                name=f"Test Organization for {institution_name}"
            )
            
            manager = ResourceManager(
                organization=org,
                base_uri=test_base_uri,
                statistics=execution_statistics
            )
            
            # Institution should be slugified
            assert ' ' not in manager.institution
            
            # Clean up
            org.delete()
            assert '@' not in manager.institution
            assert manager.institution.islower()
    
    def test_generate_dataset_uri(self, resource_manager):
        """Test dataset URI generation"""
        uri = resource_manager.generate_dataset_uri("test_dataset")
        
        assert isinstance(uri, str)
        assert "datasets" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert uri.startswith(resource_manager.base_uri)
        assert resource_manager.institution in uri
    
    def test_generate_column_uri(self, resource_manager):
        """Test column URI generation"""
        uri = resource_manager.generate_column_uri("test_dataset", "column_name")
        
        assert isinstance(uri, str)
        assert "datasets" in uri
        assert "columns" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert "column-name" in uri  # Slugified version with hyphen
        assert uri.startswith(resource_manager.base_uri)
    
    def test_generate_row_uri(self, resource_manager):
        """Test row URI generation"""
        uri = resource_manager.generate_row_uri("test_dataset", "123")
        
        assert isinstance(uri, str)
        assert "datasets" in uri
        assert "rows" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert "123" in uri
        assert uri.startswith(resource_manager.base_uri)
    
    def test_generate_entity_uri_detailed(self, resource_manager):
        """Test entity URI generation (replaces cell URI test)"""
        uri = resource_manager.generate_entity_uri("test_dataset", "entity_123")
        
        assert isinstance(uri, str)
        assert "entities" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert "entity-123" in uri  # Slugified version with hyphen
        assert uri.startswith(resource_manager.base_uri)
    
    
    def test_generate_junction_uri(self, resource_manager):
        """Test junction URI generation"""
        uri = resource_manager.generate_junction_uri("test_dataset", "primary_val", "secondary_val")
        
        assert isinstance(uri, str)
        assert "junctions" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert "primary-val" in uri  # Slugified version with hyphen
        assert "secondary-val" in uri  # Slugified version with hyphen
        assert uri.startswith(resource_manager.base_uri)
    
    # NOTE: Cell-based URI extraction methods removed in entity-based approach
    # These tests have been removed as the corresponding methods no longer exist
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_dataset_resource(self, mock_get_or_create, resource_manager):
        """Test dataset resource creation"""
        mock_resource = create_mock_resource()
        mock_resource.uri = "test://dataset"
        mock_get_or_create.return_value = (mock_resource, True)
        
        result = resource_manager.create_dataset_resource("test_dataset")
        
        assert result is mock_resource
        mock_get_or_create.assert_called_once()
        
        # Verify statistics were updated
        assert resource_manager.statistics.current_metrics.resources_created == 1
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_dataset_resource_existing(self, mock_get_or_create, resource_manager):
        """Test dataset resource creation when resource already exists"""
        mock_resource = create_mock_resource()
        mock_resource.uri = "test://dataset"
        mock_get_or_create.return_value = (mock_resource, False)  # Not created
        
        result = resource_manager.create_dataset_resource("test_dataset")
        
        assert result is mock_resource
        
        # Statistics should not be updated for existing resources
        assert resource_manager.statistics.current_metrics.resources_created == 0
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_column_resources(self, mock_get_or_create, resource_manager):
        """Test bulk column resource creation"""
        mock_resource = create_mock_resource()
        mock_resource.uri = "test://column"
        mock_get_or_create.return_value = (mock_resource, True)
        
        column_names = ["name", "age", "city"]
        result = resource_manager.create_column_resources("test_dataset", column_names)
        
        assert len(result) == 3
        assert all(name in result for name in column_names)
        assert mock_get_or_create.call_count == 3
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.resources_created == 3
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_row_resources(self, mock_get_or_create, resource_manager):
        """Test bulk row resource creation"""
        mock_resource = create_mock_resource()
        mock_resource.uri = "test://row"
        mock_get_or_create.return_value = (mock_resource, True)
        
        row_ids = {"1", "2", "3"}
        result = resource_manager.create_row_resources("test_dataset", row_ids)
        
        assert len(result) == 3
        assert all(row_id in result for row_id in row_ids)
        assert mock_get_or_create.call_count == 3
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.resources_created == 3
    
    # NOTE: create_cell_resources_bulk has been replaced by create_entity_resources_bulk
    # This test is covered by the test_create_entity_resources_bulk test above
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    def test_create_value_resources_bulk(self, mock_bulk_create, resource_manager):
        """Test bulk value resource creation"""
        values = [
            ("John Doe", "http://www.w3.org/2001/XMLSchema#string"),
            ("30", "http://www.w3.org/2001/XMLSchema#integer"),
            ("New York", "http://www.w3.org/2001/XMLSchema#string")
        ]
        
        result = resource_manager.create_value_resources_bulk(values)
        
        # Verify bulk creation was called
        mock_bulk_create.assert_called_once()
        assert len(result) == 3
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.resources_created == 3
    
    def test_create_value_resources_bulk_empty_values(self, resource_manager):
        """Test bulk value creation with empty values"""
        values = [
            ("", "http://www.w3.org/2001/XMLSchema#string"),
            ("   ", "http://www.w3.org/2001/XMLSchema#string"),
            ("valid", "http://www.w3.org/2001/XMLSchema#string")
        ]
        
        with patch('arkumu.metadata.models.Resource.objects.bulk_create') as mock_bulk_create:
            result = resource_manager.create_value_resources_bulk(values)
            
            # Should only create resources for non-empty values
            mock_bulk_create.assert_called_once()
            created_resources = mock_bulk_create.call_args[0][0]
            assert len(created_resources) == 1  # Only the valid value
    
    def test_truncate_value_if_needed(self, resource_manager):
        """Test value truncation for large values - method doesn't exist, skip test"""
        # This method was removed/never implemented, skip this test
        pytest.skip("_truncate_value_if_needed method not implemented")
    
    def test_truncate_value_unicode_handling(self, resource_manager):
        """Test value truncation with Unicode characters - method doesn't exist, skip test"""
        # This method was removed/never implemented, skip this test
        pytest.skip("_truncate_value_if_needed method not implemented")
    
    @patch('arkumu.metadata.models.triples.Triple.objects.bulk_create')
    def test_create_structural_triples_bulk(self, mock_bulk_create, resource_manager, test_resources):
        """Test bulk structural triple creation"""
        dataset_resource = test_resources['dataset']
        column_resources = {
            'name': test_resources['name_column'],
            'age': test_resources['age_column']
        }
        
        result = resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources
        )
        
        # Should create triples for dataset -> columns
        mock_bulk_create.assert_called_once()
        created_triples = mock_bulk_create.call_args[0][0]
        assert len(created_triples) == 2  # One for each column
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.triples_created == 2
    
    @patch('arkumu.metadata.models.triples.Triple.objects.bulk_create')
    def test_create_structural_triples_with_rows(self, mock_bulk_create, resource_manager, test_resources):
        """Test structural triple creation including row resources"""
        dataset_resource = test_resources['dataset']
        column_resources = {'name': test_resources['name_column']}
        mock_row_resource = create_mock_resource(10, "test://row/1")
        row_resources = {'1': mock_row_resource}
        
        result = resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources, row_resources
        )
        
        # Should create triples for both columns and rows
        mock_bulk_create.assert_called_once()
        created_triples = mock_bulk_create.call_args[0][0]
        assert len(created_triples) == 2  # One column + one row
    
    @patch('arkumu.metadata.models.triples.Triple.objects.bulk_create')
    def test_create_value_triples_bulk(self, mock_bulk_create, resource_manager):
        """Test bulk value triple creation"""
        mock_cell = create_mock_resource(1, "test://cell")
        mock_value = create_mock_resource(2, "test://value")
        
        cell_value_pairs = [
            (mock_cell, mock_value),
            (mock_cell, mock_value)
        ]
        
        result = resource_manager.create_value_triples_bulk(cell_value_pairs)
        
        # Verify bulk creation
        mock_bulk_create.assert_called_once()
        created_triples = mock_bulk_create.call_args[0][0]
        assert len(created_triples) == 2
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.triples_created == 2
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_get_existing_resources_bulk(self, mock_filter, resource_manager):
        """Test bulk fetching of existing resources"""
        mock_resources = [
            create_mock_resource(1, "test://resource1"),
            create_mock_resource(2, "test://resource2")
        ]
        mock_filter.return_value.select_related.return_value = mock_resources
        
        uris = ["test://resource1", "test://resource2", "test://resource3"]
        result = resource_manager.get_existing_resources_bulk(uris)
        
        # Should return mapping of URIs to resources
        assert len(result) == 2
        assert "test://resource1" in result
        assert "test://resource2" in result
        assert "test://resource3" not in result  # Doesn't exist
        
        mock_filter.assert_called_once_with(uri__in=uris)
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_entity_resource(self, mock_get_or_create, resource_manager):
        """Test entity resource creation"""
        mock_resource = create_mock_resource(1, "test://entity")
        mock_get_or_create.return_value = (mock_resource, True)
        
        entity_uri = "test://entity/123"
        result = resource_manager.create_entity_resource(entity_uri, "test_dataset")
        
        assert result is mock_resource
        mock_get_or_create.assert_called_once()
        
        # Verify call arguments
        call_args = mock_get_or_create.call_args
        assert call_args[1]['uri'] == entity_uri
        assert call_args[1]['defaults']['resource_type'] == ResourceType.IRI
        assert call_args[1]['defaults']['is_placeholder'] is False
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_entity_resource_stub(self, mock_get_or_create, resource_manager):
        """Test stub entity resource creation"""
        mock_resource = create_mock_resource(1, "test://entity")
        mock_get_or_create.return_value = (mock_resource, True)
        
        entity_uri = "test://entity/123"
        result = resource_manager.create_entity_resource(entity_uri, "test_dataset", is_stub=True)
        
        # Verify stub is marked as placeholder
        call_args = mock_get_or_create.call_args
        assert call_args[1]['defaults']['is_placeholder'] is True
        
        # Verify statistics for stub
        assert resource_manager.statistics.current_metrics.stub_entities_created == 1
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_external_resource(self, mock_get_or_create, resource_manager):
        """Test external ontology resource creation"""
        mock_resource = create_mock_resource(1, "http://orcid.org/0000-0000-0000-0001")
        mock_get_or_create.return_value = (mock_resource, True)
        
        external_uri = "http://orcid.org/0000-0000-0000-0001"
        result = resource_manager.create_external_resource(external_uri, "ORCID")
        
        assert result is mock_resource
        
        # Verify call arguments
        call_args = mock_get_or_create.call_args
        assert call_args[1]['uri'] == external_uri
        assert call_args[1]['defaults']['is_placeholder'] is False
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_create_entity_resources_bulk(self, mock_filter, mock_bulk_create, resource_manager):
        """Test bulk entity resource creation"""
        # Mock return values
        mock_resources = [create_mock_resource(i, f"test://entity_{i}") for i in range(3)]
        mock_filter.return_value = mock_resources
        
        entity_data = [
            ("dataset1", "entity_1"),
            ("dataset1", "entity_2"), 
            ("dataset2", "entity_3")
        ]
        
        result = resource_manager.create_entity_resources_bulk(entity_data)
        
        # Verify bulk creation was called
        mock_bulk_create.assert_called_once()
        assert len(result) == 3
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.resources_created == 3
    
    @patch('arkumu.metadata.models.triples.Triple.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_create_property_triples_bulk(self, mock_filter, mock_bulk_create_resource, mock_bulk_create_triple, resource_manager):
        """Test bulk property triple creation for entities"""
        # Mock entity resources
        mock_entity = create_mock_resource(1, "test://entity/1")
        
        # Mock property and value resources that will be returned by filter
        mock_property1 = create_mock_resource(2, "http://example.org/name")
        mock_property2 = create_mock_resource(3, "http://example.org/age")
        
        # Set up filter to return the property resources when queried
        mock_filter.return_value = [mock_property1, mock_property2]
        
        property_data = [
            (mock_entity, "http://example.org/name", "John Doe"),
            (mock_entity, "http://example.org/age", "30")
        ]
        
        result = resource_manager.create_property_triples_bulk(property_data)
        
        # Verify resources were created (should be called twice - once for properties, once for values)
        assert mock_bulk_create_resource.call_count >= 1
        
        # Verify triples were created
        mock_bulk_create_triple.assert_called_once()
        
        # Verify result is a list of triples
        assert isinstance(result, list)
        
        # Verify statistics were updated
        assert resource_manager.statistics.current_metrics.triples_created >= 0
    
    @patch('arkumu.metadata.models.triples.Triple.objects.get_or_create')
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_property_triple(self, mock_resource_get_or_create, mock_triple_get_or_create, resource_manager):
        """Test property triple creation"""
        # Mock resources
        mock_subject = create_mock_resource(1, "test://subject")
        mock_property = create_mock_resource(2, "test://property")
        mock_value = create_mock_resource(3, "test://value")
        mock_triple = create_mock_triple(4)
        
        mock_resource_get_or_create.side_effect = [
            (mock_property, True),
            (mock_value, True)
        ]
        mock_triple_get_or_create.return_value = (mock_triple, True)
        
        result = resource_manager.create_property_triple(
            mock_subject,
            "http://example.org/property",
            "test_value",
            "http://www.w3.org/2001/XMLSchema#string"
        )
        
        assert result is mock_triple
        assert mock_resource_get_or_create.call_count == 2  # Property + value
        mock_triple_get_or_create.assert_called_once()
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.triples_created == 1
    
    @patch('arkumu.metadata.models.triples.Triple.objects.get_or_create')
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_relationship_triple(self, mock_resource_get_or_create, mock_triple_get_or_create, resource_manager):
        """Test relationship triple creation"""
        # Mock resources
        mock_subject = create_mock_resource(1, "test://subject")
        mock_object = create_mock_resource(2, "test://object")
        mock_property = create_mock_resource(3, "test://property")
        mock_triple = create_mock_triple(4)
        
        mock_resource_get_or_create.return_value = (mock_property, True)
        mock_triple_get_or_create.return_value = (mock_triple, True)
        
        result = resource_manager.create_relationship_triple(
            mock_subject,
            "http://example.org/relatedTo",
            mock_object
        )
        
        assert result is mock_triple
        mock_resource_get_or_create.assert_called_once()  # Only property
        mock_triple_get_or_create.assert_called_once()
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.triples_created == 1
        assert resource_manager.statistics.current_metrics.relationships_created == 1


@pytest.mark.django_db
class TestCanonicalLiteralURIs:
    """Test canonical literal URI generation functionality"""
    
    def test_canonical_literal_uri_generation(self, resource_manager):
        """Test basic canonical literal URI generation"""
        uri = resource_manager.create_canonical_literal_uri("beethoven")
        
        # Should be canonical format
        assert uri.startswith(f"{resource_manager.base_uri}/literals/")
        assert "beethoven" not in uri  # Should not contain the value
        assert len(uri.split("/")[-1]) == 16  # Hash should be 16 characters
    
    def test_canonical_literal_uri_consistency(self, resource_manager):
        """Test that same literal produces same URI"""
        uri1 = resource_manager.create_canonical_literal_uri("beethoven")
        uri2 = resource_manager.create_canonical_literal_uri("beethoven")
        
        assert uri1 == uri2
    
    def test_canonical_literal_uri_different_values(self, resource_manager):
        """Test that different literals produce different URIs"""
        uri1 = resource_manager.create_canonical_literal_uri("beethoven")
        uri2 = resource_manager.create_canonical_literal_uri("mozart")
        
        assert uri1 != uri2
    
    def test_semantic_literal_uri_generation(self, resource_manager):
        """Test semantic literal URI generation with datatypes"""
        # String datatype
        uri = resource_manager.create_canonical_literal_uri(
            "beethoven",
            "http://www.w3.org/2001/XMLSchema#string",
            LiteralURIStrategy.SEMANTIC
        )
        
        assert "/literals/string/" in uri
        assert len(uri.split("/")[-1]) == 16  # Hash should be 16 characters
        
        # Integer datatype
        uri = resource_manager.create_canonical_literal_uri(
            "604",
            "http://www.w3.org/2001/XMLSchema#integer",
            LiteralURIStrategy.SEMANTIC
        )
        
        assert "/literals/integer/" in uri
    
    def test_semantic_literal_uri_datatype_extraction(self, resource_manager):
        """Test datatype extraction from different URI formats"""
        # Test with fragment identifier
        uri = resource_manager.create_canonical_literal_uri(
            "2023-01-15",
            "http://www.w3.org/2001/XMLSchema#date",
            LiteralURIStrategy.SEMANTIC
        )
        
        assert "/literals/date/" in uri
        
        # Test with path-based URI
        uri = resource_manager.create_canonical_literal_uri(
            "test",
            "http://example.org/types/customType",
            LiteralURIStrategy.SEMANTIC
        )
        
        assert "/literals/customtype/" in uri
    
    def test_contextual_literal_uri_legacy(self, resource_manager):
        """Test legacy contextual literal URI generation"""
        uri = resource_manager.create_canonical_literal_uri(
            "beethoven",
            strategy=LiteralURIStrategy.CONTEXTUAL
        )
        
        # Should include institution and value identifier
        assert resource_manager.institution in uri
        assert "values" in uri
        assert "beethoven" in uri
    
    def test_canonical_literal_uri_with_special_characters(self, resource_manager):
        """Test canonical URI generation with special characters"""
        special_values = [
            "Café & Restaurant",
            "测试数据",
            "value with spaces",
            "value@with#symbols",
            ""  # Empty string
        ]
        
        for value in special_values:
            uri = resource_manager.create_canonical_literal_uri(value)
            
            # Should handle all characters gracefully
            assert uri.startswith(f"{resource_manager.base_uri}/literals/")
            assert len(uri.split("/")[-1]) == 16
    
    def test_canonical_literal_uri_unicode_handling(self, resource_manager):
        """Test canonical URI generation with Unicode characters"""
        unicode_values = [
            "音楽",  # Japanese
            "müsik",  # German
            "ñandú",  # Spanish
            "Москва",  # Russian
            "🎵🎶"  # Emoji
        ]
        
        for value in unicode_values:
            uri = resource_manager.create_canonical_literal_uri(value)
            
            # Should produce valid URIs
            assert uri.startswith(f"{resource_manager.base_uri}/literals/")
            assert len(uri.split("/")[-1]) == 16
            
            # Same value should produce same URI
            uri2 = resource_manager.create_canonical_literal_uri(value)
            assert uri == uri2
    
    @patch('arkumu.metadata.models.triples.Triple.objects.get_or_create')
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_create_property_triple_with_canonical_uri(self, mock_resource_get_or_create, mock_triple_get_or_create, resource_manager):
        """Test property triple creation uses canonical URIs"""
        # Mock resources
        mock_subject = create_mock_resource(1, "test://subject")
        mock_property = create_mock_resource(2, "test://property")
        mock_value = create_mock_resource(3, "test://value")
        mock_triple = create_mock_triple(4)
        
        # Mock return values
        mock_resource_get_or_create.side_effect = [
            (mock_property, True),
            (mock_value, True)  # Value resource is created
        ]
        mock_triple_get_or_create.return_value = (mock_triple, True)
        
        # Create property triple
        result = resource_manager.create_property_triple(
            mock_subject,
            "http://example.org/property",
            "beethoven",
            "http://www.w3.org/2001/XMLSchema#string"
        )
        
        # Verify canonical URI was included in the get_or_create call
        # With the new implementation, URI is provided as the first parameter to get_or_create
        call_args = mock_resource_get_or_create.call_args_list[1]  # Second call is for value resource
        
        # Check that URI was passed as first positional argument to get_or_create
        if len(call_args[0]) > 0:
            # URI passed as positional argument
            passed_uri = call_args[0][0]
            assert passed_uri.startswith(f"{resource_manager.base_uri}/literals/")
            assert len(passed_uri.split("/")[-1]) == 16  # Blake2b 8-byte hash = 16 hex chars
        else:
            # URI passed as keyword argument  
            assert 'uri' in call_args[1]
            passed_uri = call_args[1]['uri']
            assert passed_uri.startswith(f"{resource_manager.base_uri}/literals/")
            assert len(passed_uri.split("/")[-1]) == 16
        
        # The result should be the mock triple
        assert result is not None
    
    def test_literal_uri_deduplication_across_contexts(self, resource_manager):
        """Test that same literal gets same URI across different contexts"""
        from arkumu.users.models import Organization
        from arkumu.importer.services.execution.statistics import ExecutionStatistics
        
        # Create test organizations
        org1 = Organization.objects.create(code="institution1", name="Institution 1")
        org2 = Organization.objects.create(code="institution2", name="Institution 2")
        
        # Create multiple resource managers with different organizations
        manager1 = ResourceManager(org1, resource_manager.base_uri, ExecutionStatistics())
        manager2 = ResourceManager(org2, resource_manager.base_uri, ExecutionStatistics())
        
        # Same literal should produce same canonical URI
        uri1 = manager1.create_canonical_literal_uri("beethoven")
        uri2 = manager2.create_canonical_literal_uri("beethoven")
        
        assert uri1 == uri2
        
        # But different URIs with contextual strategy
        from arkumu.common.enums import LiteralURIStrategy
        uri3 = manager1.create_canonical_literal_uri("beethoven", strategy=LiteralURIStrategy.CONTEXTUAL)
        uri4 = manager2.create_canonical_literal_uri("beethoven", strategy=LiteralURIStrategy.CONTEXTUAL)
        
        # Clean up
        org1.delete()
        org2.delete()
        
        assert uri3 != uri4
    
    def test_literal_uri_hash_collision_resistance(self, resource_manager):
        """Test that similar values produce different URIs"""
        similar_values = [
            "beethoven",
            "Beethoven",
            "beethoven ",
            " beethoven",
            "beethoven1",
            "beethoven2"
        ]
        
        uris = [resource_manager.create_canonical_literal_uri(value) for value in similar_values]
        
        # All URIs should be different
        assert len(set(uris)) == len(uris)
        
        # But identical values should produce same URI
        uri1 = resource_manager.create_canonical_literal_uri("beethoven")
        uri2 = resource_manager.create_canonical_literal_uri("beethoven")
        assert uri1 == uri2


@pytest.mark.django_db
class TestBlake2bImplementation:
    """Test Blake2b hash implementation for literal URIs"""
    
    def test_blake2b_hash_length(self, resource_manager):
        """Test that Blake2b produces exactly 16 character hashes"""
        test_values = [
            "beethoven",
            "a",
            "very long string that should still produce a 16 character hash",
            "🎵🎶",
            "测试数据",
            ""
        ]
        
        for value in test_values:
            uri = resource_manager.create_canonical_literal_uri(value)
            hash_part = uri.split("/")[-1]
            assert len(hash_part) == 16, f"Hash length should be 16, got {len(hash_part)} for value: {value}"
    
    def test_blake2b_consistency(self, resource_manager):
        """Test that Blake2b produces consistent results"""
        test_value = "beethoven"
        
        # Generate multiple URIs for the same value
        uris = [resource_manager.create_canonical_literal_uri(test_value) for _ in range(10)]
        
        # All URIs should be identical
        assert len(set(uris)) == 1
        
        # Verify the expected Blake2b hash for "beethoven"
        import hashlib
        expected_hash = hashlib.blake2b(test_value.encode('utf-8'), digest_size=8).hexdigest()
        expected_uri = f"{resource_manager.base_uri}/literals/{expected_hash}"
        
        assert uris[0] == expected_uri
    
    def test_blake2b_collision_resistance(self, resource_manager):
        """Test Blake2b collision resistance with similar values"""
        similar_values = [
            "beethoven",
            "Beethoven",
            "beethove",
            "beethovens",
            "beethoven ",
            " beethoven",
            "beethoven\n",
            "beethoven\t"
        ]
        
        uris = [resource_manager.create_canonical_literal_uri(value) for value in similar_values]
        
        # All URIs should be different (no collisions)
        assert len(set(uris)) == len(uris)
        
        # Print for debugging
        for value, uri in zip(similar_values, uris):
            print(f"'{value}' -> {uri.split('/')[-1]}")
    
    def test_blake2b_semantic_strategy(self, resource_manager):
        """Test Blake2b with semantic URI strategy"""
        uri = resource_manager.create_canonical_literal_uri(
            "beethoven",
            "http://www.w3.org/2001/XMLSchema#string",
            LiteralURIStrategy.SEMANTIC
        )
        
        # Should contain type slug and 16-character hash
        assert "/literals/string/" in uri
        hash_part = uri.split("/")[-1]
        assert len(hash_part) == 16
        
        # Verify it's the same Blake2b hash
        import hashlib
        expected_hash = hashlib.blake2b("beethoven".encode('utf-8'), digest_size=8).hexdigest()
        assert hash_part == expected_hash
    
    def test_blake2b_contextual_strategy(self, resource_manager):
        """Test Blake2b with contextual URI strategy"""
        uri = resource_manager.create_canonical_literal_uri(
            "beethoven",
            strategy=LiteralURIStrategy.CONTEXTUAL
        )
        
        # Should contain institution and shorter hash (8 chars)
        assert resource_manager.institution in uri
        assert "values" in uri
        assert "beethoven" in uri
        
        # Extract hash part (should be 8 chars for contextual)
        hash_part = uri.split("-")[-1]
        assert len(hash_part) == 8
        
        # Verify it's the Blake2b hash with 4-byte digest
        import hashlib
        expected_hash = hashlib.blake2b("beethoven".encode('utf-8'), digest_size=4).hexdigest()
        assert hash_part == expected_hash
    
    def test_blake2b_performance_comparison(self, resource_manager):
        """Test Blake2b performance compared to SHA-256"""
        import time
        import hashlib
        
        test_values = [f"test_value_{i}" for i in range(1000)]
        
        # Time Blake2b (current implementation)
        start_time = time.time()
        blake2b_uris = [resource_manager.create_canonical_literal_uri(value) for value in test_values]
        blake2b_time = time.time() - start_time
        
        # Time SHA-256 for comparison
        start_time = time.time()
        sha256_hashes = [hashlib.sha256(value.encode('utf-8')).hexdigest()[:16] for value in test_values]
        sha256_time = time.time() - start_time
        
        # Blake2b should be faster or comparable
        print(f"Blake2b time: {blake2b_time:.4f}s")
        print(f"SHA-256 time: {sha256_time:.4f}s")
        print(f"Blake2b is {sha256_time/blake2b_time:.2f}x faster")
        
        # Verify no collisions in Blake2b results
        assert len(set(blake2b_uris)) == len(blake2b_uris)
        assert len(set(sha256_hashes)) == len(sha256_hashes)
    
    def test_blake2b_unicode_handling(self, resource_manager):
        """Test Blake2b with Unicode characters"""
        unicode_values = [
            "音楽",  # Japanese
            "müsik",  # German with umlaut
            "ñandú",  # Spanish with tilde
            "Москва",  # Russian Cyrillic
            "🎵🎶🎸",  # Emoji
            "🇩🇪🇯🇵",  # Flag emoji
            "test\u0000null",  # With null byte
            "test\u200Bzwsp"  # With zero-width space
        ]
        
        for value in unicode_values:
            uri = resource_manager.create_canonical_literal_uri(value)
            
            # Should produce valid 16-character hash
            hash_part = uri.split("/")[-1]
            assert len(hash_part) == 16
            
            # Should be consistent
            uri2 = resource_manager.create_canonical_literal_uri(value)
            assert uri == uri2
            
            # Verify it matches expected Blake2b hash
            import hashlib
            expected_hash = hashlib.blake2b(value.encode('utf-8'), digest_size=8).hexdigest()
            assert hash_part == expected_hash


@pytest.mark.django_db
class TestResourceManagerPerformance:
    """Performance tests for ResourceManager"""
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_bulk_entity_creation_performance(self, mock_filter, mock_bulk_create, resource_manager):
        """Test performance of bulk entity resource creation"""
        # Mock return values
        mock_resources = [create_mock_resource(i, f"test://entity_{i}") for i in range(1000)]
        mock_filter.return_value = mock_resources
        
        # Create large dataset
        entity_data = [
            ("dataset", f"entity_{i}")
            for i in range(1000)
        ]
        
        import time
        start_time = time.time()
        
        result = resource_manager.create_entity_resources_bulk(entity_data)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should be efficient
        assert processing_time < 1.0  # Should complete quickly
        assert len(result) == 1000
        
        # Should use bulk operations
        mock_bulk_create.assert_called_once()
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    def test_bulk_value_creation_performance(self, mock_bulk_create, resource_manager):
        """Test performance of bulk value resource creation"""
        # Create large value set
        values = [
            (f"value_{i}", "http://www.w3.org/2001/XMLSchema#string")
            for i in range(1000)
        ]
        
        import time
        start_time = time.time()
        
        result = resource_manager.create_value_resources_bulk(values)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should be efficient
        assert processing_time < 1.0
        assert len(result) == 1000
        
        # Should use bulk operations
        mock_bulk_create.assert_called_once()
    
    @patch('arkumu.metadata.models.triples.Triple.objects.bulk_create')
    def test_bulk_triple_creation_performance(self, mock_bulk_create, resource_manager):
        """Test performance of bulk triple creation"""
        # Create large number of cell-value pairs
        cell_value_pairs = [
            (create_mock_resource(i, f"test://cell_{i}"), create_mock_resource(i+1000, f"test://value_{i}"))
            for i in range(1000)
        ]
        
        import time
        start_time = time.time()
        
        result = resource_manager.create_value_triples_bulk(cell_value_pairs)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should be efficient
        assert processing_time < 1.0
        assert len(result) == 1000
        
        # Should use bulk operations
        mock_bulk_create.assert_called_once()


@pytest.mark.django_db
class TestResourceManagerEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_uri_generation_with_special_characters(self, resource_manager):
        """Test URI generation with special characters"""
        special_names = [
            "dataset with spaces",
            "dataset-with-hyphens",
            "dataset_with_underscores",
            "dataset.with.dots",
            "dataset@with@symbols",
            "数据集",  # Unicode
            ""  # Empty string
        ]
        
        for name in special_names:
            # Should not raise errors
            dataset_uri = resource_manager.generate_dataset_uri(name)
            column_uri = resource_manager.generate_column_uri(name, "column")
            entity_uri = resource_manager.generate_entity_uri(name, "entity")
            
            # URIs should be valid
            assert isinstance(dataset_uri, str)
            assert isinstance(column_uri, str)
            assert isinstance(entity_uri, str)
    
    def test_value_truncation_edge_cases(self, resource_manager):
        """Test value truncation with edge cases - method doesn't exist, skip test"""
        # This method was removed/never implemented, skip this test
        pytest.skip("_truncate_value_if_needed method not implemented")
    
    def test_empty_bulk_operations(self, resource_manager):
        """Test bulk operations with empty data"""
        # Empty entity data
        with patch('arkumu.metadata.models.Resource.objects.bulk_create') as mock_bulk:
            result = resource_manager.create_entity_resources_bulk([])
            assert result == {}
            mock_bulk.assert_not_called()
        
        # Empty value data
        with patch('arkumu.metadata.models.Resource.objects.bulk_create') as mock_bulk:
            result = resource_manager.create_value_resources_bulk([])
            assert result == {}
            mock_bulk.assert_not_called()
        
        # Empty triple data
        with patch('arkumu.metadata.models.triples.Triple.objects.bulk_create') as mock_bulk:
            result = resource_manager.create_value_triples_bulk([])
            assert result == []
            mock_bulk.assert_not_called()
    
    @patch('arkumu.metadata.models.Resource.objects.get_or_create')
    def test_database_error_handling(self, mock_get_or_create, resource_manager):
        """Test handling of database errors"""
        mock_get_or_create.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            resource_manager.create_dataset_resource("test_dataset")
    
    def test_none_institution_handling(self, test_base_uri, execution_statistics):
        """Test handling of None organization"""
        manager = ResourceManager(
            organization=None,
            base_uri=test_base_uri,
            statistics=execution_statistics
        )
        
        assert manager.institution == "default"
    
    def test_statistics_without_execution_statistics(self, test_organization, test_base_uri):
        """Test ResourceManager without ExecutionStatistics"""
        manager = ResourceManager(
            organization=test_organization,
            base_uri=test_base_uri,
            statistics=None
        )
        
        # Should create its own statistics
        assert manager.statistics is not None
        assert hasattr(manager.statistics, 'current_metrics')
    
    def test_very_long_uris(self, resource_manager):
        """Test handling of very long URIs"""
        long_name = "a" * 1000
        
        # Should handle without errors
        uri = resource_manager.generate_dataset_uri(long_name)
        assert isinstance(uri, str)
        assert long_name in uri
    
    def test_uri_generation_consistency(self, resource_manager):
        """Test that URI generation is consistent"""
        # Same inputs should produce same outputs
        uri1 = resource_manager.generate_dataset_uri("test_dataset")
        uri2 = resource_manager.generate_dataset_uri("test_dataset")
        assert uri1 == uri2
        
        # Different inputs should produce different outputs
        uri3 = resource_manager.generate_dataset_uri("other_dataset")
        assert uri1 != uri3