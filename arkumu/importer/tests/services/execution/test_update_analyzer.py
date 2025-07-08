"""
Tests for UpdateAnalyzer.

Tests data change detection, conflict resolution, and update
strategy determination based on existing data and policies.
"""
import pytest
import polars as pl
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from arkumu.common.enums import UpdateStrategy
from arkumu.metadata.models import Resource
from arkumu.importer.services.execution.update_analyzer import UpdateAnalyzer


@pytest.mark.django_db
class TestUpdateAnalyzer:
    """Test suite for UpdateAnalyzer"""
    
    def test_initialization(self, resource_manager):
        """Test UpdateAnalyzer initialization"""
        analyzer = UpdateAnalyzer(
            resource_manager=resource_manager,
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            timestamp_column="updated_at"
        )
        
        assert analyzer.resource_manager is resource_manager
        assert analyzer.default_strategy == UpdateStrategy.UPDATE_VALUES
        assert analyzer.timestamp_column == "updated_at"
    
    def test_initialization_defaults(self, resource_manager):
        """Test UpdateAnalyzer initialization with defaults"""
        analyzer = UpdateAnalyzer(resource_manager=resource_manager)
        
        assert analyzer.default_strategy == UpdateStrategy.SKIP_EXISTING
        assert analyzer.timestamp_column is None
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_analyze_dataset_changes_empty_data(self, mock_filter, update_analyzer):
        """Test analysis with empty dataset"""
        mock_filter.return_value.values.return_value = []
        
        empty_df = pl.DataFrame()
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", empty_df)
        
        assert analysis["total_rows"] == 0
        assert analysis["total_cells"] == 0
        assert analysis["new_resources"] == 0
        assert analysis["existing_resources"] == 0
        assert analysis["potential_updates"] == 0
        assert analysis["conflicts"] == []
        assert isinstance(analysis["recommendations"], list)
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_analyze_dataset_changes_new_data(self, mock_filter, update_analyzer, sample_csv_data):
        """Test analysis with completely new data"""
        mock_filter.return_value.values.return_value = []  # No existing resources
        
        df = pl.DataFrame(sample_csv_data)
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", df)
        
        assert analysis["total_rows"] == len(sample_csv_data)
        assert analysis["total_cells"] > 0
        assert analysis["new_resources"] > 0
        assert analysis["existing_resources"] == 0
        assert analysis["potential_updates"] == 0
        assert analysis["conflicts"] == []
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_analyze_dataset_changes_existing_data(self, mock_filter, update_analyzer, sample_csv_data):
        """Test analysis with existing data that conflicts"""
        # Mock existing resources (note: URIs are slugified with hyphens)
        existing_resources = [
            {
                'uri': 'http://arkumu.test.org/data/test-org/datasets/test-dataset/name/1',
                'value': 'Old Name',
                'name': 'name',
                'updated_at': datetime.now(timezone.utc) - timedelta(days=1)
            },
            {
                'uri': 'http://arkumu.test.org/data/test-org/datasets/test-dataset/age/1',
                'value': '25',
                'name': 'age',
                'updated_at': datetime.now(timezone.utc) - timedelta(days=1)
            }
        ]
        mock_filter.return_value.values.return_value = existing_resources
        
        df = pl.DataFrame(sample_csv_data[:1])  # Single row for testing
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", df)
        
        assert analysis["existing_resources"] > 0
        assert analysis["potential_updates"] > 0  # Value changes detected
        assert len(analysis["conflicts"]) > 0
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_analyze_dataset_changes_with_mapping_config(self, mock_filter, update_analyzer, 
                                                       sample_csv_data, complex_mapping_config):
        """Test analysis with complex mapping configuration"""
        mock_filter.return_value.values.return_value = []
        
        df = pl.DataFrame([
            {"person_id": "P001", "name": "John", "department_id": "D001", 
             "skills": "Python,Java", "orcid": "0000-0000-0000-0001"}
        ])
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", df, complex_mapping_config)
        
        # Should detect special column types
        assert "person_id" in analysis["anchor_columns"]
        assert "department_id" in analysis["fk_columns"]
        assert "skills" in analysis["multi_value_columns"]
        
        # Should generate appropriate recommendations
        recommendations = " ".join(analysis["recommendations"])
        assert "anchor" in recommendations.lower()
        assert "foreign key" in recommendations.lower()
        assert "multi-value" in recommendations.lower()
    
    def test_would_value_change(self, update_analyzer):
        """Test value change detection"""
        existing_resource = {'value': 'old_value'}
        
        # Same value - no change
        assert not update_analyzer._would_value_change(existing_resource, 'old_value')
        
        # Different value - change detected
        assert update_analyzer._would_value_change(existing_resource, 'new_value')
        
        # Empty existing value
        empty_resource = {'value': ''}
        assert update_analyzer._would_value_change(empty_resource, 'new_value')
        
        # None existing value
        none_resource = {'value': None}
        assert update_analyzer._would_value_change(none_resource, 'new_value')
    
    def test_get_column_type(self, update_analyzer, complex_mapping_config):
        """Test column type detection from mapping config"""
        # Test anchor column
        assert update_analyzer._get_column_type("person_id", complex_mapping_config) == "anchor"
        
        # Test FK column
        assert update_analyzer._get_column_type("department_id", complex_mapping_config) == "foreign_key"
        
        # Test multi-value column
        assert update_analyzer._get_column_type("skills", complex_mapping_config) == "multi_value"
        
        # Test external ontology column
        assert update_analyzer._get_column_type("orcid", complex_mapping_config) == "external_ontology"
        
        # Test regular column
        assert update_analyzer._get_column_type("name", complex_mapping_config) == "regular"
        
        # Test unknown column
        assert update_analyzer._get_column_type("unknown", complex_mapping_config) == "regular"
        
        # Test with no config
        assert update_analyzer._get_column_type("any_column", None) == "regular"
        assert update_analyzer._get_column_type("any_column", {}) == "regular"
    
    def test_parse_timestamp(self, update_analyzer):
        """Test timestamp parsing with various formats"""
        test_cases = [
            ("2023-01-01 10:00:00", True),
            ("2023-01-01T10:00:00", True),
            ("2023-01-01T10:00:00Z", True),
            ("2023-01-01T10:00:00.123", True),
            ("2023-01-01", True),
            ("01.01.2023", True),
            ("01/01/2023", True),
            ("1/1/2023", True),
            ("invalid_date", False),
            ("", False),
            ("2023-13-01", False),  # Invalid month
        ]
        
        for timestamp_str, should_parse in test_cases:
            result = update_analyzer._parse_timestamp(timestamp_str)
            
            if should_parse:
                assert result is not None
                assert isinstance(result, datetime)
                assert result.tzinfo is not None  # Should have timezone
            else:
                assert result is None
    
    def test_compare_timestamps(self, update_analyzer):
        """Test timestamp comparison"""
        base_time = datetime.now(timezone.utc)
        older_time = base_time - timedelta(hours=1)
        newer_time = base_time + timedelta(hours=1)
        
        # Test newer
        assert update_analyzer._compare_timestamps(newer_time, base_time) == "newer"
        
        # Test older
        assert update_analyzer._compare_timestamps(older_time, base_time) == "older"
        
        # Test equal
        assert update_analyzer._compare_timestamps(base_time, base_time) == "equal"
        
        # Test with None existing timestamp
        assert update_analyzer._compare_timestamps(base_time, None) == "unknown"
    
    def test_add_timestamp_analysis(self, update_analyzer, timestamp_csv_data):
        """Test timestamp analysis addition to conflict info"""
        row_data = timestamp_csv_data[0]  # First row
        existing_resource = {
            'updated_at': datetime.now(timezone.utc) - timedelta(hours=1)
        }
        
        conflict_info = {
            "uri": "test://uri",
            "column": "name",
            "row_id": "1"
        }
        
        # Set timestamp column
        update_analyzer.timestamp_column = "updated_at"
        
        update_analyzer._add_timestamp_analysis(conflict_info, row_data, existing_resource)
        
        # Should add timestamp information
        assert "new_timestamp" in conflict_info
        assert "new_timestamp_parsed" in conflict_info
        assert "existing_timestamp" in conflict_info
        assert "timestamp_comparison" in conflict_info
        
        # Should compare timestamps
        assert conflict_info["timestamp_comparison"] in ["newer", "older", "equal"]
    
    def test_generate_recommendations(self, update_analyzer):
        """Test recommendation generation"""
        analysis = {
            "potential_updates": 10,
            "existing_resources": 100,
            "new_resources": 5,
            "fk_columns": ["department_id"],
            "anchor_columns": ["person_id"],
            "multi_value_columns": ["skills"],
            "recommendations": []
        }
        
        update_analyzer._generate_recommendations(analysis)
        
        recommendations = analysis["recommendations"]
        assert len(recommendations) > 0
        
        # Should have recommendation for updates
        assert any("UPDATE_VALUES" in rec for rec in recommendations)
        
        # Should have recommendation for existing data
        assert any("SKIP_EXISTING" in rec for rec in recommendations)
        
        # Should have recommendations for special columns
        assert any("Foreign key" in rec for rec in recommendations)
        assert any("Anchor" in rec for rec in recommendations)
        assert any("Multi-value" in rec for rec in recommendations)
    
    def test_determine_update_strategy_no_existing(self, update_analyzer):
        """Test update strategy for new resources"""
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=None,
            new_value="new_value",
            row_data={"col": "value"},
            column_config=None
        )
        
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_update_strategy_same_value(self, update_analyzer):
        """Test update strategy when values are the same"""
        existing_resource = Mock()
        existing_resource.value = "same_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=existing_resource,
            new_value="same_value",
            row_data={"col": "value"},
            column_config=None
        )
        
        assert strategy == UpdateStrategy.SKIP_EXISTING
    
    def test_determine_update_strategy_skip_existing(self, update_analyzer):
        """Test update strategy with SKIP_EXISTING default"""
        update_analyzer.default_strategy = UpdateStrategy.SKIP_EXISTING
        
        existing_resource = Mock()
        existing_resource.value = "old_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=existing_resource,
            new_value="new_value",
            row_data={"col": "value"},
            column_config=None
        )
        
        assert strategy == UpdateStrategy.SKIP_EXISTING
    
    def test_determine_update_strategy_update_values(self, update_analyzer):
        """Test update strategy with UPDATE_VALUES default"""
        update_analyzer.default_strategy = UpdateStrategy.UPDATE_VALUES
        
        existing_resource = Mock()
        existing_resource.value = "old_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=existing_resource,
            new_value="new_value",
            row_data={"col": "value"},
            column_config=None
        )
        
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_update_strategy_timestamp_based(self, update_analyzer):
        """Test timestamp-based update strategy"""
        update_analyzer.default_strategy = UpdateStrategy.TIMESTAMP_BASED
        update_analyzer.timestamp_column = "updated_at"
        
        # Mock existing resource with old timestamp
        existing_resource = Mock()
        existing_resource.value = "old_value"
        existing_resource.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # Row data with newer timestamp
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        row_data = {
            "col": "new_value",
            "updated_at": future_time.strftime("%Y-%m-%d %H:%M:%S")  # Actually newer
        }
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=existing_resource,
            new_value="new_value",
            row_data=row_data,
            column_config=None
        )
        
        # Should update because timestamp is newer
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_timestamp_based_strategy_newer(self, update_analyzer):
        """Test timestamp-based strategy with newer data"""
        update_analyzer.timestamp_column = "updated_at"
        
        existing_resource = Mock()
        existing_resource.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        row_data = {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        
        strategy = update_analyzer._determine_timestamp_based_strategy(existing_resource, row_data)
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_timestamp_based_strategy_older(self, update_analyzer):
        """Test timestamp-based strategy with older data"""
        update_analyzer.timestamp_column = "updated_at"
        
        existing_resource = Mock()
        existing_resource.updated_at = datetime.now(timezone.utc)
        
        row_data = {
            "updated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        }
        
        strategy = update_analyzer._determine_timestamp_based_strategy(existing_resource, row_data)
        assert strategy == UpdateStrategy.SKIP_EXISTING
    
    def test_determine_timestamp_based_strategy_no_timestamp_column(self, update_analyzer):
        """Test timestamp-based strategy without timestamp column"""
        update_analyzer.timestamp_column = None
        
        existing_resource = Mock()
        row_data = {"col": "value"}
        
        strategy = update_analyzer._determine_timestamp_based_strategy(existing_resource, row_data)
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_timestamp_based_strategy_invalid_timestamp(self, update_analyzer):
        """Test timestamp-based strategy with invalid timestamp"""
        update_analyzer.timestamp_column = "updated_at"
        
        existing_resource = Mock()
        existing_resource.updated_at = datetime.now(timezone.utc)
        
        row_data = {
            "updated_at": "invalid_timestamp"
        }
        
        strategy = update_analyzer._determine_timestamp_based_strategy(existing_resource, row_data)
        assert strategy == UpdateStrategy.UPDATE_VALUES  # Default when can't parse


@pytest.mark.django_db
class TestUpdateAnalyzerPerformance:
    """Performance tests for UpdateAnalyzer"""
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_large_dataset_analysis_performance(self, mock_filter, update_analyzer, performance_test_data):
        """Test analysis performance with large dataset"""
        # Mock existing resources (simulate some existing data)
        existing_resources = [
            {
                'uri': f'http://test.org/cell_{i}',
                'value': f'old_value_{i}',
                'name': 'name',
                'updated_at': datetime.now(timezone.utc)
            }
            for i in range(100)  # Some existing resources
        ]
        mock_filter.return_value.values.return_value = existing_resources
        
        # Use subset of performance data
        test_data = performance_test_data[:5000]
        df = pl.DataFrame(test_data)
        
        import time
        start_time = time.time()
        
        analysis = update_analyzer.analyze_dataset_changes("performance_test", df)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify analysis completed
        assert analysis["total_rows"] == len(test_data)
        assert analysis["total_cells"] > 0
        
        # Should complete in reasonable time
        assert processing_time < 30.0  # Should complete within 30 seconds
        
        print(f"Analysis of {len(test_data)} rows completed in {processing_time:.2f} seconds")
    
    def test_timestamp_parsing_performance(self, update_analyzer):
        """Test timestamp parsing performance"""
        # Create many timestamp strings
        timestamp_strings = [
            "2023-01-01 10:00:00",
            "2023-01-01T10:00:00Z",
            "2023-01-01",
            "01/01/2023",
            "invalid_date"
        ] * 1000
        
        import time
        start_time = time.time()
        
        results = [update_analyzer._parse_timestamp(ts) for ts in timestamp_strings]
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should be efficient
        assert processing_time < 5.0  # Should complete quickly
        assert len(results) == len(timestamp_strings)
        
        print(f"Parsed {len(timestamp_strings)} timestamps in {processing_time:.3f} seconds")


@pytest.mark.django_db
class TestUpdateAnalyzerEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_analysis_with_malformed_data(self, update_analyzer):
        """Test analysis with malformed DataFrame"""
        # DataFrame with missing columns
        incomplete_df = pl.DataFrame({"incomplete": ["data"]})
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", incomplete_df)
        
        # Should handle gracefully
        assert isinstance(analysis, dict)
        assert analysis["total_rows"] == 1
    
    def test_analysis_with_none_values(self, update_analyzer):
        """Test analysis with None values in data"""
        df = pl.DataFrame({
            "name": ["John", None, "Jane"],
            "age": [None, "25", "30"]
        })
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", df)
        
        # Should handle None values gracefully
        assert isinstance(analysis, dict)
        assert analysis["total_rows"] == 3
    
    def test_timestamp_analysis_edge_cases(self, update_analyzer):
        """Test timestamp analysis with edge cases"""
        edge_cases = [
            "",
            "0000-00-00",
            "9999-12-31 23:59:59",
            "2023-02-29",  # Invalid date
            "not_a_date_at_all"
        ]
        
        for timestamp_str in edge_cases:
            result = update_analyzer._parse_timestamp(timestamp_str)
            # Should not raise exceptions
            assert result is None or isinstance(result, datetime)
    
    def test_recommendations_with_empty_analysis(self, update_analyzer):
        """Test recommendation generation with empty analysis"""
        empty_analysis = {
            "potential_updates": 0,
            "existing_resources": 0,
            "new_resources": 0,
            "fk_columns": [],
            "anchor_columns": [],
            "multi_value_columns": [],
            "recommendations": []
        }
        
        update_analyzer._generate_recommendations(empty_analysis)
        
        # Should handle empty analysis gracefully
        assert isinstance(empty_analysis["recommendations"], list)
    
    def test_value_change_detection_edge_cases(self, update_analyzer):
        """Test value change detection with edge cases"""
        edge_cases = [
            ({'value': None}, "", True),  # None in DB, empty string in CSV
            ({'value': ""}, "", False),   # Empty string in both
            ({'value': "old"}, "new", True),  # Different strings
            ({'value': "same"}, "same", False),  # Same strings
            ({'value': "0"}, "1", True),  # Different numeric strings
            ({'value': "true"}, "True", True),  # Different boolean strings (case matters)
        ]
        
        for existing_resource, new_value, expected_change in edge_cases:
            result = update_analyzer._would_value_change(existing_resource, new_value)
            assert result == expected_change
    
    @patch('arkumu.metadata.models.Resource.objects.filter')
    def test_analysis_with_very_long_values(self, mock_filter, update_analyzer):
        """Test analysis with very long cell values"""
        mock_filter.return_value.values.return_value = []
        
        long_value = "x" * 10000
        df = pl.DataFrame({
            "long_column": [long_value, "normal_value"]
        })
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", df)
        
        # Should handle long values gracefully
        assert analysis["total_rows"] == 2
        assert analysis["total_cells"] == 2
    
    def test_update_strategy_with_none_resource(self, update_analyzer):
        """Test update strategy determination with None resource"""
        strategy = update_analyzer.determine_update_strategy(
            existing_resource=None,
            new_value="any_value",
            row_data={},
            column_config={}
        )
        
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_column_type_detection_malformed_config(self, update_analyzer):
        """Test column type detection with malformed config"""
        malformed_configs = [
            None,
            {},
            {"columns": None},
            {"columns": {}},
            {"not_columns": {"col": {}}},
            {"columns": {"col": None}},
            {"columns": {"col": "not_a_dict"}}
        ]
        
        for config in malformed_configs:
            result = update_analyzer._get_column_type("any_column", config)
            assert result == "regular"  # Should default to regular