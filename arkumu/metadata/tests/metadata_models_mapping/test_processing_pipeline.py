"""
Test suite for ProcessingPipelineService

Tests multi-phase semantic transformation pipelines with various processing stages.
Includes unit tests, integration tests, and performance benchmarks.
"""

import pytest
import polars as pl
from pathlib import Path
import tempfile
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
import time
import uuid

from arkumu.metadata.services.metadata_models_mapping.processing_pipeline import (
    ProcessingPipelineService, ProcessingPhase, ProcessingStatus,
    ProcessingResult, PipelineExecution, ProcessingOptions
)


# Fixtures
@pytest.fixture
def mock_services():
    """Create mock service dependencies"""
    return {
        'table_analysis': Mock(),
        'mapping_config': Mock(),
        'reference_resolution': Mock(),
        'validation': Mock()
    }


@pytest.fixture
def pipeline_service(mock_services):
    """Create ProcessingPipelineService instance with mocked dependencies"""
    return ProcessingPipelineService(
        table_analysis_service=mock_services['table_analysis'],
        mapping_config_service=mock_services['mapping_config'],
        reference_resolution_service=mock_services['reference_resolution'],
        validation_service=mock_services['validation']
    )


@pytest.fixture
def sample_csv_files():
    """Create multiple temporary CSV files for testing"""
    files = []
    
    # Entity table
    entity_data = {
        'id': [1, 2, 3, 4, 5],
        'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
        'department': ['Engineering', 'Sales', 'Engineering', 'Marketing', 'Sales'],
        'email': ['alice@company.com', 'bob@company.com', 'charlie@company.com', 
                 'david@company.com', 'eve@company.com']
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df = pl.DataFrame(entity_data)
        df.write_csv(f.name)
        files.append(f.name)
    
    # Junction table
    junction_data = {
        'employee_id': [1, 1, 2, 3, 4],
        'project_id': ['P001', 'P002', 'P001', 'P002', 'P003'],
        'role': ['Lead', 'Member', 'Member', 'Lead', 'Member']
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df = pl.DataFrame(junction_data)
        df.write_csv(f.name)
        files.append(f.name)
    
    yield files
    
    # Cleanup
    for file_path in files:
        Path(file_path).unlink()


@pytest.fixture
def sample_config():
    """Sample mapping configuration"""
    return {
        'id': 'test_config',
        'entity_rules': [
            {
                'id': 'person_rule',
                'pattern_type': 'column_name',
                'pattern_value': 'name',
                'target_type': 'Person',
                'confidence': 0.9,
                'id_prefix': 'person'
            },
            {
                'id': 'email_rule',
                'pattern_type': 'contains',
                'pattern_value': '@',
                'target_type': 'Email',
                'confidence': 0.85,
                'id_prefix': 'email'
            }
        ],
        'relationship_templates': [
            {
                'id': 'employee_project',
                'source_column': 'employee_id',
                'target_column': 'project_id',
                'predicate': 'worksOn',
                'source_type': 'Person',
                'target_type': 'Project',
                'table_type': 'junction',
                'handles_junction_tables': True
            }
        ]
    }


@pytest.fixture
def sample_analysis():
    """Sample table analysis result"""
    return Mock(
        table_type='entity',
        column_count=4,
        row_count=5,
        quality_score=0.85,
        columns=[
            Mock(name='id'),
            Mock(name='name'),
            Mock(name='department'),
            Mock(name='email')
        ]
    )


@pytest.fixture
def processing_options():
    """Default processing options"""
    return ProcessingOptions(
        dry_run=False,
        parallel_processing=False,  # Easier for testing
        max_workers=2,
        chunk_size=1000,
        validate_during_processing=True,
        continue_on_errors=False,
        output_format='turtle',
        create_backup=True
    )


# Unit Tests
class TestProcessingPipelineService:
    """Unit tests for ProcessingPipelineService"""
    
    def test_initialization(self, mock_services):
        """Test service initialization"""
        service = ProcessingPipelineService(
            table_analysis_service=mock_services['table_analysis'],
            mapping_config_service=mock_services['mapping_config'],
            reference_resolution_service=mock_services['reference_resolution'],
            validation_service=mock_services['validation']
        )
        
        assert service.table_analysis == mock_services['table_analysis']
        assert service.mapping_config == mock_services['mapping_config']
        assert service.reference_resolution == mock_services['reference_resolution']
        assert service.validation == mock_services['validation']
        assert len(service._phase_processors) == 5
        assert service._executions == {}
    
    @patch('uuid.uuid4')
    def test_execute_pipeline_success(self, mock_uuid, pipeline_service, sample_csv_files,
                                    sample_config, sample_analysis, processing_options):
        """Test successful pipeline execution"""
        # Setup
        mock_uuid.return_value = 'test-execution-id'
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        pipeline_service.validation.validate_entity.return_value = {'errors': []}
        pipeline_service.validation.validate_relationship.return_value = {'errors': []}
        
        # Execute
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=processing_options
        )
        
        # Verify
        assert execution_id == 'test-execution-id'
        assert execution_id in pipeline_service._executions
        
        execution = pipeline_service._executions[execution_id]
        assert execution.total_status == ProcessingStatus.COMPLETED
        assert len(execution.phase_results) == 5
        assert execution.end_time is not None
        assert execution.summary is not None
    
    def test_execute_pipeline_no_config(self, pipeline_service):
        """Test pipeline execution with missing configuration"""
        pipeline_service.mapping_config.get_configuration.return_value = None
        
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=['dummy.csv'],
            configuration_id='missing_config'
        )
        
        execution = pipeline_service._executions[execution_id]
        assert execution.total_status == ProcessingStatus.FAILED
        assert len(execution.phase_results) > 0
        assert any('Configuration missing_config not found' in str(r.errors) 
                  for r in execution.phase_results)
    
    def test_execute_pipeline_with_phase_failure(self, pipeline_service, sample_csv_files,
                                                sample_config, processing_options):
        """Test pipeline execution with phase failure"""
        # Setup - make analysis phase fail
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.side_effect = Exception("Analysis failed")
        
        # Execute
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=processing_options
        )
        
        # Verify
        execution = pipeline_service._executions[execution_id]
        assert execution.total_status == ProcessingStatus.FAILED
        assert execution.phase_results[0].status == ProcessingStatus.FAILED
        assert "Analysis failed" in str(execution.phase_results[0].errors)
    
    def test_execute_pipeline_continue_on_errors(self, pipeline_service, sample_csv_files,
                                                sample_config, sample_analysis):
        """Test pipeline execution with continue_on_errors option"""
        # Setup
        options = ProcessingOptions(continue_on_errors=True)
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        
        # Make validation phase fail
        pipeline_service.validation.validate_entity.return_value = {
            'errors': ['Validation error 1', 'Validation error 2']
        }
        
        # Execute
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=options
        )
        
        # Verify - should complete despite validation errors
        execution = pipeline_service._executions[execution_id]
        assert execution.total_status == ProcessingStatus.COMPLETED
        assert len(execution.phase_results) == 5
        
        # Check validation phase had errors but pipeline continued
        validation_result = next(r for r in execution.phase_results 
                               if r.phase == ProcessingPhase.VALIDATION)
        assert validation_result.status == ProcessingStatus.FAILED
        assert len(validation_result.errors) > 0


class TestProcessingPhases:
    """Test individual processing phases"""
    
    def test_analysis_phase(self, pipeline_service, sample_csv_files, sample_config,
                           sample_analysis, processing_options):
        """Test analysis phase processing"""
        context = {}
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        
        result = pipeline_service._process_analysis_phase(
            context, sample_csv_files, sample_config, processing_options
        )
        
        assert result.phase == ProcessingPhase.ANALYSIS
        assert result.status == ProcessingStatus.COMPLETED
        assert result.input_count == len(sample_csv_files)
        assert result.output_count == len(sample_csv_files)
        assert 'datasets' in context
        assert len(context['datasets']) == len(sample_csv_files)
    
    def test_analysis_phase_with_errors(self, pipeline_service, sample_config, processing_options):
        """Test analysis phase with file errors"""
        context = {}
        bad_files = ['missing1.csv', 'missing2.csv']
        
        pipeline_service.table_analysis.analyze_csv.side_effect = FileNotFoundError("File not found")
        
        result = pipeline_service._process_analysis_phase(
            context, bad_files, sample_config, processing_options
        )
        
        assert result.status == ProcessingStatus.FAILED
        assert len(result.errors) == 2
        assert result.output_count == 0
    
    def test_entity_creation_phase(self, pipeline_service, sample_csv_files, sample_config,
                                  sample_analysis, processing_options):
        """Test entity creation phase"""
        # Setup context from analysis phase
        context = {
            'datasets': {
                sample_csv_files[0]: sample_analysis
            }
        }
        
        result = pipeline_service._process_entity_creation_phase(
            context, [sample_csv_files[0]], sample_config, processing_options
        )
        
        assert result.phase == ProcessingPhase.ENTITY_CREATION
        assert result.status == ProcessingStatus.COMPLETED
        assert result.input_count > 0
        assert result.output_count > 0
        assert 'entities' in context
    
    def test_relationship_mapping_phase(self, pipeline_service, sample_csv_files,
                                      sample_config, processing_options):
        """Test relationship mapping phase"""
        # Setup context with entities
        context = {
            'datasets': {
                sample_csv_files[1]: Mock(table_type='junction')
            },
            'entities': {
                sample_csv_files[0]: {
                    'person:1': {'id': 'person:1', 'type': 'Person', 'source_value': '1'},
                    'project:P001': {'id': 'project:P001', 'type': 'Project', 'source_value': 'P001'}
                }
            }
        }
        
        result = pipeline_service._process_relationship_mapping_phase(
            context, [sample_csv_files[1]], sample_config, processing_options
        )
        
        assert result.phase == ProcessingPhase.RELATIONSHIP_MAPPING
        assert result.status == ProcessingStatus.COMPLETED
        assert 'relationships' in context
    
    def test_validation_phase(self, pipeline_service, sample_config, processing_options):
        """Test validation phase"""
        # Setup context
        context = {
            'entities': {
                'file1': {
                    'entity1': {'id': 'entity1', 'type': 'Person'},
                    'entity2': {'id': 'entity2', 'type': 'Email'}
                }
            },
            'relationships': [
                {'source_entity': 'entity1', 'target_entity': 'entity2', 'predicate': 'hasEmail'}
            ]
        }
        
        pipeline_service.validation.validate_entity.return_value = {'errors': []}
        pipeline_service.validation.validate_relationship.return_value = {'errors': []}
        
        result = pipeline_service._process_validation_phase(
            context, [], sample_config, processing_options
        )
        
        assert result.phase == ProcessingPhase.VALIDATION
        assert result.status == ProcessingStatus.COMPLETED
        assert result.input_count == 3  # 2 entities + 1 relationship
        assert result.output_count == 3
        assert pipeline_service.validation.validate_entity.call_count == 2
        assert pipeline_service.validation.validate_relationship.call_count == 1
    
    def test_output_generation_phase(self, pipeline_service, sample_config, processing_options):
        """Test output generation phase"""
        # Setup context
        context = {
            'entities': {
                'file1': {
                    'person:alice': {
                        'id': 'person:alice',
                        'type': 'Person',
                        'source_value': 'Alice'
                    }
                }
            },
            'relationships': [
                {
                    'source_entity': 'person:alice',
                    'target_entity': 'project:p1',
                    'predicate': 'worksOn'
                }
            ]
        }
        
        result = pipeline_service._process_output_generation_phase(
            context, [], sample_config, processing_options
        )
        
        assert result.phase == ProcessingPhase.OUTPUT_GENERATION
        assert result.status == ProcessingStatus.COMPLETED
        assert result.output_count > 0
        assert 'output_triples' in context
        assert len(context['output_triples']) >= 3  # At least type, label, and relationship


class TestHelperMethods:
    """Test helper methods"""
    
    def test_rule_matches_column(self, pipeline_service):
        """Test rule matching logic"""
        # Prefix rule
        rule = {'pattern_type': 'prefix', 'pattern_value': 'user_'}
        assert pipeline_service._rule_matches_column(rule, 'id', 'user_123')
        assert not pipeline_service._rule_matches_column(rule, 'id', 'admin_123')
        
        # Suffix rule
        rule = {'pattern_type': 'suffix', 'pattern_value': '_id'}
        assert pipeline_service._rule_matches_column(rule, 'col', 'user_id')
        assert not pipeline_service._rule_matches_column(rule, 'col', 'user_name')
        
        # Contains rule
        rule = {'pattern_type': 'contains', 'pattern_value': '@'}
        assert pipeline_service._rule_matches_column(rule, 'email', 'test@example.com')
        assert not pipeline_service._rule_matches_column(rule, 'name', 'John Doe')
        
        # Column name rule
        rule = {'pattern_type': 'column_name', 'pattern_value': 'email'}
        assert pipeline_service._rule_matches_column(rule, 'email_address', 'any_value')
        assert not pipeline_service._rule_matches_column(rule, 'phone', 'any_value')
    
    def test_generate_entity_id(self, pipeline_service):
        """Test entity ID generation"""
        rule = {'id_prefix': 'person'}
        
        # Simple value
        assert pipeline_service._generate_entity_id('John Doe', rule) == 'person:John_Doe'
        
        # Value with special characters
        assert pipeline_service._generate_entity_id('user/admin', rule) == 'person:user_admin'
        
        # Default prefix
        rule_no_prefix = {}
        assert pipeline_service._generate_entity_id('test', rule_no_prefix) == 'entity:test'
    
    def test_find_applicable_relationship_templates(self, pipeline_service):
        """Test finding applicable relationship templates"""
        analysis = Mock(table_type='junction')
        
        templates = [
            {'id': 't1', 'table_type': 'entity'},
            {'id': 't2', 'table_type': 'junction'},
            {'id': 't3', 'handles_junction_tables': True},
            {'id': 't4', 'table_type': 'reference'}
        ]
        
        applicable = pipeline_service._find_applicable_relationship_templates(analysis, templates)
        
        assert len(applicable) == 2
        assert applicable[0]['id'] == 't2'
        assert applicable[1]['id'] == 't3'
    
    def test_generate_entity_triples(self, pipeline_service):
        """Test entity triple generation"""
        entity_data = {
            'id': 'person:alice',
            'type': 'Person',
            'source_value': 'Alice Smith'
        }
        
        triples = pipeline_service._generate_entity_triples(entity_data)
        
        assert len(triples) == 2
        assert ('person:alice', 'rdf:type', 'Person') in triples
        assert ('person:alice', 'rdfs:label', '"Alice Smith"') in triples
    
    def test_generate_relationship_triples(self, pipeline_service):
        """Test relationship triple generation"""
        relationship = {
            'source_entity': 'person:alice',
            'predicate': 'worksOn',
            'target_entity': 'project:p1'
        }
        
        triples = pipeline_service._generate_relationship_triples(relationship)
        
        assert len(triples) == 1
        assert ('person:alice', 'worksOn', 'project:p1') in triples
    
    def test_serialize_output(self, pipeline_service):
        """Test output serialization"""
        triples = [
            ('person:alice', 'rdf:type', 'Person'),
            ('person:alice', 'worksOn', 'project:p1')
        ]
        
        # Turtle format
        turtle_output = pipeline_service._serialize_output(triples, 'turtle')
        assert 'person:alice rdf:type Person .' in turtle_output
        assert 'person:alice worksOn project:p1 .' in turtle_output
        
        # N-Triples format
        ntriples_output = pipeline_service._serialize_output(triples, 'ntriples')
        assert '<person:alice> <rdf:type> <Person> .' in ntriples_output
        assert '<person:alice> <worksOn> <project:p1> .' in ntriples_output


class TestExecutionManagement:
    """Test execution management methods"""
    
    def test_get_execution_status(self, pipeline_service):
        """Test getting execution status"""
        # Create a mock execution
        execution = PipelineExecution(
            id='test-exec',
            configuration_id='test_config',
            start_time=time.time(),
            end_time=None,
            total_status=ProcessingStatus.RUNNING,
            phase_results=[
                ProcessingResult(
                    phase=ProcessingPhase.ANALYSIS,
                    status=ProcessingStatus.COMPLETED,
                    start_time=0,
                    end_time=1,
                    input_count=10,
                    output_count=10,
                    errors=[],
                    warnings=[],
                    metadata={}
                )
            ],
            input_datasets=['file1.csv'],
            output_location=None,
            summary={}
        )
        
        pipeline_service._executions['test-exec'] = execution
        
        status = pipeline_service.get_execution_status('test-exec')
        
        assert status is not None
        assert status['id'] == 'test-exec'
        assert status['status'] == 'running'
        assert status['current_phase'] == 'analysis'
        assert status['progress'] == 20  # 1 of 5 phases
    
    def test_get_execution_status_not_found(self, pipeline_service):
        """Test getting status of non-existent execution"""
        status = pipeline_service.get_execution_status('non-existent')
        assert status is None
    
    def test_get_execution_details(self, pipeline_service):
        """Test getting full execution details"""
        execution = Mock(id='test-exec')
        pipeline_service._executions['test-exec'] = execution
        
        details = pipeline_service.get_execution_details('test-exec')
        assert details == execution
    
    def test_list_executions(self, pipeline_service):
        """Test listing all executions"""
        # Add some executions
        for i in range(3):
            execution = PipelineExecution(
                id=f'exec-{i}',
                configuration_id='config',
                start_time=time.time(),
                end_time=time.time() + 10,
                total_status=ProcessingStatus.COMPLETED,
                phase_results=[],
                input_datasets=[f'file{i}.csv'],
                output_location=None,
                summary={}
            )
            pipeline_service._executions[f'exec-{i}'] = execution
        
        executions = pipeline_service.list_executions()
        
        assert len(executions) == 3
        assert all('id' in exec for exec in executions)
        assert all('status' in exec for exec in executions)
        assert all('datasets' in exec for exec in executions)


# Integration Tests
class TestIntegration:
    """Integration tests with multiple components"""
    
    def test_full_pipeline_execution(self, pipeline_service, sample_csv_files,
                                   sample_config, sample_analysis, processing_options):
        """Test complete pipeline execution end-to-end"""
        # Setup comprehensive mocks
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        pipeline_service.validation.validate_entity.return_value = {'errors': []}
        pipeline_service.validation.validate_relationship.return_value = {'errors': []}
        
        # Execute
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=processing_options
        )
        
        # Get results
        execution = pipeline_service.get_execution_details(execution_id)
        
        # Comprehensive verification
        assert execution.total_status == ProcessingStatus.COMPLETED
        assert len(execution.phase_results) == 5
        
        # Check each phase completed
        for phase in ProcessingPhase:
            phase_result = next((r for r in execution.phase_results if r.phase == phase), None)
            assert phase_result is not None
            assert phase_result.status in [ProcessingStatus.COMPLETED, ProcessingStatus.SKIPPED]
        
        # Check summary
        assert execution.summary['total_phases'] == 5
        assert execution.summary['successful_phases'] > 0
        assert execution.summary['datasets_processed'] == len(sample_csv_files)
    
    def test_dry_run_execution(self, pipeline_service, sample_csv_files,
                             sample_config, sample_analysis):
        """Test pipeline execution in dry run mode"""
        options = ProcessingOptions(dry_run=True)
        
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=options
        )
        
        execution = pipeline_service.get_execution_details(execution_id)
        
        # Should complete but not create actual entities
        assert execution.total_status == ProcessingStatus.COMPLETED
        
        # Check that dry run was respected
        entity_phase = next(r for r in execution.phase_results 
                          if r.phase == ProcessingPhase.ENTITY_CREATION)
        assert entity_phase.output_count > 0  # Counted potential entities


# Performance Tests
class TestPerformance:
    """Performance tests using time-based measurements"""
    
    def test_performance_single_phase(self, pipeline_service, sample_csv_files,
                                    sample_config, sample_analysis, processing_options):
        """Test single phase execution performance"""
        context = {}
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        
        start_time = time.time()
        result = pipeline_service._process_analysis_phase(
            context, sample_csv_files, sample_config, processing_options
        )
        execution_time = time.time() - start_time
        
        assert result.status == ProcessingStatus.COMPLETED
        assert execution_time < 5.0  # Should complete within 5 seconds
    
    def test_performance_full_pipeline(self, pipeline_service, sample_csv_files,
                                     sample_config, sample_analysis, processing_options):
        """Test full pipeline execution performance"""
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
        pipeline_service.validation.validate_entity.return_value = {'errors': []}
        pipeline_service.validation.validate_relationship.return_value = {'errors': []}
        
        start_time = time.time()
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=sample_csv_files,
            configuration_id='test_config',
            options=processing_options
        )
        execution_time = time.time() - start_time
        
        assert execution_id in pipeline_service._executions
        assert execution_time < 10.0  # Should complete within 10 seconds
    
    def test_performance_large_dataset_processing(self, pipeline_service,
                                                 sample_config, processing_options):
        """Test processing performance with larger datasets"""
        # Create moderately large dataset for performance testing
        large_data = {
            'id': list(range(1000)),  # Reduced size for CI environments
            'name': [f'Person{i}' for i in range(1000)],
            'email': [f'user{i}@example.com' for i in range(1000)]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df = pl.DataFrame(large_data)
            df.write_csv(f.name)
            large_file = f.name
        
        try:
            context = {
                'datasets': {
                    large_file: Mock(table_type='entity', row_count=1000)
                }
            }
            
            start_time = time.time()
            result = pipeline_service._process_entity_creation_phase(
                context, [large_file], sample_config, processing_options
            )
            execution_time = time.time() - start_time
            
            assert result.input_count == 1000
            assert execution_time < 15.0  # Should process 1000 records within 15 seconds
        finally:
            Path(large_file).unlink()


# Edge Cases and Error Handling
class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_dataset_list(self, pipeline_service, sample_config):
        """Test pipeline with empty dataset list"""
        pipeline_service.mapping_config.get_configuration.return_value = sample_config
        
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=[],
            configuration_id='test_config'
        )
        
        execution = pipeline_service.get_execution_details(execution_id)
        assert execution.total_status == ProcessingStatus.COMPLETED
        assert execution.summary['datasets_processed'] == 0
    
    def test_null_values_in_data(self, pipeline_service, sample_config, sample_analysis,
                                processing_options):
        """Test handling of null values"""
        # Create dataset with nulls
        data = {
            'id': [1, None, 3],
            'name': ['Alice', 'Bob', None],
            'email': [None, 'bob@example.com', 'charlie@example.com']
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df = pl.DataFrame(data)
            df.write_csv(f.name)
            null_file = f.name
        
        try:
            pipeline_service.mapping_config.get_configuration.return_value = sample_config
            pipeline_service.table_analysis.analyze_csv.return_value = sample_analysis
            pipeline_service.validation.validate_entity.return_value = {'errors': []}
            
            execution_id = pipeline_service.execute_pipeline(
                dataset_paths=[null_file],
                configuration_id='test_config',
                options=processing_options
            )
            
            execution = pipeline_service.get_execution_details(execution_id)
            assert execution.total_status == ProcessingStatus.COMPLETED
            
        finally:
            Path(null_file).unlink()
