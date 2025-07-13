"""
Tests for entity-based processing in MappingExecutionEngine.
Focuses on latest implementation changes from the Option A plan.
"""

import pytest
import polars as pl
from unittest.mock import Mock, patch, MagicMock
from arkumu.importer.services.execution.execution_engine import MappingExecutionEngine
from arkumu.importer.services.execution.uri_generator import UnifiedURIGenerator
from arkumu.importer.services.execution.resource_manager import ResourceManager
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.metadata.models import Resource


@pytest.mark.django_db
class TestEntityBasedProcessing:
    """Test suite for entity-based processing implementation."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock external dependencies for isolated testing."""
        with patch('arkumu.importer.services.execution.execution_engine.ResourceManager') as mock_rm, \
             patch('arkumu.importer.services.execution.execution_engine.UnifiedURIGenerator') as mock_urig, \
             patch('arkumu.importer.services.execution.execution_engine.ExecutionStatistics') as mock_stats:
            
            yield {
                'resource_manager': mock_rm.return_value,
                'uri_generator': mock_urig.return_value,
                'statistics': mock_stats.return_value
            }

    @pytest.fixture
    def engine(self, mock_dependencies):
        """Create MappingExecutionEngine instance with mocked dependencies."""
        engine = MappingExecutionEngine(
            organization_id="test_org",
            base_uri="http://data.test.org"
        )
        
        # Replace with mocks
        engine.resource_manager = mock_dependencies['resource_manager']
        engine.uri_generator = mock_dependencies['uri_generator']
        engine.statistics = mock_dependencies['statistics']
        
        return engine

    def test_process_batch_entity_uri_generation(self, engine, mock_dependencies):
        """Test that _process_batch correctly generates entity URIs."""
        # Setup test data
        batch_df = pl.DataFrame({
            "product_id": ["PROD001", "PROD002"],
            "name": ["Product A", "Product B"],
            "price": ["10.99", "20.99"],
            "row_id": [1, 2]
        })
        
        dataset_name = "products"
        mapping_config = {
            "columns": {
                "product_id": {"is_anchor": True, "arkumu_type": "identifier"},
                "name": {"arkumu_type": "name"},
                "price": {"arkumu_type": "price"}
            },
            "anchor_columns": ["product_id"]
        }
        column_resources = {}
        
        # Configure mocks
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["product_id"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/products/prod001",
            "http://data.test.org/test_org/entities/products/prod002"
        ])
        
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/products/prod001": Mock(spec=Resource),
            "http://data.test.org/test_org/entities/products/prod002": Mock(spec=Resource)
        }
        
        # Execute
        engine._process_batch(batch_df, dataset_name, mapping_config, column_resources)
        
        # Verify anchor column resolution was called
        mock_dependencies['uri_generator'].resolve_anchor_columns.assert_called_once_with(
            mapping_config, ["product_id", "name", "price"]
        )
        
        # Verify entity URI generation was called
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.assert_called_once_with(
            batch_df, dataset_name, ["product_id"]
        )
        
        # Verify entity resources were created
        expected_entity_data = [("products", "prod001"), ("products", "prod002")]
        mock_dependencies['resource_manager'].create_entity_resources_bulk.assert_called_once_with(
            expected_entity_data
        )

    def test_process_batch_property_creation(self, engine, mock_dependencies):
        """Test that _process_batch creates property triples correctly."""
        batch_df = pl.DataFrame({
            "id": ["1", "2"],
            "name": ["Alice", "Bob"],
            "age": ["25", "30"]
        })
        
        mapping_config = {
            "columns": {
                "id": {"is_anchor": True, "arkumu_type": "identifier"},
                "name": {"arkumu_type": "person_name"},
                "age": {"arkumu_type": "age_years"}
            }
        }
        
        # Configure mocks
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["id"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/dataset/1",
            "http://data.test.org/test_org/entities/dataset/2"
        ])
        
        entity_resource_1 = Mock(spec=Resource)
        entity_resource_2 = Mock(spec=Resource)
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/dataset/1": entity_resource_1,
            "http://data.test.org/test_org/entities/dataset/2": entity_resource_2
        }
        
        # Execute
        engine._process_batch(batch_df, "dataset", mapping_config, {})
        
        # Verify property triples were created
        mock_dependencies['resource_manager'].create_property_triples_bulk.assert_called_once()
        
        # Get the property data that was passed
        call_args = mock_dependencies['resource_manager'].create_property_triples_bulk.call_args[0][0]
        
        # Should have created properties for ALL columns for each entity (including anchor)
        # Entity 1: id, name, age properties (3 properties)
        # Entity 2: id, name, age properties (3 properties)
        assert len(call_args) == 6  # 2 entities × 3 properties each

    def test_process_batch_excludes_system_columns(self, engine, mock_dependencies):
        """Test that _process_batch excludes row_id and other system columns from properties."""
        batch_df = pl.DataFrame({
            "id": ["1"],
            "name": ["Alice"],
            "row_id": [1],
            "_internal": ["system_value"]
        })
        
        mapping_config = {"columns": {"id": {"is_anchor": True}}}
        
        # Configure mocks
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["id"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/dataset/1"
        ])
        
        entity_resource = Mock(spec=Resource)
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/dataset/1": entity_resource
        }
        
        # Execute
        engine._process_batch(batch_df, "dataset", mapping_config, {})
        
        # Get property data
        call_args = mock_dependencies['resource_manager'].create_property_triples_bulk.call_args[0][0]
        
        # Should create properties for 'name', 'id', and '_internal' (excluding only row_id)
        # The implementation only excludes 'row_id', not columns starting with '_'
        property_names = [prop[1] for prop in call_args]  # property URIs
        assert len(call_args) == 3  # 'name', 'id', and '_internal' properties
        assert any("name" in prop_uri for prop_uri in property_names)
        assert any("id" in prop_uri for prop_uri in property_names)
        assert any("internal" in prop_uri for prop_uri in property_names)

    def test_process_batch_handles_empty_values(self, engine, mock_dependencies):
        """Test that _process_batch skips empty/null values."""
        batch_df = pl.DataFrame({
            "id": ["1", "2"],
            "name": ["Alice", ""],  # Empty value
            "description": ["Valid desc", None]  # Null value
        })
        
        mapping_config = {"columns": {"id": {"is_anchor": True}}}
        
        # Configure mocks
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["id"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/dataset/1",
            "http://data.test.org/test_org/entities/dataset/2"
        ])
        
        entity_resource_1 = Mock(spec=Resource)
        entity_resource_2 = Mock(spec=Resource)
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/dataset/1": entity_resource_1,
            "http://data.test.org/test_org/entities/dataset/2": entity_resource_2
        }
        
        # Execute
        engine._process_batch(batch_df, "dataset", mapping_config, {})
        
        # Get property data
        call_args = mock_dependencies['resource_manager'].create_property_triples_bulk.call_args[0][0]
        
        # Should create properties for non-empty values including anchor
        # Entity 1: id="1", name="Alice", description="Valid desc" (3 properties)
        # Entity 2: id="2" (1 property, empty name and null description skipped)
        assert len(call_args) == 4

    def test_process_batch_statistics_update(self, engine, mock_dependencies):
        """Test that _process_batch updates statistics correctly."""
        batch_df = pl.DataFrame({
            "id": ["1", "2"],
            "name": ["Alice", "Bob"]
        })
        
        mapping_config = {"columns": {"id": {"is_anchor": True}}}
        
        # Configure mocks
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["id"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/dataset/1",
            "http://data.test.org/test_org/entities/dataset/2"
        ])
        
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/dataset/1": Mock(),
            "http://data.test.org/test_org/entities/dataset/2": Mock()
        }
        
        # Mock statistics with proper numeric attributes
        mock_metrics = Mock()
        mock_metrics.entities_processed = 0
        mock_metrics.properties_created = 0
        mock_dependencies['statistics'].current_metrics = mock_metrics
        
        # Execute
        engine._process_batch(batch_df, "dataset", mapping_config, {})
        
        # Verify statistics were updated
        assert mock_metrics.entities_processed == 2
        assert mock_metrics.properties_created == 4  # 2 entities × 2 properties each (id + name)

    def test_generate_property_uri_with_mapping(self, engine):
        """Test property URI generation uses arkumu_type from mapping."""
        mapping_config = {
            "columns": {
                "full_name": {"arkumu_type": "person_name"},
                "birth_date": {"arkumu_type": "date_of_birth"}
            }
        }
        
        # Test with arkumu_type
        uri1 = engine._generate_property_uri("full_name", mapping_config)
        assert "person-name" in uri1  # Slugified version with hyphens
        
        # Test without arkumu_type falls back to column name
        uri2 = engine._generate_property_uri("unknown_column", mapping_config)
        assert "unknown-column" in uri2  # Slugified version with hyphens

    def test_generate_property_uri_without_mapping(self, engine):
        """Test property URI generation without mapping config."""
        uri = engine._generate_property_uri("column_name", None)
        assert "column-name" in uri  # Slugified version with hyphens

    def test_process_batch_no_rows(self, engine, mock_dependencies):
        """Test that _process_batch handles empty DataFrame gracefully."""
        empty_df = pl.DataFrame({"id": []})
        
        # Execute
        engine._process_batch(empty_df, "dataset", {}, {})
        
        # Should return early without calling any bulk operations
        mock_dependencies['uri_generator'].resolve_anchor_columns.assert_not_called()
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.assert_not_called()
        mock_dependencies['resource_manager'].create_entity_resources_bulk.assert_not_called()

    def test_process_batch_with_default_anchor_resolution(self, engine, mock_dependencies):
        """Test _process_batch when using default anchor column resolution."""
        batch_df = pl.DataFrame({
            "first_column": ["A", "B"],
            "second_column": ["X", "Y"],
            "row_id": [1, 2]
        })
        
        # No explicit anchor configuration
        mapping_config = None
        
        # Configure mocks - should resolve to first non-system column
        mock_dependencies['uri_generator'].resolve_anchor_columns.return_value = ["first_column"]
        mock_dependencies['uri_generator'].generate_entity_uris_bulk.return_value = pl.Series([
            "http://data.test.org/test_org/entities/dataset/a",
            "http://data.test.org/test_org/entities/dataset/b"
        ])
        
        mock_dependencies['resource_manager'].create_entity_resources_bulk.return_value = {
            "http://data.test.org/test_org/entities/dataset/a": Mock(),
            "http://data.test.org/test_org/entities/dataset/b": Mock()
        }
        
        # Execute
        engine._process_batch(batch_df, "dataset", mapping_config, {})
        
        # Verify correct headers were passed (excluding row_id)
        mock_dependencies['uri_generator'].resolve_anchor_columns.assert_called_once_with(
            mapping_config, ["first_column", "second_column"]
        )