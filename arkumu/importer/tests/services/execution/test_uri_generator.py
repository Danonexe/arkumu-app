"""
Tests for UnifiedURIGenerator focusing on latest entity-based implementation changes.
"""

import pytest
import polars as pl
from arkumu.importer.services.execution.uri_generator import UnifiedURIGenerator


class TestUnifiedURIGenerator:
    """Test suite for entity-based URI generation and anchor column resolution."""

    @pytest.fixture
    def uri_generator(self):
        """Create a URI generator instance for testing."""
        return UnifiedURIGenerator(
            base_uri="http://data.test.org", 
            institution="test-org"
        )

    def test_anchor_column_resolution_explicit_anchors(self, uri_generator):
        """Test that explicitly marked anchor columns are used correctly."""
        dataset_config = {
            "columns": {
                "product_id": {"is_anchor": True, "arkumu_type": "identifier"},
                "name": {"is_anchor": False, "arkumu_type": "name"},
                "value": {"is_anchor": False, "arkumu_type": "value"}
            }
        }
        csv_headers = ["product_id", "name", "value", "row_id"]
        
        anchors = uri_generator.resolve_anchor_columns(dataset_config, csv_headers)
        
        assert anchors == ["product_id"]

    def test_anchor_column_resolution_multiple_anchors(self, uri_generator):
        """Test multiple explicit anchor columns."""
        dataset_config = {
            "columns": {
                "first_id": {"is_anchor": True},
                "second_id": {"is_anchor": True},
                "data": {"is_anchor": False}
            }
        }
        csv_headers = ["first_id", "second_id", "data"]
        
        anchors = uri_generator.resolve_anchor_columns(dataset_config, csv_headers)
        
        assert set(anchors) == {"first_id", "second_id"}

    def test_anchor_column_resolution_anchor_columns_list(self, uri_generator):
        """Test anchor_columns list from mapping config (per plan specs)."""
        dataset_config = {
            "anchor_columns": ["key_field", "secondary_key"],
            "columns": {
                "key_field": {"arkumu_type": "key"},
                "secondary_key": {"arkumu_type": "secondary"},
                "data": {"arkumu_type": "data"}
            }
        }
        csv_headers = ["key_field", "secondary_key", "data"]
        
        anchors = uri_generator.resolve_anchor_columns(dataset_config, csv_headers)
        
        assert anchors == ["key_field", "secondary_key"]

    def test_anchor_column_resolution_default_first_column(self, uri_generator):
        """Test default behavior: use first column when no explicit anchors."""
        dataset_config = {
            "columns": {
                "name": {"arkumu_type": "name"},
                "value": {"arkumu_type": "value"}
            }
        }
        csv_headers = ["name", "value", "description"]
        
        anchors = uri_generator.resolve_anchor_columns(dataset_config, csv_headers)
        
        assert anchors == ["name"]

    def test_anchor_column_resolution_excludes_system_columns(self, uri_generator):
        """Test that system columns are excluded from anchor consideration."""
        csv_headers = ["row_id", "_id", "id", "name", "value"]
        
        anchors = uri_generator.resolve_anchor_columns(None, csv_headers)
        
        # Should exclude row_id, _id, id and use first non-system column
        assert anchors == ["name"]

    def test_anchor_column_resolution_no_eligible_columns(self, uri_generator):
        """Test fallback when only system columns are available."""
        csv_headers = ["row_id", "_id", "index"]
        
        anchors = uri_generator.resolve_anchor_columns(None, csv_headers)
        
        assert anchors == []

    def test_generate_entity_uri_single_anchor(self, uri_generator):
        """Test entity URI generation with single anchor column."""
        row_data = {"product_id": "PROD123", "name": "Test Product", "price": "99.99"}
        anchor_columns = ["product_id"]
        
        uri = uri_generator.generate_entity_uri("products", row_data, anchor_columns)
        
        assert uri == "http://data.test.org/test-org/entities/products/prod123"

    def test_generate_entity_uri_multiple_anchors(self, uri_generator):
        """Test entity URI generation with multiple anchor columns (composite hash)."""
        row_data = {"region": "US", "store_id": "ST001", "name": "Store Name"}
        anchor_columns = ["region", "store_id"]
        
        uri = uri_generator.generate_entity_uri("stores", row_data, anchor_columns)
        
        # Should generate composite hash-based URI
        assert uri.startswith("http://data.test.org/test-org/entities/stores/composite-")
        assert len(uri.split("/")[-1]) == len("composite-") + 8  # composite- + 8-char hash

    def test_generate_entity_uri_empty_anchors_fallback(self, uri_generator):
        """Test fallback to row_id when anchor columns are empty."""
        row_data = {"row_id": 42, "data": "some value"}
        anchor_columns = []
        
        uri = uri_generator.generate_entity_uri("dataset", row_data, anchor_columns)
        
        assert uri == "http://data.test.org/test-org/entities/dataset/row-42"

    def test_generate_entity_uri_no_row_id_fallback(self, uri_generator):
        """Test hash-based fallback when no row_id and empty anchors."""
        row_data = {"name": "test", "value": "123"}
        anchor_columns = []
        
        uri = uri_generator.generate_entity_uri("dataset", row_data, anchor_columns)
        
        # Should generate entity-<hash> format
        assert uri.startswith("http://data.test.org/test-org/entities/dataset/entity-")
        assert len(uri.split("/")[-1]) == len("entity-") + 8  # entity- + 8-char hash

    def test_generate_entity_uris_bulk_single_anchor(self, uri_generator):
        """Test bulk URI generation with single anchor column."""
        df = pl.DataFrame({
            "product_id": ["PROD001", "PROD002", "PROD003"],
            "name": ["Product A", "Product B", "Product C"],
            "price": [10.0, 20.0, 30.0]
        })
        anchor_columns = ["product_id"]
        
        uris = uri_generator.generate_entity_uris_bulk(df, "products", anchor_columns)
        
        expected_uris = [
            "http://data.test.org/test-org/entities/products/prod001",
            "http://data.test.org/test-org/entities/products/prod002", 
            "http://data.test.org/test-org/entities/products/prod003"
        ]
        assert uris.to_list() == expected_uris

    def test_generate_entity_uris_bulk_multiple_anchors(self, uri_generator):
        """Test bulk URI generation with multiple anchor columns."""
        df = pl.DataFrame({
            "region": ["US", "EU", "ASIA"],
            "store_id": ["ST001", "ST002", "ST003"],
            "name": ["Store A", "Store B", "Store C"]
        })
        anchor_columns = ["region", "store_id"]
        
        uris = uri_generator.generate_entity_uris_bulk(df, "stores", anchor_columns)
        
        # All URIs should have composite hash format
        for uri in uris.to_list():
            assert uri.startswith("http://data.test.org/test-org/entities/stores/composite-")
            assert len(uri.split("/")[-1]) == len("composite-") + 8

    def test_generate_entity_uris_bulk_no_anchors_with_row_id(self, uri_generator):
        """Test bulk URI generation fallback to row_id when no anchor columns."""
        df = pl.DataFrame({
            "row_id": [1, 2, 3],
            "data": ["A", "B", "C"]
        })
        anchor_columns = []
        
        uris = uri_generator.generate_entity_uris_bulk(df, "dataset", anchor_columns)
        
        expected_uris = [
            "http://data.test.org/test-org/entities/dataset/row-1",
            "http://data.test.org/test-org/entities/dataset/row-2",
            "http://data.test.org/test-org/entities/dataset/row-3"
        ]
        assert uris.to_list() == expected_uris

    def test_generate_entity_uris_bulk_no_anchors_no_row_id(self, uri_generator):
        """Test bulk URI generation fallback to row numbers when no anchors or row_id."""
        df = pl.DataFrame({
            "name": ["Alice", "Bob", "Charlie"],
            "age": [25, 30, 35]
        })
        anchor_columns = []
        
        uris = uri_generator.generate_entity_uris_bulk(df, "people", anchor_columns)
        
        expected_uris = [
            "http://data.test.org/test-org/entities/people/row-0",
            "http://data.test.org/test-org/entities/people/row-1",
            "http://data.test.org/test-org/entities/people/row-2"
        ]
        assert uris.to_list() == expected_uris

    def test_generate_entity_uris_bulk_handles_null_values(self, uri_generator):
        """Test bulk URI generation handles null/empty anchor values."""
        df = pl.DataFrame({
            "id": ["ID001", None, "ID003"],
            "name": ["Item A", "Item B", "Item C"]
        })
        anchor_columns = ["id"]
        
        uris = uri_generator.generate_entity_uris_bulk(df, "items", anchor_columns)
        
        # Should handle null value by falling back to row number
        expected = [
            "http://data.test.org/test-org/entities/items/id001",
            "http://data.test.org/test-org/entities/items/row-1",  # fallback for null
            "http://data.test.org/test-org/entities/items/id003"
        ]
        assert uris.to_list() == expected

    def test_generate_entity_uris_bulk_missing_anchor_column(self, uri_generator):
        """Test bulk URI generation when anchor column doesn't exist in DataFrame."""
        df = pl.DataFrame({
            "name": ["Alice", "Bob"],
            "age": [25, 30]
        })
        anchor_columns = ["missing_column"]
        
        uris = uri_generator.generate_entity_uris_bulk(df, "people", anchor_columns)
        
        # Should fallback to row numbers
        expected = [
            "http://data.test.org/test-org/entities/people/row-0",
            "http://data.test.org/test-org/entities/people/row-1"
        ]
        assert uris.to_list() == expected

    def test_uri_generation_stability(self, uri_generator):
        """Test that URI generation is stable/deterministic."""
        row_data = {"id": "TEST123", "name": "Test Item"}
        anchor_columns = ["id"]
        
        uri1 = uri_generator.generate_entity_uri("products", row_data, anchor_columns)
        uri2 = uri_generator.generate_entity_uri("products", row_data, anchor_columns)
        
        assert uri1 == uri2

    def test_uri_generation_with_special_characters(self, uri_generator):
        """Test URI generation handles special characters in anchor values."""
        row_data = {"product_id": "PROD/123 & Co.", "name": "Special Product"}
        anchor_columns = ["product_id"]
        
        uri = uri_generator.generate_entity_uri("products", row_data, anchor_columns)
        
        # Should be properly slugified (& becomes "and")
        assert uri == "http://data.test.org/test-org/entities/products/prod-123-and-co"

    def test_institution_slugification(self):
        """Test that institution names are properly slugified."""
        generator = UnifiedURIGenerator("http://test.org", "Test Institution & Co.")
        
        row_data = {"product_id": "123"}
        anchor_columns = ["product_id"]
        
        uri = generator.generate_entity_uri("dataset", row_data, anchor_columns)
        
        assert "test-institution-and-co" in uri