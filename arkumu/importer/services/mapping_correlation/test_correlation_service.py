"""
Comprehensive unit tests for the MappingFileCorrelationService.

Tests the integration with MappingValidator and S3DirectDataAnalyzer,
as well as the exact matching logic for deterministic file-dataset correlation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from .correlation_service import MappingFileCorrelationService
from .data_models import (
    FileAnalysis, 
    MappingAnalysis, 
    DatasetCorrelation, 
    CorrelationResult
)
from .mapping_extractor import MappingExtractor
from .exact_matcher import ExactMatcher


class TestMappingFileCorrelationService:
    """Test suite for MappingFileCorrelationService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.organization_code = "test_org"
        self.service = MappingFileCorrelationService(self.organization_code)
        
        # Sample mapping configuration
        self.sample_mapping_config = {
            'id': 'test_mapping_1',
            'name': 'Test Mapping',
            'organization_id': 'test_org',
            'workspace_columns': {
                'col1': {
                    'name': 'id',
                    'type': 'integer',
                    'dataset': 'Person'
                },
                'col2': {
                    'name': 'name',
                    'type': 'string',
                    'dataset': 'Person'
                },
                'col3': {
                    'name': 'event_id',
                    'type': 'integer',
                    'dataset': 'Event'
                },
                'col4': {
                    'name': 'title',
                    'type': 'string',
                    'dataset': 'Event'
                }
            }
        }
        
        # Sample file paths
        self.sample_file_paths = [
            'metadata/Person.csv',
            'metadata/Event.csv',
            'metadata/UnknownFile.csv'
        ]
    
    def test_exact_file_dataset_match(self):
        """Test when CSV filename exactly matches dataset name."""
        # Mock the service's dependencies
        with patch.object(self.service.mapping_validator, 'validate_mapping_completeness') as mock_completeness:
            with patch.object(self.service.mapping_validator, 'validate_file_structure') as mock_file_structure:
                with patch.object(self.service.mapping_validator, 'validate_column_mappings') as mock_column_mappings:
                    with patch.object(self.service.mapping_validator, 'validate_data_types') as mock_data_types:
                        with patch.object(self.service.s3_analyzer, 'analyze_s3_dataset_completely') as mock_analyze:
                            
                            # Configure mocks
                            mock_completeness.return_value = {
                                'is_complete': True,
                                'missing_components': [],
                                'issues': []
                            }
                            mock_file_structure.return_value = []
                            mock_column_mappings.return_value = {
                                'mapped_columns': {'id': {}, 'name': {}},
                                'unmapped_columns': [],
                                'missing_required_columns': [],
                                'coverage_percentage': 100.0,
                                'issues': []
                            }
                            mock_data_types.return_value = []
                            
                            # Mock S3DirectDataAnalyzer response
                            mock_analysis = Mock()
                            mock_analysis.row_count = 100
                            mock_analysis.column_types = {'id': 'int64', 'name': 'object'}
                            mock_analysis.preview = Mock()
                            mock_analysis.preview.column_headers = ['id', 'name']
                            mock_analysis.preview.data_rows = [[1, 'John'], [2, 'Jane']]
                            mock_analyze.return_value = mock_analysis
                            
                            # Test correlation analysis
                            result = self.service.analyze_file_dataset_correlation(
                                file_paths=['metadata/Person.csv'],
                                mapping_config=self.sample_mapping_config
                            )
                            
                            # Assertions
                            assert isinstance(result, CorrelationResult)
                            assert len(result.dataset_correlations) == 1
                            
                            correlation = result.dataset_correlations[0]
                            assert correlation.is_exact_match is True
                            assert correlation.dataset_name == 'Person'
                            assert correlation.status == 'exact_match'
                            assert 'Person' in result.exactly_matched_datasets
                            assert len(result.missing_datasets) == 1  # Event dataset missing
                            assert result.has_all_required_datasets is False
                            assert len(result.unmatched_files) == 0
    
    def test_no_file_dataset_match(self):
        """Test when CSV filename does not match any dataset."""
        # Mock the service's dependencies
        with patch.object(self.service.mapping_validator, 'validate_mapping_completeness') as mock_completeness:
            with patch.object(self.service.mapping_validator, 'validate_file_structure') as mock_file_structure:
                with patch.object(self.service.s3_analyzer, 'analyze_s3_dataset_completely') as mock_analyze:
                    
                    # Configure mocks
                    mock_completeness.return_value = {
                        'is_complete': True,
                        'missing_components': [],
                        'issues': []
                    }
                    mock_file_structure.return_value = []
                    
                    # Mock S3DirectDataAnalyzer response
                    mock_analysis = Mock()
                    mock_analysis.row_count = 50
                    mock_analysis.column_types = {'unknown_col1': 'object', 'unknown_col2': 'object'}
                    mock_analysis.preview = Mock()
                    mock_analysis.preview.column_headers = ['unknown_col1', 'unknown_col2']
                    mock_analysis.preview.data_rows = []
                    mock_analyze.return_value = mock_analysis
                    
                    # Test correlation analysis with unmatched file
                    result = self.service.analyze_file_dataset_correlation(
                        file_paths=['metadata/UnknownFile.csv'],
                        mapping_config=self.sample_mapping_config
                    )
                    
                    # Assertions
                    assert len(result.dataset_correlations) == 1
                    
                    correlation = result.dataset_correlations[0]
                    assert correlation.is_exact_match is False
                    assert correlation.dataset_name == ''
                    assert correlation.status == 'no_match'
                    assert len(result.exactly_matched_datasets) == 0
                    assert len(result.missing_datasets) == 2  # Both Person and Event missing
                    assert 'metadata/UnknownFile.csv' in result.unmatched_files
                    assert result.has_all_required_datasets is False
                    assert result.has_no_extra_files is False
    
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.S3DirectDataAnalyzer')
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.MappingValidator')
    @patch('arkumu.importer.services.mapping_correlation.mapping_extractor.MappingValidator')
    def test_exact_column_matching(self, mock_extractor_validator, mock_validator, mock_analyzer):
        """Test exact column name matching between file and mapping."""
        # Mock MappingValidator responses with missing columns
        mock_validator.return_value.validate_mapping_completeness.return_value = {
            'is_complete': True,
            'missing_components': [],
            'issues': []
        }
        mock_validator.return_value.validate_file_structure.return_value = []
        mock_validator.return_value.validate_column_mappings.return_value = {
            'mapped_columns': {'id': {}},  # Only id is mapped
            'unmapped_columns': ['extra_column'],  # Extra column in file
            'missing_required_columns': ['name'],  # Missing required column
            'coverage_percentage': 50.0,
            'issues': []
        }
        mock_validator.return_value.validate_data_types.return_value = []
        
        # Mock static method in MappingExtractor
        mock_extractor_validator.validate_mapping_completeness.return_value = {
            'is_complete': True,
            'missing_components': [],
            'issues': []
        }
        
        # Mock S3DirectDataAnalyzer responses
        mock_analysis = Mock()
        mock_analysis.columns = ['id', 'extra_column']  # Missing 'name', has extra column
        mock_analysis.row_count = 100
        mock_analysis.column_types = {'id': 'int64', 'extra_column': 'object'}
        mock_analysis.sample_data = []
        
        mock_analyzer.return_value.analyze_s3_file.return_value = mock_analysis
        
        # Test correlation analysis
        result = self.service.analyze_file_dataset_correlation(
            file_paths=['metadata/Person.csv'],
            mapping_config=self.sample_mapping_config
        )
        
        # Assertions
        correlation = result.dataset_correlations[0]
        assert correlation.is_exact_match is True  # Filename match
        assert correlation.dataset_name == 'Person'
        assert 'id' in correlation.matched_columns
        assert 'name' in correlation.missing_columns
        assert 'extra_column' in correlation.extra_columns
        assert correlation.has_issues is True
    
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.S3DirectDataAnalyzer')
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.MappingValidator')
    @patch('arkumu.importer.services.mapping_correlation.mapping_extractor.MappingValidator')
    def test_missing_datasets_detection(self, mock_extractor_validator, mock_validator, mock_analyzer):
        """Test detection of required datasets with no matching files."""
        # Mock MappingValidator responses
        mock_validator.return_value.validate_mapping_completeness.return_value = {
            'is_complete': True,
            'missing_components': [],
            'issues': []
        }
        mock_validator.return_value.validate_file_structure.return_value = []
        mock_validator.return_value.validate_column_mappings.return_value = {
            'mapped_columns': {'id': {}, 'name': {}},
            'unmapped_columns': [],
            'missing_required_columns': [],
            'coverage_percentage': 100.0,
            'issues': []
        }
        mock_validator.return_value.validate_data_types.return_value = []
        
        # Mock S3DirectDataAnalyzer responses (only Person file, Event missing)
        mock_analysis = Mock()
        mock_analysis.columns = ['id', 'name']
        mock_analysis.row_count = 100
        mock_analysis.column_types = {'id': 'int64', 'name': 'object'}
        mock_analysis.sample_data = []
        
        mock_analyzer.return_value.analyze_s3_file.return_value = mock_analysis
        
        # Test with only Person file (Event dataset missing)
        result = self.service.analyze_file_dataset_correlation(
            file_paths=['metadata/Person.csv'],
            mapping_config=self.sample_mapping_config
        )
        
        # Assertions
        assert 'Event' in result.missing_datasets
        assert 'Person' in result.exactly_matched_datasets
        assert result.has_all_required_datasets is False
        assert len(result.recommendations) > 0
        
        # Check recommendations contain missing dataset info
        missing_recommendations = [r for r in result.recommendations if 'Event' in r]
        assert len(missing_recommendations) > 0
    
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.S3DirectDataAnalyzer')
    @patch('arkumu.importer.services.mapping_correlation.correlation_service.MappingValidator')
    def test_binary_ready_state(self, mock_validator, mock_analyzer):
        """Test binary ready state - all datasets matched and no extra files."""
        # Mock MappingValidator responses (perfect match)
        mock_validator.return_value.validate_mapping_completeness.return_value = {
            'is_complete': True,
            'missing_components': [],
            'issues': []
        }
        mock_validator.return_value.validate_file_structure.return_value = []
        mock_validator.return_value.validate_column_mappings.return_value = {
            'mapped_columns': {'id': {}, 'name': {}},
            'unmapped_columns': [],
            'missing_required_columns': [],
            'coverage_percentage': 100.0,
            'issues': []
        }
        mock_validator.return_value.validate_data_types.return_value = []
        
        # Mock S3DirectDataAnalyzer responses
        mock_analyzer.return_value.analyze_s3_file.side_effect = [
            self._create_mock_analysis(['id', 'name']),  # Person.csv
            self._create_mock_analysis(['event_id', 'title'])  # Event.csv
        ]
        
        # Test with both required files
        result = self.service.analyze_file_dataset_correlation(
            file_paths=['metadata/Person.csv', 'metadata/Event.csv'],
            mapping_config=self.sample_mapping_config
        )
        
        # Assertions
        assert result.has_all_required_datasets is True
        assert result.has_no_extra_files is True
        assert result.is_ready_for_execution is True
        assert len(result.missing_datasets) == 0
        assert len(result.unmatched_files) == 0
        assert set(result.exactly_matched_datasets) == {'Person', 'Event'}
    
    def test_mapping_extractor_integration(self):
        """Test integration with MappingExtractor helper class."""
        # Test dataset extraction
        datasets = MappingExtractor.extract_expected_datasets(self.sample_mapping_config)
        assert set(datasets) == {'Person', 'Event'}
        
        # Test columns per dataset extraction
        dataset_columns = MappingExtractor.extract_columns_per_dataset(self.sample_mapping_config)
        assert 'Person' in dataset_columns
        assert 'Event' in dataset_columns
        assert set(dataset_columns['Person']) == {'id', 'name'}
        assert set(dataset_columns['Event']) == {'event_id', 'title'}
    
    def test_exact_matcher_integration(self):
        """Test integration with ExactMatcher helper class."""
        expected_datasets = ['Person', 'Event']
        
        # Test exact filename matching
        match = ExactMatcher.match_filename_to_dataset('metadata/Person.csv', expected_datasets)
        assert match == 'Person'
        
        no_match = ExactMatcher.match_filename_to_dataset('metadata/Unknown.csv', expected_datasets)
        assert no_match is None
        
        # Test missing datasets detection
        matched_datasets = {'Person'}
        missing = ExactMatcher.find_missing_datasets(matched_datasets, expected_datasets)
        assert missing == ['Event']
        
        # Test unmatched files detection
        file_paths = ['metadata/Person.csv', 'metadata/Unknown.csv']
        unmatched = ExactMatcher.find_unmatched_files(file_paths, expected_datasets)
        assert 'metadata/Unknown.csv' in unmatched
        assert 'metadata/Person.csv' not in unmatched
    
    def test_invalid_mapping_configuration(self):
        """Test handling of invalid mapping configuration."""
        invalid_mapping = {'invalid': 'config'}
        
        with patch.object(self.service.mapping_validator, 'validate_mapping_completeness') as mock_validate:
            mock_validate.return_value = {
                'is_complete': False,
                'missing_components': ['workspace_columns'],
                'issues': []
            }
            
            result = self.service.analyze_file_dataset_correlation(
                file_paths=['metadata/Person.csv'],
                mapping_config=invalid_mapping
            )
            
            assert result.mapping_analysis is None
            assert result.has_all_required_datasets is False
            assert len(result.recommendations) > 0
    
    def test_file_analysis_error_handling(self):
        """Test error handling when file analysis fails."""
        with patch.object(self.service.mapping_validator, 'validate_mapping_completeness') as mock_validate:
            mock_validate.return_value = {
                'is_complete': True,
                'missing_components': [],
                'issues': []
            }
            
            with patch.object(self.service.mapping_validator, 'validate_file_structure') as mock_file_validate:
                mock_file_validate.return_value = [
                    {
                        'code': 'FILE_NOT_FOUND',
                        'severity': 'ERROR',
                        'message': 'File not found'
                    }
                ]
                
                result = self.service.analyze_file_dataset_correlation(
                    file_paths=['metadata/nonexistent.csv'],
                    mapping_config=self.sample_mapping_config
                )
                
                # Should handle errors gracefully
                assert len(result.file_analyses) == 0
                assert result.has_all_required_datasets is False
    
    def test_coverage_calculation(self):
        """Test coverage percentage calculations."""
        result = CorrelationResult(
            file_analyses=[],
            mapping_analysis=None,
            dataset_correlations=[
                DatasetCorrelation(
                    file_path='metadata/Person.csv',
                    dataset_name='Person',
                    is_exact_match=True,
                    matched_columns=['id', 'name'],
                    missing_columns=[],
                    extra_columns=['extra'],
                    type_mismatches=[],
                    status='exact_match'
                )
            ],
            exactly_matched_datasets=['Person'],
            missing_datasets=[],
            unmatched_files=[],
            has_all_required_datasets=True,
            has_no_extra_files=True
        )
        
        # Test individual correlation coverage
        correlation = result.dataset_correlations[0]
        expected_coverage = (2 / 3) * 100  # 2 matched out of 3 total columns
        assert abs(correlation.coverage_percentage - expected_coverage) < 0.1
        
        # Test overall coverage
        assert result.overall_coverage_percentage == expected_coverage
    
    def _create_mock_analysis(self, columns):
        """Helper method to create mock S3 analysis results."""
        mock_analysis = Mock()
        mock_analysis.columns = columns
        mock_analysis.row_count = 100
        mock_analysis.column_types = {col: 'object' for col in columns}
        mock_analysis.sample_data = []
        return mock_analysis


class TestDataModels:
    """Test suite for data models used by the correlation service."""
    
    def test_file_analysis_post_init(self):
        """Test FileAnalysis post-initialization."""
        file_analysis = FileAnalysis(
            file_path='metadata/test.csv',
            file_name='',  # Should be auto-populated
            column_count=3,
            row_count=100,
            columns=['col1', 'col2', 'col3'],
            column_types={'col1': 'int', 'col2': 'str', 'col3': 'float'}
        )
        
        assert file_analysis.file_name == 'test'
    
    def test_dataset_correlation_properties(self):
        """Test DatasetCorrelation computed properties."""
        correlation = DatasetCorrelation(
            file_path='metadata/Person.csv',
            dataset_name='Person',
            is_exact_match=True,
            matched_columns=['id', 'name'],
            missing_columns=['email'],
            extra_columns=['extra'],
            type_mismatches=[{'column': 'id', 'expected': 'int', 'actual': 'str'}],
            status='exact_match'
        )
        
        assert correlation.has_issues is True  # Has missing columns and type mismatches
        # Coverage = matched / (matched + extra) = 2 / (2 + 1) = 66.67%
        assert abs(correlation.coverage_percentage - 66.67) < 0.1
    
    def test_correlation_result_properties(self):
        """Test CorrelationResult computed properties."""
        correlation_with_issues = DatasetCorrelation(
            file_path='metadata/Person.csv',
            dataset_name='Person',
            is_exact_match=True,
            matched_columns=['id'],
            missing_columns=['name', 'email'],
            extra_columns=[],
            type_mismatches=[{'mismatch': 'test'}],
            status='exact_match'
        )
        
        result = CorrelationResult(
            file_analyses=[],
            mapping_analysis=None,
            dataset_correlations=[correlation_with_issues],
            exactly_matched_datasets=['Person'],
            missing_datasets=['Event'],
            unmatched_files=['metadata/unknown.csv'],
            has_all_required_datasets=False,
            has_no_extra_files=False
        )
        
        assert result.is_ready_for_execution is False
        assert result.total_issues_count == 5  # 2 missing columns + 1 type mismatch + 1 missing dataset + 1 unmatched file


@pytest.mark.django_db
class TestCorrelationServiceIntegration:
    """Integration tests for the correlation service."""
    
    def test_real_mapping_validator_integration(self):
        """Test with real MappingValidator instance."""
        from arkumu.importer.services.mapping_validation.validator import MappingValidator
        
        validator = MappingValidator()
        
        # Test with valid mapping config
        mapping_config = {
            'workspace_columns': {
                'col1': {'name': 'id', 'dataset': 'Person', 'type': 'integer'}
            },
            'organization_id': 'test_org'
        }
        
        completeness_result = validator.validate_mapping_completeness(mapping_config)
        assert completeness_result['is_complete'] is True
        
        # Test column mappings
        file_columns = ['id', 'name', 'extra']
        column_result = validator.validate_column_mappings(mapping_config['workspace_columns'], file_columns)
        
        assert 'id' in column_result['mapped_columns']
        assert 'name' in column_result['unmapped_columns']
        assert 'extra' in column_result['unmapped_columns']