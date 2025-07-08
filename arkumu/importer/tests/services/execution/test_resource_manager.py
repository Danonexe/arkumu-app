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
    
    def test_initialization(self, test_organization_code, test_base_uri, execution_statistics):
        """Test ResourceManager initialization"""
        manager = ResourceManager(
            institution=test_organization_code,
            base_uri=test_base_uri,
            statistics=execution_statistics
        )
        
        assert manager.institution == test_organization_code.lower().replace('_', '-').replace(' ', '-')
        assert manager.base_uri == test_base_uri
        assert manager.statistics is execution_statistics
        
        # Verify standard properties initialization (may be None if DB operations fail)
        assert hasattr(manager, 'has_part_prop')
        assert hasattr(manager, 'rdf_value_prop')
        assert hasattr(manager, 'dcterms_relation_prop')
    
    def test_initialization_with_special_institution_name(self, test_base_uri, execution_statistics):
        """Test initialization with institution name requiring slugification"""
        special_names = [
            "Test University",
            "University@Example.org",
            "Test-University_123",
            "Université de Test"
        ]
        
        for institution in special_names:
            manager = ResourceManager(
                institution=institution,
                base_uri=test_base_uri,
                statistics=execution_statistics
            )
            
            # Institution should be slugified
            assert ' ' not in manager.institution
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
    
    def test_generate_cell_uri(self, resource_manager):
        """Test cell URI generation"""
        uri = resource_manager.generate_cell_uri("test_dataset", "column_name", "123")
        
        assert isinstance(uri, str)
        assert "datasets" in uri
        assert "test-dataset" in uri  # Slugified version with hyphen
        assert "column-name" in uri  # Slugified version with hyphen
        assert "123" in uri
        assert uri.startswith(resource_manager.base_uri)
    
    def test_generate_entity_uri(self, resource_manager):
        """Test entity URI generation"""
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
    
    def test_extract_row_id_from_uri(self, resource_manager):
        """Test extracting row ID from cell URI"""
        cell_uri = resource_manager.generate_cell_uri("dataset", "column", "row_123")
        row_id = resource_manager.extract_row_id_from_uri(cell_uri)
        
        assert row_id == "row-123"  # Slugified version with hyphen
    
    def test_extract_row_id_from_invalid_uri(self, resource_manager):
        """Test extracting row ID from invalid URI"""
        invalid_uri = "not/a/valid/uri"
        row_id = resource_manager.extract_row_id_from_uri(invalid_uri)
        
        assert row_id == "uri"  # Last part of the URI
    
    def test_extract_column_name_from_uri(self, resource_manager):
        """Test extracting column name from cell URI"""
        cell_uri = resource_manager.generate_cell_uri("dataset", "column_name", "row_123")
        column_name = resource_manager.extract_column_name_from_uri(cell_uri)
        
        assert column_name == "column-name"  # Slugified version with hyphen
    
    def test_extract_column_name_from_invalid_uri(self, resource_manager):
        """Test extracting column name from invalid URI"""
        invalid_uri = "not/a/valid/uri"
        column_name = resource_manager.extract_column_name_from_uri(invalid_uri)
        
        assert column_name is None
    
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
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_create_cell_resources_bulk(self, mock_filter, mock_bulk_create, resource_manager):
        """Test bulk cell resource creation"""
        # Mock created resources
        mock_resources = [create_mock_resource(i, f"test://cell_{i}") for i in range(3)]
        mock_filter.return_value = mock_resources
        
        cell_data = [
            ("dataset", "col1", "row1"),
            ("dataset", "col1", "row2"),
            ("dataset", "col2", "row1")
        ]
        
        result = resource_manager.create_cell_resources_bulk(cell_data)
        
        # Verify bulk creation was called
        mock_bulk_create.assert_called_once()
        assert len(result) == 3
        
        # Verify statistics
        assert resource_manager.statistics.current_metrics.resources_created == 3
    
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
        """Test value truncation for large values"""
        # Test normal value (no truncation)
        normal_value = "normal value"
        result = resource_manager._truncate_value_if_needed(normal_value)
        assert result == normal_value
        
        # Test very long value (should be truncated)
        long_value = "x" * 2000  # Longer than MAX_INDEXED_VALUE_SIZE
        result = resource_manager._truncate_value_if_needed(long_value)
        
        assert len(result.encode('utf-8')) <= 1003  # MAX_INDEXED_VALUE_SIZE + "..." 
        assert result.endswith("...")
        assert resource_manager.statistics.current_metrics.values_truncated == 1
    
    def test_truncate_value_unicode_handling(self, resource_manager):
        """Test value truncation with Unicode characters"""
        # Create a long Unicode string
        unicode_value = "测试" * 600  # Should exceed byte limit
        result = resource_manager._truncate_value_if_needed(unicode_value)
        
        # Should handle Unicode correctly during truncation
        assert result.endswith("...")
        assert len(result.encode('utf-8')) <= 1003
    
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
        assert resource_manager.statistics.current_metrics.values_created == 2
    
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
        assert call_args[1]['defaults']['source'] == "ORCID"
        assert call_args[1]['defaults']['is_placeholder'] is False
    
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
class TestResourceManagerPerformance:
    """Performance tests for ResourceManager"""
    
    @patch('arkumu.metadata.models.Resource.objects.bulk_create')
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_bulk_cell_creation_performance(self, mock_filter, mock_bulk_create, resource_manager):
        """Test performance of bulk cell resource creation"""
        # Mock return values
        mock_resources = [create_mock_resource(i, f"test://cell_{i}") for i in range(1000)]
        mock_filter.return_value = mock_resources
        
        # Create large dataset
        cell_data = [
            ("dataset", f"col_{i % 10}", f"row_{i}")
            for i in range(1000)
        ]
        
        import time
        start_time = time.time()
        
        result = resource_manager.create_cell_resources_bulk(cell_data)
        
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
            cell_uri = resource_manager.generate_cell_uri(name, "column", "row")
            
            # URIs should be valid
            assert isinstance(dataset_uri, str)
            assert isinstance(column_uri, str)
            assert isinstance(cell_uri, str)
    
    def test_value_truncation_edge_cases(self, resource_manager):
        """Test value truncation with edge cases"""
        edge_cases = [
            "",  # Empty string
            "a",  # Single character
            "a" * 999,  # Just under limit
            "a" * 1000,  # At limit
            "a" * 1001,  # Just over limit
            "测试" * 500,  # Unicode characters
        ]
        
        for value in edge_cases:
            result = resource_manager._truncate_value_if_needed(value)
            
            # Should handle all cases gracefully
            assert isinstance(result, str)
            if value:  # Non-empty
                assert len(result.encode('utf-8')) <= 1003  # MAX + "..."
    
    def test_empty_bulk_operations(self, resource_manager):
        """Test bulk operations with empty data"""
        # Empty cell data
        with patch('arkumu.metadata.models.Resource.objects.bulk_create') as mock_bulk:
            result = resource_manager.create_cell_resources_bulk([])
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
        """Test handling of None institution"""
        manager = ResourceManager(
            institution=None,
            base_uri=test_base_uri,
            statistics=execution_statistics
        )
        
        assert manager.institution == "default"
    
    def test_statistics_without_execution_statistics(self, test_organization_code, test_base_uri):
        """Test ResourceManager without ExecutionStatistics"""
        manager = ResourceManager(
            institution=test_organization_code,
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
    
    def test_uri_extraction_edge_cases(self, resource_manager):
        """Test URI extraction with edge cases"""
        edge_cases = [
            "",
            "/",
            "///",
            "http://",
            "single_part",
            "http://example.org/path/to/resource"
        ]
        
        for uri in edge_cases:
            # Should not raise errors
            row_id = resource_manager.extract_row_id_from_uri(uri)
            column_name = resource_manager.extract_column_name_from_uri(uri)
            
            # Results can be None or string
            assert row_id is None or isinstance(row_id, str)
            assert column_name is None or isinstance(column_name, str)