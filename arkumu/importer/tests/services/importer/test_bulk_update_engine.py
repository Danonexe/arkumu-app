import pytest
import polars as pl
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from arkumu.importer.services.importer.bulk_update_engine import (
    BulkUpdateEngine,
    BulkUpdateStats,
    ResourceUpdate,
    UpdateStrategy
)
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
from arkumu.importer.services.importer.bulk_data_analyzer import BulkDataAnalyzer
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType


@pytest.mark.django_db
class TestBulkUpdateEngine:
    
    def setup_method(self):
        self.uri_service = BulkURIService("http://example.com/data", "test_institution")
        self.data_analyzer = BulkDataAnalyzer()
        self.engine = BulkUpdateEngine(
            default_strategy=UpdateStrategy.SKIP_EXISTING,
            uri_service=self.uri_service,
            data_analyzer=self.data_analyzer
        )
    
    def test_init(self):
        assert self.engine.default_strategy == UpdateStrategy.SKIP_EXISTING
        assert self.engine.uri_service == self.uri_service
        assert self.engine.data_analyzer == self.data_analyzer
        assert self.engine.rdf_value_prop is None
    
    def test_update_strategy_enum(self):
        assert UpdateStrategy.SKIP_EXISTING.value == "skip_existing"
        assert UpdateStrategy.UPDATE_VALUES.value == "update_values"
        assert UpdateStrategy.MERGE_TRIPLES.value == "merge_triples"
        assert UpdateStrategy.REPLACE_ALL.value == "replace_all"
        assert UpdateStrategy.TIMESTAMP_BASED.value == "timestamp_based"
    
    def test_bulk_update_stats(self):
        stats = BulkUpdateStats()
        assert stats.rows_processed == 0
        assert stats.cells_processed == 0
        assert stats.resources_created == 0
        assert stats.resources_updated == 0
        assert stats.resources_skipped == 0
        assert stats.triples_created == 0
        assert stats.triples_updated == 0
        assert stats.triples_skipped == 0
        assert stats.row_links_created == 0
        assert stats.errors == 0
        assert stats.truncated_values == 0
        assert stats.multi_value_cells_detected == 0
        assert stats.total_values_created == 0
        assert stats.relationships_created == 0
    
    def test_bulk_update_stats_merge(self):
        stats1 = BulkUpdateStats(rows_processed=5, cells_processed=10, resources_created=3)
        stats2 = BulkUpdateStats(rows_processed=3, cells_processed=7, resources_updated=2)
        
        stats1.merge(stats2)
        
        assert stats1.rows_processed == 8
        assert stats1.cells_processed == 17
        assert stats1.resources_created == 3
        assert stats1.resources_updated == 2
    
    def test_resource_update(self):
        update = ResourceUpdate(
            uri="http://example.com/test",
            new_values=["value1", "value2"],
            new_name="test_name",
            new_datatype="string",
            action=UpdateStrategy.UPDATE_VALUES,
            is_multi_value=True
        )
        
        assert update.uri == "http://example.com/test"
        assert update.new_values == ["value1", "value2"]
        assert update.new_name == "test_name"
        assert update.new_datatype == "string"
        assert update.action == UpdateStrategy.UPDATE_VALUES
        assert update.is_multi_value is True
        assert update.existing_resource is None
    
    def test_set_rdf_properties(self):
        # Create a mock RDF value property
        rdf_value_prop = Resource.objects.create(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY,
            name="value",
            source="test_institution"
        )
        
        self.engine.set_rdf_properties(rdf_value_prop)
        
        assert self.engine.rdf_value_prop == rdf_value_prop
    
    def test_prepare_update_data_vectorized_empty(self):
        empty_df = pl.DataFrame()
        
        updates, stats = self.engine.prepare_update_data_vectorized(empty_df, "test_dataset")
        
        assert updates == []
        assert isinstance(stats, BulkUpdateStats)
        assert stats.rows_processed == 0
    
    def test_prepare_update_data_vectorized_simple(self):
        df = pl.DataFrame({
            "col1": ["value1", "value2"],
            "col2": ["value3", "value4"]
        })
        
        updates, stats = self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        assert len(updates) == 4  # 2 rows × 2 columns
        assert stats.rows_processed == 2
        assert all(isinstance(update, ResourceUpdate) for update in updates)
        assert all(update.action == UpdateStrategy.SKIP_EXISTING for update in updates)
    
    def test_prepare_update_data_vectorized_multi_value(self):
        df = pl.DataFrame({
            "multi_col": ["a,b,c", "d,e"],
            "single_col": ["value1", "value2"]
        })
        
        column_configs = {
            "multi_col": {"is_multi_value": True, "multi_value_separator": ","}
        }
        
        updates, stats = self.engine.prepare_update_data_vectorized(
            df, "test_dataset", column_configs
        )
        
        # Should have more updates due to multi-value splitting
        assert len(updates) > 4
        
        # Check that multi-value updates are marked correctly
        multi_value_updates = [u for u in updates if u.is_multi_value]
        assert len(multi_value_updates) > 0
    
    def test_prepare_update_data_vectorized_unicode_normalization(self):
        df = pl.DataFrame({
            "text_col": ["café", "naïve", "résumé"]
        })
        
        updates, stats = self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        assert len(updates) == 3
        assert stats.rows_processed == 3
        
        # Check that Unicode values are properly handled
        values = [update.new_values[0] for update in updates]
        assert "café" in values
        assert "naïve" in values
        assert "résumé" in values
    
    def test_prepare_update_data_vectorized_large_values(self):
        # Test value truncation for large values
        large_value = "x" * 1500  # Larger than MAX_INDEXED_VALUE_SIZE
        df = pl.DataFrame({
            "large_col": [large_value, "normal_value"]
        })
        
        updates, stats = self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        assert len(updates) == 2
        assert stats.truncated_values >= 1
        
        # Check that large value was truncated
        large_update = next(u for u in updates if u.new_values[0].endswith("..."))
        assert len(large_update.new_values[0]) < len(large_value)
    
    def test_get_existing_resources_bulk(self):
        # Create test resources
        resource1 = Resource.objects.create(
            uri="http://example.com/test1",
            resource_type=ResourceType.IRI,
            name="Test 1",
            source="test_institution"
        )
        
        resource2 = Resource.objects.create(
            uri="http://example.com/test2",
            resource_type=ResourceType.IRI,
            name="Test 2",
            source="test_institution"
        )
        
        uris = ["http://example.com/test1", "http://example.com/test2", "http://example.com/nonexistent"]
        
        result = self.engine.get_existing_resources_bulk(uris)
        
        assert len(result) == 2
        assert "http://example.com/test1" in result
        assert "http://example.com/test2" in result
        assert "http://example.com/nonexistent" not in result
        assert result["http://example.com/test1"] == resource1
        assert result["http://example.com/test2"] == resource2
    
    def test_determine_update_actions_skip_existing(self):
        # Set up the engine with the same URI service used in setup
        self.engine.uri_service = self.uri_service
        self.engine.data_analyzer = self.data_analyzer
        
        # Create existing resource with the expected URI pattern
        expected_uri = self.uri_service.generate_cell_uri("test_dataset", "col1", "0")
        existing_resource = Resource.objects.create(
            uri=expected_uri,
            resource_type=ResourceType.IRI,
            name="Test",
            source="test-institution"
        )
        
        df = pl.DataFrame({
            "col1": ["value1", "value2"]
        })
        
        self.engine.default_strategy = UpdateStrategy.SKIP_EXISTING
        
        updates, stats = self.engine.determine_update_actions(df, "test_dataset")
        
        # Find the update for the existing resource
        existing_update = next(
            (u for u in updates if u.uri == existing_resource.uri), None
        )
        
        assert existing_update is not None
        assert existing_update.action == UpdateStrategy.SKIP_EXISTING
        assert existing_update.existing_resource == existing_resource
        assert stats.resources_skipped >= 1
    
    def test_determine_update_actions_update_values(self):
        # Set up the engine with the same URI service used in setup
        self.engine.uri_service = self.uri_service
        self.engine.data_analyzer = self.data_analyzer
        
        # Create existing resource with a value using expected URI
        expected_uri = self.uri_service.generate_cell_uri("test_dataset", "col1", "0")
        existing_cell = Resource.objects.create(
            uri=expected_uri,
            resource_type=ResourceType.IRI,
            name="Test",
            source="test-institution"
        )
        
        existing_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="old_value",
            source="test-institution",
            name="Test"
        )
        
        rdf_value_prop = Resource.objects.create(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY,
            name="value",
            source="test-institution"
        )
        
        Triple.objects.create(
            subject=existing_cell,
            predicate=rdf_value_prop,
            object=existing_literal
        )
        
        self.engine.set_rdf_properties(rdf_value_prop)
        self.engine.default_strategy = UpdateStrategy.UPDATE_VALUES
        
        df = pl.DataFrame({
            "col1": ["new_value", "value2"]
        })
        
        updates, stats = self.engine.determine_update_actions(df, "test_dataset")
        
        # Find the update for the existing resource
        existing_update = next(
            (u for u in updates if u.uri == existing_cell.uri), None
        )
        
        assert existing_update is not None
        assert existing_update.action == UpdateStrategy.UPDATE_VALUES
        assert stats.resources_updated >= 1
    
    def test_filter_updates_by_strategy(self):
        updates = [
            ResourceUpdate(uri="uri1", action=UpdateStrategy.SKIP_EXISTING),
            ResourceUpdate(uri="uri2", action=UpdateStrategy.UPDATE_VALUES),
            ResourceUpdate(uri="uri3", action=UpdateStrategy.SKIP_EXISTING),
            ResourceUpdate(uri="uri4", action=UpdateStrategy.MERGE_TRIPLES)
        ]
        
        filtered = self.engine.filter_updates_by_strategy(
            updates, [UpdateStrategy.UPDATE_VALUES, UpdateStrategy.MERGE_TRIPLES]
        )
        
        assert len(filtered) == 2
        assert filtered[0].uri == "uri2"
        assert filtered[1].uri == "uri4"
    
    def test_group_updates_by_dataset(self):
        updates = [
            ResourceUpdate(uri="http://example.com/data/test_institution/datasets/dataset1/col1/1"),
            ResourceUpdate(uri="http://example.com/data/test_institution/datasets/dataset1/col2/1"),
            ResourceUpdate(uri="http://example.com/data/test_institution/datasets/dataset2/col1/1"),
            ResourceUpdate(uri="http://example.com/data/test_institution/datasets/dataset2/col2/1")
        ]
        
        grouped = self.engine.group_updates_by_dataset(updates)
        
        assert len(grouped) == 2
        assert "dataset1" in grouped
        assert "dataset2" in grouped
        assert len(grouped["dataset1"]) == 2
        assert len(grouped["dataset2"]) == 2
    
    def test_validate_updates(self):
        # Set up the engine with the URI service
        self.engine.uri_service = self.uri_service
        
        # Use valid URIs that match the institution pattern
        valid_uri1 = self.uri_service.generate_cell_uri("dataset", "column", "1")
        valid_uri2 = self.uri_service.generate_cell_uri("dataset", "column", "2")
        
        updates = [
            ResourceUpdate(uri=valid_uri1, new_values=["value1"]),
            ResourceUpdate(uri="", new_values=["value2"]),  # Invalid URI
            ResourceUpdate(uri=valid_uri2, new_values=[]),  # No values
            ResourceUpdate(uri=valid_uri1, new_values=["value3", ""]),  # Mixed values
        ]
        
        valid_updates, errors = self.engine.validate_updates(updates)
        
        assert len(valid_updates) == 2
        assert len(errors) >= 2
        
        # Check that valid updates have proper values
        assert valid_updates[0].uri == valid_uri1
        assert valid_updates[0].new_values == ["value1"]
        assert valid_updates[1].uri == valid_uri1
        assert valid_updates[1].new_values == ["value3"]  # Empty values should be filtered out
    
    def test_validate_updates_with_uri_service(self):
        # Set up the engine with the URI service
        self.engine.uri_service = self.uri_service
        
        # Test validation with URI service
        valid_uri = self.uri_service.generate_cell_uri("test_dataset", "col1", "0")
        updates = [
            ResourceUpdate(
                uri=valid_uri,
                new_values=["value1"]
            ),
            ResourceUpdate(
                uri="invalid_uri_format",
                new_values=["value2"]
            )
        ]
        
        valid_updates, errors = self.engine.validate_updates(updates)
        
        # Should have at least one valid update and one error
        assert len(valid_updates) >= 1
        assert len(errors) >= 1
    
    def test_prepare_update_data_null_handling(self):
        df = pl.DataFrame({
            "col1": ["value1", None, "value3"],
            "col2": [None, "value2", ""]
        })
        
        updates, stats = self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        # Should only create updates for non-null, non-empty values
        assert len(updates) == 3  # value1, value2, value3
        assert stats.rows_processed == 3
        
        # Check that no updates have empty or None values
        for update in updates:
            assert all(val and val.strip() for val in update.new_values)
    
    def test_prepare_update_data_with_row_index(self):
        df = pl.DataFrame({
            "col1": ["value1", "value2", "value3"]
        })
        
        updates, stats = self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        # Check that URIs contain correct row indices (1-based in URI)
        uris = [update.uri for update in updates]
        assert any("/1" in uri for uri in uris)  # Row 1
        assert any("/2" in uri for uri in uris)  # Row 2
        assert any("/3" in uri for uri in uris)  # Row 3
    
    def test_multi_value_uri_generation(self):
        df = pl.DataFrame({
            "multi_col": ["a,b,c"]
        })
        
        column_configs = {
            "multi_col": {"is_multi_value": True, "multi_value_separator": ","}
        }
        
        updates, stats = self.engine.prepare_update_data_vectorized(
            df, "test_dataset", column_configs
        )
        
        # Should have 3 updates for the multi-value cell
        assert len(updates) == 3
        
        # Each update should have a unique URI with value index
        uris = [update.uri for update in updates]
        assert len(set(uris)) == 3  # All URIs should be unique
        
        # Check that value indices are included in URIs
        assert any("v0" in uri for uri in uris)
        assert any("v1" in uri for uri in uris)
        assert any("v2" in uri for uri in uris)
    
    @patch('arkumu.importer.services.importer.bulk_update_engine.logger')
    def test_logging(self, mock_logger):
        df = pl.DataFrame({
            "col1": ["value1", "value2"]
        })
        
        self.engine.prepare_update_data_vectorized(df, "test_dataset")
        
        # Check that info logs were called
        mock_logger.info.assert_called()
    
    def test_engine_with_different_strategies(self):
        # Test engine initialization with different strategies
        for strategy in UpdateStrategy:
            engine = BulkUpdateEngine(default_strategy=strategy)
            assert engine.default_strategy == strategy
    
    def test_complex_dataset_processing(self):
        # Test with a more complex dataset
        df = pl.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "name": ["Item 1", "Item 2", "Item 3", "Item 4", "Item 5"],
            "tags": ["tag1,tag2", "tag3", "tag1,tag3,tag4", "", "tag2"],
            "description": ["Desc 1", None, "Desc 3", "Desc 4", ""],
            "value": [10.5, 20.0, 15.75, 0.0, None]
        })
        
        column_configs = {
            "tags": {"is_multi_value": True, "multi_value_separator": ","}
        }
        
        updates, stats = self.engine.prepare_update_data_vectorized(
            df, "complex_dataset", column_configs
        )
        
        assert len(updates) > 5  # More than just the rows due to multi-value
        assert stats.rows_processed == 5
        
        # Check that multi-value column creates multiple updates
        tag_updates = [u for u in updates if "tags" in u.uri]
        assert len(tag_updates) > 3  # tag1,tag2 + tag3 + tag1,tag3,tag4 + tag2