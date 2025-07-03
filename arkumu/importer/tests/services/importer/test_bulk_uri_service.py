import pytest
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService


class TestBulkURIService:
    
    def setup_method(self):
        self.uri_service = BulkURIService("http://example.com/data", "test_institution")
    
    def test_init(self):
        assert self.uri_service.base_uri == "http://example.com/data"
        assert self.uri_service.institution == "test-institution"  # Gets slugified
        
        # Test with None institution
        service = BulkURIService("http://example.com/data", None)
        assert service.institution == "default"
        
        # Test with institution that needs slugification
        service = BulkURIService("http://example.com/data", "Test Institution 123!")
        assert service.institution == "test-institution-123"
    
    def test_generate_dataset_uri(self):
        uri = self.uri_service.generate_dataset_uri("my_dataset")
        assert uri == "http://example.com/data/test-institution/datasets/my-dataset"
        
        # Test with special characters
        uri = self.uri_service.generate_dataset_uri("My Dataset! 123")
        assert "my-dataset-123" in uri
    
    def test_generate_column_uri(self):
        uri = self.uri_service.generate_column_uri("my_dataset", "my_column")
        expected = "http://example.com/data/test-institution/datasets/my-dataset/columns/my-column"
        assert uri == expected
        
        # Test with special characters
        uri = self.uri_service.generate_column_uri("dataset", "My Column!")
        assert "my-column" in uri
    
    def test_generate_row_uri(self):
        uri = self.uri_service.generate_row_uri("my_dataset", "123")
        expected = "http://example.com/data/test-institution/datasets/my-dataset/rows/123"
        assert uri == expected
        
        # Test with special characters
        uri = self.uri_service.generate_row_uri("dataset", "Row ID!")
        assert "row-id" in uri
    
    def test_generate_cell_uri(self):
        # Test basic cell URI
        uri = self.uri_service.generate_cell_uri("my_dataset", "my_column", "0")
        expected = "http://example.com/data/test-institution/datasets/my-dataset/my-column/1"
        assert uri == expected
        
        # Test numeric row_id conversion (0-based to 1-based)
        uri = self.uri_service.generate_cell_uri("dataset", "column", "5")
        assert uri.endswith("/6")  # 5 + 1 = 6
        
        # Test non-numeric row_id
        uri = self.uri_service.generate_cell_uri("dataset", "column", "abc")
        assert uri.endswith("/abc")
        
        # Test with value index for multi-value
        uri = self.uri_service.generate_cell_uri("dataset", "column", "0", 2)
        assert uri.endswith("/1/v2")
        
        # Test with special characters
        uri = self.uri_service.generate_cell_uri("dataset", "My Column!", "0")
        assert "my-column" in uri
    
    def test_generate_entity_uri(self):
        uri = self.uri_service.generate_entity_uri("my_dataset", "entity_value")
        expected = "http://example.com/data/test-institution/entities/my-dataset/entity-value"
        assert uri == expected
        
        # Test with special characters
        uri = self.uri_service.generate_entity_uri("dataset", "Entity Value!")
        assert "entity-value" in uri
    
    def test_generate_property_uri(self):
        uri = self.uri_service.generate_property_uri("my_property")
        expected = "http://example.com/data/test-institution/properties/my-property"
        assert uri == expected
        
        # Test with special characters
        uri = self.uri_service.generate_property_uri("My Property!")
        assert "my-property" in uri
    
    def test_generate_junction_uri(self):
        uri = self.uri_service.generate_junction_uri("dataset", "context", "junction_id")
        expected = "http://example.com/data/test-institution/junctions/dataset/context/junction-id"
        assert uri == expected
        
        # Test with special characters
        uri = self.uri_service.generate_junction_uri("dataset", "My Context!", "Junction ID!")
        assert "my-context" in uri
        assert "junction-id" in uri
    
    def test_extract_row_id_from_uri(self):
        # Test standard cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/my_column/123"
        row_id = self.uri_service.extract_row_id_from_uri(uri)
        assert row_id == "123"
        
        # Test with multi-value URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/my_column/123/v0"
        row_id = self.uri_service.extract_row_id_from_uri(uri)
        assert row_id == "v0"  # Returns the last segment
        
        # Test with invalid URI
        row_id = self.uri_service.extract_row_id_from_uri("invalid")
        assert row_id == "invalid"
    
    def test_extract_column_name_from_uri(self):
        # Test standard cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/my_column/123"
        column_name = self.uri_service.extract_column_name_from_uri(uri)
        assert column_name == "my_column"
        
        # Test with datasets not in URI
        column_name = self.uri_service.extract_column_name_from_uri("http://example.com/other/path")
        assert column_name is None
        
        # Test with too short URI
        column_name = self.uri_service.extract_column_name_from_uri("http://example.com/datasets/name")
        assert column_name is None
    
    def test_extract_dataset_name_from_uri(self):
        # Test with dataset URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset"
        dataset_name = self.uri_service.extract_dataset_name_from_uri(uri)
        assert dataset_name == "my_dataset"
        
        # Test with cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/column/row"
        dataset_name = self.uri_service.extract_dataset_name_from_uri(uri)
        assert dataset_name == "my_dataset"
        
        # Test with URI without datasets
        dataset_name = self.uri_service.extract_dataset_name_from_uri("http://example.com/other/path")
        assert dataset_name is None
    
    def test_is_cell_uri(self):
        # Test valid cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/column/row"
        assert self.uri_service.is_cell_uri(uri) is True
        
        # Test dataset URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset"
        assert self.uri_service.is_cell_uri(uri) is False
        
        # Test column URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/columns/column"
        assert self.uri_service.is_cell_uri(uri) is False
        
        # Test invalid URI
        assert self.uri_service.is_cell_uri("invalid") is False
    
    def test_is_row_uri(self):
        # Test valid row URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/rows/123"
        assert self.uri_service.is_row_uri(uri) is True
        
        # Test cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/column/row"
        assert self.uri_service.is_row_uri(uri) is False
        
        # Test dataset URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset"
        assert self.uri_service.is_row_uri(uri) is False
        
        # Test invalid URI
        assert self.uri_service.is_row_uri("invalid") is False
    
    def test_is_column_uri(self):
        # Test valid column URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/columns/column"
        assert self.uri_service.is_column_uri(uri) is True
        
        # Test cell URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset/column/row"
        assert self.uri_service.is_column_uri(uri) is False
        
        # Test dataset URI
        uri = "http://example.com/data/test_institution/datasets/my_dataset"
        assert self.uri_service.is_column_uri(uri) is False
        
        # Test invalid URI
        assert self.uri_service.is_column_uri("invalid") is False
    
    def test_validate_uri_pattern(self):
        # Test valid cell URI
        uri = "http://example.com/data/test-institution/datasets/my_dataset/column/row"
        result = self.uri_service.validate_uri_pattern(uri)
        assert result["is_valid"] is True
        assert result["uri_type"] == "cell"
        assert result["components"]["dataset_name"] == "my_dataset"
        assert result["components"]["column_name"] == "column"
        assert result["components"]["row_id"] == "row"
        
        # Test valid row URI
        uri = "http://example.com/data/test-institution/datasets/my_dataset/rows/123"
        result = self.uri_service.validate_uri_pattern(uri)
        assert result["is_valid"] is True
        assert result["uri_type"] == "row"
        
        # Test valid column URI
        uri = "http://example.com/data/test-institution/datasets/my_dataset/columns/column"
        result = self.uri_service.validate_uri_pattern(uri)
        assert result["is_valid"] is True
        assert result["uri_type"] == "column"
        
        # Test valid dataset URI
        uri = "http://example.com/data/test-institution/datasets/my_dataset"
        result = self.uri_service.validate_uri_pattern(uri)
        assert result["is_valid"] is True
        assert result["uri_type"] == "dataset"
        
        # Test invalid URI (no http)
        result = self.uri_service.validate_uri_pattern("invalid_uri")
        assert result["is_valid"] is False
        assert "URI must start with http:// or https://" in result["errors"]
        
        # Test invalid URI (too short)
        result = self.uri_service.validate_uri_pattern("http://a")
        assert result["is_valid"] is False
        assert "URI structure is too short" in result["errors"]
        
        # Test invalid URI (wrong institution)
        uri = "http://example.com/data/wrong_institution/datasets/my_dataset"
        result = self.uri_service.validate_uri_pattern(uri)
        assert result["is_valid"] is False
        assert "Institution" in result["errors"][0]
    
    def test_get_uri_hierarchy(self):
        # Test cell URI hierarchy
        uri = "http://example.com/data/test-institution/datasets/my_dataset/column/row"
        hierarchy = self.uri_service.get_uri_hierarchy(uri)
        
        assert len(hierarchy) == 3  # dataset, column, row
        assert self.uri_service.generate_dataset_uri("my_dataset") in hierarchy
        assert self.uri_service.generate_column_uri("my_dataset", "column") in hierarchy
        assert self.uri_service.generate_row_uri("my_dataset", "row") in hierarchy
        
        # Test column URI hierarchy
        uri = "http://example.com/data/test-institution/datasets/my_dataset/columns/column"
        hierarchy = self.uri_service.get_uri_hierarchy(uri)
        
        assert len(hierarchy) == 1  # Just dataset
        assert self.uri_service.generate_dataset_uri("my_dataset") in hierarchy
        
        # Test invalid URI
        hierarchy = self.uri_service.get_uri_hierarchy("invalid")
        assert hierarchy == []
    
    def test_edge_cases(self):
        # Test with empty strings
        uri = self.uri_service.generate_dataset_uri("")
        assert "datasets/" in uri
        
        # Test with None values
        uri = self.uri_service.generate_cell_uri("dataset", "column", None)
        assert "none" in uri.lower()
        
        # Test with very long names
        long_name = "a" * 1000
        uri = self.uri_service.generate_dataset_uri(long_name)
        assert len(uri) > 100  # Should still generate a URI
    
    def test_multi_value_uris(self):
        # Test that multi-value URIs are unique
        base_uri = self.uri_service.generate_cell_uri("dataset", "column", "1")
        multi_uri_0 = self.uri_service.generate_cell_uri("dataset", "column", "1", 0)
        multi_uri_1 = self.uri_service.generate_cell_uri("dataset", "column", "1", 1)
        
        assert base_uri != multi_uri_0
        assert base_uri != multi_uri_1
        assert multi_uri_0 != multi_uri_1
        assert multi_uri_0.endswith("/v0")
        assert multi_uri_1.endswith("/v1")
    
    def test_special_characters_handling(self):
        # Test various special characters
        special_chars = ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", " ", "ñ", "café"]
        
        for char in special_chars:
            dataset_name = f"test{char}dataset"
            uri = self.uri_service.generate_dataset_uri(dataset_name)
            # Should not contain the special character directly
            assert char not in uri or char in ["ñ", "café"]  # Unicode chars might be preserved
            # Should be a valid URI
            assert uri.startswith("http://")
    
    def test_consistency(self):
        # Test that the same inputs always produce the same outputs
        dataset_name = "test_dataset"
        column_name = "test_column"
        row_id = "123"
        
        uri1 = self.uri_service.generate_cell_uri(dataset_name, column_name, row_id)
        uri2 = self.uri_service.generate_cell_uri(dataset_name, column_name, row_id)
        
        assert uri1 == uri2
        
        # Test extraction consistency
        extracted_dataset = self.uri_service.extract_dataset_name_from_uri(uri1)
        extracted_column = self.uri_service.extract_column_name_from_uri(uri1)
        extracted_row = self.uri_service.extract_row_id_from_uri(uri1)
        
        assert extracted_dataset == "test-dataset"  # Dataset name gets slugified
        assert extracted_column == "test-column"  # Column name gets slugified
        assert extracted_row == "124"  # 123 + 1 for display format
    
    def test_numeric_row_id_conversion(self):
        # Test 0-based to 1-based conversion for numeric row IDs
        test_cases = [
            ("0", "1"),
            ("1", "2"),
            ("10", "11"),
            ("99", "100")
        ]
        
        for input_row_id, expected_display_id in test_cases:
            uri = self.uri_service.generate_cell_uri("dataset", "column", input_row_id)
            assert uri.endswith(f"/{expected_display_id}")
        
        # Test non-numeric row IDs (should not be converted, but may be slugified)
        non_numeric_cases = [
            ("abc", "abc"),
            ("row_1", "row-1"),  # Underscore becomes hyphen in slugification
            ("1abc", "1abc"),
            ("", "n-a")  # Empty string gets default value
        ]
        
        for row_id, expected_slugified in non_numeric_cases:
            uri = self.uri_service.generate_cell_uri("dataset", "column", row_id)
            if row_id:  # Skip empty string case
                assert expected_slugified in uri.lower()
            else:
                assert "n-a" in uri or expected_slugified in uri