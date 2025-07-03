"""
Tests for the integrated MappingAwareProcessor + SmartBulkUpdaterPolars system
"""

import pytest
from unittest.mock import Mock, patch
import polars as pl
from dataclasses import dataclass
from typing import Dict, Any, List

from arkumu.importer.services.execution.mapping_aware_processor import (
    MappingAwareProcessor, 
    ProcessingContext
)
from arkumu.importer.services.mapping_consumer import (
    ExecutionConfig, 
    ColumnConfig, 
    DatasetConfig,
    ColumnType,
    ProcessingStrategy,
    FKRelationship
)
from arkumu.importer.services.execution.statistics import ExecutionStatistics


@pytest.fixture
def integrated_processor():
    """MappingAwareProcessor with integrated SmartBulkUpdaterPolars."""
    statistics = ExecutionStatistics()
    return MappingAwareProcessor(
        institution="test_institution",
        base_uri="http://test.example.com",
        statistics=statistics
    )


@pytest.fixture
def multi_value_execution_config():
    """Execution config with multi-value columns."""
    # Create column configs
    name_column = ColumnConfig(
        column_name="name",
        dataset_name="people",
        arkumu_type="person_name",
        column_type=ColumnType.REGULAR,
        is_anchor=True
    )
    
    skills_column = ColumnConfig(
        column_name="skills",
        dataset_name="people",
        arkumu_type="person_skills",
        column_type=ColumnType.MULTI_VALUE,
        is_multi_value=True,
        multi_value_separator=","
    )
    
    # Create dataset config
    people_dataset = DatasetConfig(
        dataset_name="people",
        columns=[name_column, skills_column]
    )
    
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="multi_value_test",
        organization="test_org",
        datasets=[people_dataset],
        fk_relationships=[],
        relationship_contexts=[],
        external_ontologies=[]
    )


@pytest.fixture
def multi_value_csv_data():
    """CSV data with multi-value columns."""
    return {
        "people": [
            {"name": "Alice", "skills": "python,javascript,sql"},
            {"name": "Bob", "skills": "java,kotlin"},
            {"name": "Charlie", "skills": "ruby,go,rust,docker"}
        ]
    }


@pytest.fixture
def fk_integrated_execution_config():
    """Execution config with FK relationships for integrated testing."""
    # Person columns
    person_name = ColumnConfig(
        column_name="name", 
        dataset_name="people",
        arkumu_type="person_name",
        is_anchor=True
    )
    
    person_dept = ColumnConfig(
        column_name="department_id",
        dataset_name="people", 
        arkumu_type="works_in",
        column_type=ColumnType.FOREIGN_KEY
    )
    
    # Department columns  
    dept_name = ColumnConfig(
        column_name="name",
        dataset_name="departments",
        arkumu_type="department_name", 
        is_anchor=True
    )
    
    # Create datasets
    people_dataset = DatasetConfig(
        dataset_name="people",
        columns=[person_name, person_dept]
    )
    
    departments_dataset = DatasetConfig(
        dataset_name="departments", 
        columns=[dept_name]
    )
    
    # Create FK relationship
    fk_rel = FKRelationship(
        source_column="department_id",
        source_dataset="people",
        target_column="name", 
        target_dataset="departments",
        relationship_type="works_in"
    )
    
    return ExecutionConfig(
        mapping_id=2,
        mapping_name="fk_integrated_test",
        organization="test_org",
        datasets=[departments_dataset, people_dataset],
        fk_relationships=[fk_rel],
        relationship_contexts=[],
        external_ontologies=[]
    )


@pytest.fixture
def fk_integrated_csv_data():
    """CSV data with FK relationships for integrated testing."""
    return {
        "departments": [
            {"name": "Engineering"},
            {"name": "Design"}
        ],
        "people": [
            {"name": "Alice", "department_id": "Engineering"},
            {"name": "Bob", "department_id": "Design"}
        ]
    }


class TestIntegratedMappingBulkProcessor:
    """Test integrated MappingAwareProcessor + SmartBulkUpdaterPolars system."""
    
    def test_bulk_updater_initialization(self, integrated_processor):
        """Test that the bulk updater is properly initialized."""
        assert integrated_processor.bulk_updater is not None
        assert integrated_processor.bulk_updater.institution == "test-institution"  # Slugified
        assert integrated_processor.bulk_updater.base_uri == "http://test.example.com"
        assert integrated_processor.bulk_updater.link_row_cells is True
        assert integrated_processor.bulk_updater.link_topology == "row"
    
    def test_column_config_conversion(self, integrated_processor):
        """Test conversion of mapping column configs to bulk format."""
        columns = [
            ColumnConfig("name", "test", "name", is_anchor=True),
            ColumnConfig("skills", "test", "skills", is_multi_value=True, multi_value_separator=","),
            ColumnConfig("dept", "test", "dept", column_type=ColumnType.FOREIGN_KEY)
        ]
        
        bulk_configs = integrated_processor._convert_column_configs_to_bulk_format(columns)
        
        assert "name" in bulk_configs
        assert bulk_configs["name"]["is_anchor"] is True
        assert bulk_configs["name"]["is_multi_value"] is False
        
        assert "skills" in bulk_configs
        assert bulk_configs["skills"]["is_multi_value"] is True
        assert bulk_configs["skills"]["multi_value_separator"] == ","
        
        assert "dept" in bulk_configs
        assert bulk_configs["dept"]["column_type"] == "foreign_key"
    
    @pytest.mark.django_db
    def test_multi_value_processing_integration(self, integrated_processor, 
                                              multi_value_execution_config, multi_value_csv_data):
        """Test integrated multi-value processing."""
        # Mock the bulk updater methods to track calls
        with patch.object(integrated_processor.bulk_updater, 'determine_update_actions_polars') as mock_determine, \
             patch.object(integrated_processor.bulk_updater, 'execute_bulk_update') as mock_execute:
            
            # Configure mocks with proper BulkUpdateStats attributes
            from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats
            mock_stats = BulkUpdateStats()
            mock_determine.return_value = ([], mock_stats)
            
            exec_stats = BulkUpdateStats()
            exec_stats.resources_created = 6
            exec_stats.triples_created = 9
            exec_stats.relationships_created = 0
            mock_execute.return_value = exec_stats
            
            result = integrated_processor.process_with_execution_config(
                multi_value_execution_config,
                multi_value_csv_data,
                ProcessingStrategy.ENTITY_CENTRIC
            )
            
            # Verify the bulk updater was called with column configs
            mock_determine.assert_called_once()
            call_args = mock_determine.call_args
            dataset_name = call_args[0][1]
            column_configs = call_args[0][2]
            
            assert dataset_name == "people"
            assert "name" in column_configs
            assert "skills" in column_configs
            assert column_configs["skills"]["is_multi_value"] is True
            assert column_configs["skills"]["multi_value_separator"] == ","
    
    @pytest.mark.django_db
    def test_fk_relationship_integration(self, integrated_processor,
                                       fk_integrated_execution_config, fk_integrated_csv_data):
        """Test integrated FK relationship processing."""
        # Mock the bulk updater methods
        with patch.object(integrated_processor.bulk_updater, 'determine_update_actions_polars') as mock_determine, \
             patch.object(integrated_processor.bulk_updater, 'execute_bulk_update') as mock_execute, \
             patch.object(integrated_processor.bulk_updater, 'process_fk_relationships') as mock_fk:
            
            # Configure mocks with proper BulkUpdateStats attributes
            from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats
            mock_stats = BulkUpdateStats()
            mock_determine.return_value = ([], mock_stats)
            
            exec_stats = BulkUpdateStats()
            exec_stats.resources_created = 4
            exec_stats.triples_created = 4
            exec_stats.relationships_created = 0
            mock_execute.return_value = exec_stats
            
            fk_stats = BulkUpdateStats()
            fk_stats.triples_created = 2
            fk_stats.relationships_created = 2
            mock_fk.return_value = fk_stats
            
            result = integrated_processor.process_with_execution_config(
                fk_integrated_execution_config,
                fk_integrated_csv_data,
                ProcessingStrategy.ENTITY_CENTRIC
            )
            
            # Verify FK relationships were configured
            fk_relationships = integrated_processor.bulk_updater.fk_relationships
            assert len(fk_relationships) == 1
            assert fk_relationships[0].source_column == "department_id"
            assert fk_relationships[0].target_dataset == "departments"
            assert fk_relationships[0].relationship_type == "works_in"
            
            # Verify FK processing was called
            mock_fk.assert_called_once_with(fk_integrated_csv_data)
    
    def test_bulk_stats_merging(self, integrated_processor):
        """Test merging of BulkUpdateStats into ExecutionMetrics."""
        # Create mock bulk stats with proper BulkUpdateStats object
        from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats
        mock_bulk_stats = BulkUpdateStats()
        mock_bulk_stats.resources_created = 10
        mock_bulk_stats.triples_created = 20
        mock_bulk_stats.relationships_created = 5
        mock_bulk_stats.rows_processed = 100
        mock_bulk_stats.cells_processed = 300
        mock_bulk_stats.errors = 2
        
        # Get initial metrics
        initial_resources = integrated_processor.statistics.current_metrics.resources_created
        initial_triples = integrated_processor.statistics.current_metrics.triples_created
        
        # Merge stats
        integrated_processor._merge_bulk_stats_to_execution_metrics(mock_bulk_stats)
        
        # Verify merging
        metrics = integrated_processor.statistics.current_metrics
        assert metrics.resources_created == initial_resources + 10
        assert metrics.triples_created == initial_triples + 20
        assert metrics.relationships_created == 5
        assert metrics.rows_processed == 100
        assert metrics.cells_processed == 300
        assert metrics.errors == 2
    
    @pytest.mark.django_db
    def test_performance_with_bulk_updater(self, integrated_processor):
        """Test that the integrated system uses the optimized bulk updater for performance."""
        # Create larger dataset for performance testing
        large_csv_data = {
            "test_dataset": [
                {"id": f"item_{i}", "value": f"value_{i}", "tags": f"tag1,tag2,tag3"}
                for i in range(100)  # 100 rows
            ]
        }
        
        config = ExecutionConfig(
            mapping_id=3,
            mapping_name="performance_test",
            organization="test_org",
            datasets=[DatasetConfig(
                dataset_name="test_dataset",
                columns=[
                    ColumnConfig("id", "test_dataset", "item_id", is_anchor=True),
                    ColumnConfig("value", "test_dataset", "item_value"),
                    ColumnConfig("tags", "test_dataset", "item_tags", is_multi_value=True, multi_value_separator=",")
                ]
            )],
            fk_relationships=[],
            relationship_contexts=[],
            external_ontologies=[]
        )
        
        # Mock bulk updater to verify it's being used
        with patch.object(integrated_processor.bulk_updater, 'determine_update_actions_polars') as mock_determine, \
             patch.object(integrated_processor.bulk_updater, 'execute_bulk_update') as mock_execute:
            from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats
            mock_stats = BulkUpdateStats()
            mock_determine.return_value = ([], mock_stats)
            mock_execute.return_value = BulkUpdateStats()
            
            # Process the data
            result = integrated_processor.process_with_execution_config(
                config, large_csv_data, ProcessingStrategy.ENTITY_CENTRIC
            )
            
            # Verify bulk updater was used (not the old resource manager approach)
            mock_determine.assert_called_once()
            
            # Verify the DataFrame was passed (indicating Polars optimization)
            call_args = mock_determine.call_args
            df_arg = call_args[0][0]  # First argument should be the DataFrame
            assert hasattr(df_arg, 'height')  # Polars DataFrame has height attribute
            assert df_arg.height == 100  # Should have 100 rows


class TestSmartBulkUpdaterPolarsEnhancements:
    """Test the enhancements made to SmartBulkUpdaterPolars."""
    
    def test_multi_value_analysis_with_config(self):
        """Test multi-value analysis with explicit configuration."""
        from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
        
        updater = SmartBulkUpdaterPolars()
        df = pl.DataFrame({
            "name": ["Alice", "Bob"],
            "skills": ["python,java", "single_skill"]
        })
        
        # Test with explicit multi-value config
        column_configs = {
            "skills": {"is_multi_value": True, "multi_value_separator": ","}
        }
        
        analysis = updater.analyze_dataset_multi_values_polars(df, column_configs)
        
        assert analysis["skills"]["is_multi_value"] is True
        assert analysis["skills"]["separator"] == ","
        assert analysis["name"]["is_multi_value"] is False
    
    def test_fk_relationship_dataclass(self):
        """Test FK relationship dataclass."""
        from arkumu.importer.services.importer.smart_bulk_updater_polars import FKRelationship
        
        fk_rel = FKRelationship(
            source_column="dept_id",
            source_dataset="employees",
            target_column="id",
            target_dataset="departments",
            relationship_type="belongs_to"
        )
        
        assert fk_rel.source_column == "dept_id"
        assert fk_rel.target_dataset == "departments"
        assert fk_rel.relationship_type == "belongs_to"


@pytest.mark.django_db
class TestFullIntegrationWorkflow:
    """Test the complete integration workflow."""
    
    def test_complete_mapping_to_rdf_workflow(self):
        """Test complete workflow from mapping config to RDF creation."""
        from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
        
        # Create a complete workflow test
        updater = SmartBulkUpdaterPolars(
            institution="test_inst",
            base_uri="http://test.example.com",
            link_row_cells=True
        )
        
        # Test data with multi-value and relationships
        csv_data = [
            {"name": "Alice", "skills": "python,sql", "dept": "Engineering"},
            {"name": "Bob", "skills": "java", "dept": "Design"}
        ]
        
        column_configs = {
            "name": {"is_multi_value": False, "is_anchor": True},
            "skills": {"is_multi_value": True, "multi_value_separator": ","},
            "dept": {"is_multi_value": False, "column_type": "foreign_key"}
        }
        
        # Mock the database operations since this is an integration test
        with patch.object(updater, 'determine_update_actions_polars') as mock_determine:
            # Simulate the processing
            from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats
            mock_stats = BulkUpdateStats()
            mock_stats.resources_created = 10
            mock_stats.triples_created = 15
            mock_determine.return_value = ([], mock_stats)
            
            # Test the updated method signature
            result = updater.import_csv_with_smart_updates(
                csv_data, "test_dataset", column_configs=column_configs
            )
            
            # Verify column configs were passed through
            mock_determine.assert_called_once()
            call_args = mock_determine.call_args
            assert call_args[0][2] == column_configs  # Third argument should be column_configs