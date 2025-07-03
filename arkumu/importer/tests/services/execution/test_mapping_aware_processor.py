"""
Tests for MappingAwareProcessor
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
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
    FKRelationship,
    RelationshipContext
)
from arkumu.importer.services.execution.statistics import ExecutionStatistics


@pytest.fixture
def mock_statistics():
    """Mock ExecutionStatistics instance."""
    from arkumu.importer.services.execution.statistics import ExecutionMetrics
    stats = Mock(spec=ExecutionStatistics)
    # Create a real ExecutionMetrics object instead of mocking it
    stats.current_metrics = ExecutionMetrics()
    return stats


@pytest.fixture
def mapping_aware_processor(mock_statistics):
    """MappingAwareProcessor instance for testing."""
    return MappingAwareProcessor(
        institution="test_institution",
        base_uri="http://test.example.com",
        statistics=mock_statistics
    )


@pytest.fixture
def sample_execution_config():
    """Sample execution configuration for testing."""
    # Create column configs
    name_column = ColumnConfig(
        column_name="name",
        dataset_name="people",
        arkumu_type="person_name",
        column_type=ColumnType.REGULAR,
        is_anchor=True
    )
    
    age_column = ColumnConfig(
        column_name="age",
        dataset_name="people", 
        arkumu_type="person_age",
        datatype="http://www.w3.org/2001/XMLSchema#int"
    )
    
    tags_column = ColumnConfig(
        column_name="tags",
        dataset_name="people",
        arkumu_type="person_tags",
        column_type=ColumnType.MULTI_VALUE,
        is_multi_value=True,
        multi_value_separator=","
    )
    
    # Create dataset config
    people_dataset = DatasetConfig(
        dataset_name="people",
        columns=[name_column, age_column, tags_column]
    )
    
    # Create execution config
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="test_mapping",
        organization="test_org",
        datasets=[people_dataset],
        fk_relationships=[],
        relationship_contexts=[],
        external_ontologies=[]
    )


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing."""
    return {
        "people": [
            {"name": "Alice", "age": 25, "tags": "art,design"},
            {"name": "Bob", "age": 30, "tags": "tech"},
            {"name": "Charlie", "age": 35, "tags": "music,art"}
        ]
    }


@pytest.fixture
def fk_execution_config():
    """Execution config with FK relationships."""
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
        mapping_name="fk_test_mapping",
        organization="test_org",
        datasets=[departments_dataset, people_dataset],  # Departments first (dependency order)
        fk_relationships=[fk_rel],
        relationship_contexts=[],
        external_ontologies=[]
    )


@pytest.fixture
def fk_csv_data():
    """CSV data with FK relationships."""
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


class TestMappingAwareProcessor:
    """Test MappingAwareProcessor functionality."""
    
    def test_initialization(self, mapping_aware_processor, mock_statistics):
        """Test processor initializes correctly."""
        assert mapping_aware_processor.institution == "test_institution"
        assert mapping_aware_processor.base_uri == "http://test.example.com"
        assert mapping_aware_processor.statistics == mock_statistics
        assert mapping_aware_processor.data_processor is not None
        assert mapping_aware_processor.resource_manager is not None
        assert mapping_aware_processor.entity_cache == {}
        assert mapping_aware_processor.pending_relationships == []
    
    @patch('arkumu.importer.services.execution.mapping_aware_processor.logger')
    def test_process_with_execution_config_entity_centric(self, mock_logger, mapping_aware_processor, 
                                                        sample_execution_config, sample_csv_data):
        """Test processing with entity-centric strategy."""
        with patch.object(mapping_aware_processor, '_process_entity_centric') as mock_process:
            mock_process.return_value = Mock()
            
            result = mapping_aware_processor.process_with_execution_config(
                sample_execution_config,
                sample_csv_data,
                ProcessingStrategy.ENTITY_CENTRIC
            )
            
            mock_process.assert_called_once()
            mock_logger.info.assert_called_with(
                "Starting mapping-aware processing with ProcessingStrategy.ENTITY_CENTRIC strategy"
            )
    
    def test_process_with_execution_config_unsupported_strategy(self, mapping_aware_processor,
                                                               sample_execution_config, sample_csv_data):
        """Test error handling for unsupported strategy."""
        with pytest.raises(ValueError, match="Unsupported processing strategy"):
            mapping_aware_processor.process_with_execution_config(
                sample_execution_config,
                sample_csv_data,
                "invalid_strategy"
            )
    
    def test_group_columns_by_type(self, mapping_aware_processor):
        """Test column grouping by type."""
        columns = [
            ColumnConfig("name", "test", "name", is_anchor=True),
            ColumnConfig("age", "test", "age"), 
            ColumnConfig("dept", "test", "dept", column_type=ColumnType.FOREIGN_KEY),
            ColumnConfig("tags", "test", "tags", is_multi_value=True),
            ColumnConfig("wiki", "test", "wiki", is_external_ontology=True),
            ColumnConfig("context", "test", "context", column_type=ColumnType.RELATIONSHIP_CONTEXT)
        ]
        
        groups = mapping_aware_processor._group_columns_by_type(columns)
        
        assert len(groups['anchor']) == 1
        assert groups['anchor'][0].column_name == "name"
        
        assert len(groups['regular']) == 1
        assert groups['regular'][0].column_name == "age"
        
        assert len(groups['foreign_key']) == 1
        assert groups['foreign_key'][0].column_name == "dept"
        
        assert len(groups['multi_value']) == 1
        assert groups['multi_value'][0].column_name == "tags"
        
        assert len(groups['external_ontology']) == 1
        assert groups['external_ontology'][0].column_name == "wiki"
        
        assert len(groups['relationship_context']) == 1
        assert groups['relationship_context'][0].column_name == "context"
    
    def test_generate_entity_uri_with_anchor_columns(self, mapping_aware_processor):
        """Test entity URI generation using anchor columns."""
        dataset_config = Mock()
        dataset_config.columns = [
            Mock(is_anchor=True, column_name="id"),
            Mock(is_anchor=False, column_name="name")
        ]
        
        row_data = {"id": "123", "name": "Test"}
        
        with patch.object(mapping_aware_processor.resource_manager, 'generate_entity_uri') as mock_gen:
            mock_gen.return_value = "http://test.example.com/entities/test_dataset/123"
            
            result = mapping_aware_processor._generate_entity_uri("test_dataset", row_data, dataset_config)
            
            mock_gen.assert_called_once_with("test_dataset", "123")
            assert result == "http://test.example.com/entities/test_dataset/123"
    
    def test_generate_entity_uri_fallback_to_row_id(self, mapping_aware_processor):
        """Test entity URI generation falling back to row_id."""
        dataset_config = Mock()
        dataset_config.columns = [Mock(is_anchor=False, column_name="name")]
        
        row_data = {"name": "Test", "row_id": 5}
        
        with patch.object(mapping_aware_processor.resource_manager, 'generate_entity_uri') as mock_gen:
            mock_gen.return_value = "http://test.example.com/entities/test_dataset/6"
            
            result = mapping_aware_processor._generate_entity_uri("test_dataset", row_data, dataset_config)
            
            mock_gen.assert_called_once_with("test_dataset", "6")  # row_id + 1
    
    def test_split_multi_value(self, mapping_aware_processor):
        """Test multi-value string splitting."""
        # Normal splitting
        result = mapping_aware_processor._split_multi_value("art,design,tech", ",")
        assert result == ["art", "design", "tech"]
        
        # With whitespace
        result = mapping_aware_processor._split_multi_value(" art , design , tech ", ",")
        assert result == ["art", "design", "tech"]
        
        # Empty separator
        result = mapping_aware_processor._split_multi_value("art,design", "")
        assert result == ["art,design"]
        
        # Empty value
        result = mapping_aware_processor._split_multi_value("", ",")
        assert result == []
    
    def test_generate_property_uri(self, mapping_aware_processor):
        """Test property URI generation."""
        # Regular arkumu type
        result = mapping_aware_processor._generate_property_uri("person_name")
        assert result == "http://test.example.com/properties/person_name"
        
        # Full URI
        result = mapping_aware_processor._generate_property_uri("http://schema.org/name")
        assert result == "http://schema.org/name"
    
    def test_generate_external_ontology_uri(self, mapping_aware_processor):
        """Test external ontology URI generation."""
        column = ColumnConfig(
            column_name="orcid",
            dataset_name="people",
            arkumu_type="person_orcid",
            external_ontology_config={
                'uri_template': 'https://orcid.org/{identifier}'
            }
        )
        
        result = mapping_aware_processor._generate_external_ontology_uri(column, "0000-0000-0000-0000")
        assert result == "https://orcid.org/0000-0000-0000-0000"
        
        # No config
        column.external_ontology_config = None
        result = mapping_aware_processor._generate_external_ontology_uri(column, "test")
        assert result is None
    
    @patch('arkumu.importer.services.execution.mapping_aware_processor.logger')
    def test_process_entity_centric_missing_csv_data(self, mock_logger, mapping_aware_processor,
                                                    sample_execution_config):
        """Test entity-centric processing handles missing CSV data."""
        context = ProcessingContext(
            execution_config=sample_execution_config,
            current_dataset="",
            all_csv_sources={},  # Empty CSV sources
            entity_cache={},
            processed_datasets=set()
        )
        
        with patch.object(mapping_aware_processor, '_resolve_pending_relationships'):
            result = mapping_aware_processor._process_entity_centric(context)
            
            mock_logger.warning.assert_called_with("No CSV data for dataset: people")
    
    def test_process_regular_columns(self, mapping_aware_processor):
        """Test processing of regular columns."""
        entity_resource = Mock()
        row_data = {"name": "Alice", "age": "25"}
        
        columns = [
            ColumnConfig("name", "people", "person_name"),
            ColumnConfig("age", "people", "person_age", datatype="http://www.w3.org/2001/XMLSchema#int")
        ]
        
        context = Mock()
        
        with patch.object(mapping_aware_processor.resource_manager, 'create_property_triple') as mock_create:
            mapping_aware_processor._process_regular_columns(entity_resource, row_data, columns, context)
            
            assert mock_create.call_count == 2
            
            # Check first call (name)
            call_args = mock_create.call_args_list[0]
            assert call_args[0][0] == entity_resource
            assert call_args[0][1] == "http://test.example.com/properties/person_name"
            assert call_args[0][2] == "Alice"
            assert call_args[0][3] == "http://www.w3.org/2001/XMLSchema#string"
            
            # Check second call (age)
            call_args = mock_create.call_args_list[1]
            assert call_args[0][1] == "http://test.example.com/properties/person_age"
            assert call_args[0][2] == "25"
            assert call_args[0][3] == "http://www.w3.org/2001/XMLSchema#int"
    
    def test_process_multi_value_columns(self, mapping_aware_processor):
        """Test processing of multi-value columns."""
        entity_resource = Mock()
        row_data = {"tags": "art,design,tech"}
        
        columns = [
            ColumnConfig(
                "tags", 
                "people", 
                "person_tags",
                is_multi_value=True,
                multi_value_separator=","
            )
        ]
        
        context = Mock()
        
        with patch.object(mapping_aware_processor.resource_manager, 'create_property_triple') as mock_create:
            mapping_aware_processor._process_multi_value_columns(entity_resource, row_data, columns, context)
            
            # Should create 3 property triples (one for each tag)
            assert mock_create.call_count == 3
            
            # Check the values
            calls = mock_create.call_args_list
            values = [call[0][2] for call in calls]
            assert "art" in values
            assert "design" in values
            assert "tech" in values
    
    def test_queue_fk_relationships(self, mapping_aware_processor):
        """Test queuing of FK relationships."""
        entity_uri = "http://test.example.com/entities/people/alice"
        row_data = {"department": "engineering"}
        
        columns = [
            ColumnConfig(
                "department",
                "people", 
                "works_in",
                column_type=ColumnType.FOREIGN_KEY
            )
        ]
        
        context = Mock()
        
        with patch.object(mapping_aware_processor, '_get_target_dataset_for_column') as mock_get_target:
            mock_get_target.return_value = "departments"
            
            mapping_aware_processor._queue_fk_relationships(entity_uri, row_data, columns, context)
            
            assert len(mapping_aware_processor.pending_relationships) == 1
            
            relationship = mapping_aware_processor.pending_relationships[0]
            assert relationship['source_entity_uri'] == entity_uri
            assert relationship['source_column'] == "department"
            assert relationship['target_value'] == "engineering"
            assert relationship['target_dataset'] == "departments"
            assert relationship['relationship_type'] == "works_in"
    
    def test_queue_fk_relationships_multi_value(self, mapping_aware_processor):
        """Test queuing FK relationships for multi-value columns."""
        entity_uri = "http://test.example.com/entities/people/alice"
        row_data = {"departments": "engineering,design"}
        
        columns = [
            ColumnConfig(
                "departments",
                "people",
                "works_in", 
                column_type=ColumnType.FOREIGN_KEY,
                is_multi_value=True,
                multi_value_separator=","
            )
        ]
        
        context = Mock()
        
        with patch.object(mapping_aware_processor, '_get_target_dataset_for_column') as mock_get_target:
            mock_get_target.return_value = "departments"
            
            mapping_aware_processor._queue_fk_relationships(entity_uri, row_data, columns, context)
            
            # Should queue 2 relationships
            assert len(mapping_aware_processor.pending_relationships) == 2
            
            values = [rel['target_value'] for rel in mapping_aware_processor.pending_relationships]
            assert "engineering" in values
            assert "design" in values
    
    @patch('arkumu.importer.services.execution.mapping_aware_processor.logger')
    def test_resolve_pending_relationships_success(self, mock_logger, mapping_aware_processor):
        """Test successful resolution of pending relationships."""
        # Setup pending relationship
        mapping_aware_processor.pending_relationships = [{
            'source_entity_uri': 'http://test.example.com/entities/people/alice',
            'source_column': 'department',
            'target_value': 'engineering',
            'target_dataset': 'departments',
            'relationship_type': 'works_in'
        }]
        
        # Setup context with entity cache
        context = Mock()
        context.entity_cache = {
            'http://test.example.com/entities/people/alice': Mock(),
            'http://test.example.com/entities/departments/engineering': Mock()
        }
        
        # Mock methods
        with patch.object(mapping_aware_processor, '_generate_target_entity_uri') as mock_gen_uri, \
             patch.object(mapping_aware_processor, '_get_or_create_target_entity') as mock_get_target, \
             patch.object(mapping_aware_processor, '_generate_property_uri') as mock_gen_prop, \
             patch.object(mapping_aware_processor.resource_manager, 'create_relationship_triple') as mock_create_rel:
            
            mock_gen_uri.return_value = 'http://test.example.com/entities/departments/engineering'
            mock_get_target.return_value = context.entity_cache['http://test.example.com/entities/departments/engineering']
            mock_gen_prop.return_value = 'http://test.example.com/properties/works_in'
            
            mapping_aware_processor._resolve_pending_relationships(context)
            
            # Verify relationship was created
            mock_create_rel.assert_called_once()
            
            # Verify pending relationships cleared
            assert len(mapping_aware_processor.pending_relationships) == 0
            
            # Check log messages
            mock_logger.info.assert_any_call("Resolving 1 pending FK relationships")
            mock_logger.info.assert_any_call("FK resolution completed: 1 resolved, 0 failed")
    
    @patch('arkumu.importer.services.execution.mapping_aware_processor.logger')
    def test_resolve_pending_relationships_failure(self, mock_logger, mapping_aware_processor):
        """Test handling of failed relationship resolution."""
        # Setup pending relationship
        mapping_aware_processor.pending_relationships = [{
            'source_entity_uri': 'http://test.example.com/entities/people/alice',
            'source_column': 'department',
            'target_value': 'engineering',
            'target_dataset': 'departments',
            'relationship_type': 'works_in'
        }]
        
        context = Mock()
        context.entity_cache = {}  # Empty cache - will cause failure
        
        with patch.object(mapping_aware_processor, '_generate_target_entity_uri'), \
             patch.object(mapping_aware_processor, '_get_or_create_target_entity') as mock_get_target:
            
            mock_get_target.return_value = None  # Simulate failure
            
            mapping_aware_processor._resolve_pending_relationships(context)
            
            # Check failure was logged
            mock_logger.warning.assert_called()
            mock_logger.info.assert_any_call("FK resolution completed: 0 resolved, 1 failed")
    
    def test_get_or_create_target_entity_from_cache(self, mapping_aware_processor):
        """Test getting target entity from cache."""
        target_uri = "http://test.example.com/entities/departments/engineering"
        cached_entity = Mock()
        
        context = Mock()
        context.entity_cache = {target_uri: cached_entity}
        
        relationship = {'target_dataset': 'departments'}
        
        result = mapping_aware_processor._get_or_create_target_entity(target_uri, relationship, context)
        
        assert result == cached_entity
    
    def test_get_or_create_target_entity_create_stub(self, mapping_aware_processor):
        """Test creating stub target entity."""
        target_uri = "http://test.example.com/entities/departments/engineering"
        stub_entity = Mock()
        
        context = Mock()
        context.entity_cache = {}
        
        relationship = {'target_dataset': 'departments'}
        
        with patch.object(mapping_aware_processor.resource_manager, 'create_entity_resource') as mock_create:
            mock_create.return_value = stub_entity
            
            result = mapping_aware_processor._get_or_create_target_entity(target_uri, relationship, context)
            
            mock_create.assert_called_once_with(target_uri, 'departments', is_stub=True)
            assert result == stub_entity
            assert context.entity_cache[target_uri] == stub_entity


class TestMappingAwareProcessorIntegration:
    """Integration tests for MappingAwareProcessor."""
    
    @pytest.mark.django_db
    def test_entity_centric_processing_integration(self, mapping_aware_processor, 
                                                  sample_execution_config, sample_csv_data):
        """Test complete entity-centric processing flow."""
        # Test the actual processing using SmartBulkUpdaterPolars
        result = mapping_aware_processor.process_with_execution_config(
            sample_execution_config,
            sample_csv_data,
            ProcessingStrategy.ENTITY_CENTRIC
        )
        
        # Verify processing completed successfully
        assert result.resources_created > 0
        assert result.triples_created > 0
        
        # Multi-value processing creates additional "rows" for each split value:
        # Alice: art,design = 2 split values (2 rows)
        # Bob: tech = 1 value (1 row)  
        # Charlie: music,art = 2 split values (2 rows)
        # Total: 2 + 1 + 2 = 5 rows processed
        assert result.rows_processed == 5
        
        # Verify multi-value processing occurred
        # Alice: art,design = 2 values; Charlie: music,art = 2 values; Bob: tech = 1 value
        # Total: 2 + 2 + 1 = 5 tag values + 3 names + 3 ages = 11 cell values
        assert result.cells_processed == 11
    
    @pytest.mark.django_db  
    def test_fk_relationship_processing_integration(self, mapping_aware_processor,
                                                   fk_execution_config, fk_csv_data):
        """Test FK relationship processing integration."""
        # Test the actual FK processing using SmartBulkUpdaterPolars
        result = mapping_aware_processor.process_with_execution_config(
            fk_execution_config,
            fk_csv_data,
            ProcessingStrategy.ENTITY_CENTRIC
        )
        
        # Verify processing completed successfully
        assert result.resources_created > 0
        assert result.triples_created > 0
        assert result.rows_processed == 4  # 2 departments + 2 people = 4 total rows
        
        # Verify FK relationships were processed
        # 2 people + 2 departments = 4 entities, each with name columns = 4 cells
        # 2 people with department_id columns = 2 more cells
        # Total: 4 + 2 = 6 cells processed  
        assert result.cells_processed == 6