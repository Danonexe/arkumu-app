"""
Comprehensive GUI simulation tests for pre-execution validation service.

This test suite simulates the complete user workflow as it would happen in the GUI:
1. User selects organization (fuk)
2. User browses and selects files from S3
3. User chooses a mapping (fuk-test)
4. User clicks validate button
5. User receives validation results and acts on them

These tests mirror the real user experience and ensure the entire validation
pipeline works correctly end-to-end with proper error handling and state management.
"""

import pytest
import json
import os
import io
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, List, Any
import logging

# Django imports
from django.test import RequestFactory, TestCase
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import JsonResponse, QueryDict

# Moto for S3 mocking
import boto3
from moto import mock_aws

# Arkumu imports
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping
from arkumu.importer.views.ingest_views import (
    IngestDataView, 
    run_pre_execution_validation,
    get_organization_files_for_ingest,
    toggle_file_selection,
    select_all_files,
    SELECTED_FILES_SESSION_KEY
)
from arkumu.importer.services.pre_execution_validation.pre_execution_validator import PreExecutionValidator
from arkumu.importer.services.pre_execution_validation.validation_result import (
    PreExecutionValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationCategory,
    ValidationMode,
    ValidationErrorCodes,
    FileValidationResult,
    ColumnMappingValidationResult,
    RelationshipValidationResult,
    ResourceEstimate
)
from arkumu.storage.services.bucket_service import BucketService

User = get_user_model()
logger = logging.getLogger(__name__)


class TestGUISimulationE2E:
    """
    End-to-end GUI simulation tests that test the complete validation workflow.
    
    These tests simulate the exact user interactions and verify that the entire
    validation pipeline works correctly from start to finish.
    """
    
    @pytest.fixture
    def user(self):
        """Create a test user"""
        username = f'testuser_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'
        return User.objects.create_user(
            username=username,
            email='test@example.com',
            password='testpass123'
        )
    
    @pytest.fixture
    def fuk_organization(self):
        """Get or create FUK organization"""
        try:
            return Organization.objects.get(code='fuk')
        except Organization.DoesNotExist:
            return Organization.objects.create(
                code='fuk',
                name='Folkwang Universität der Künste',
                domain='folkwang-uni.de'
            )
    
    @pytest.fixture
    def fuk_test_mapping(self, fuk_organization):
        """Get or create the real fuk-test mapping"""
        try:
            return Mapping.objects.get(name='fuk-test', organization_id=fuk_organization.code)
        except Mapping.DoesNotExist:
            # Create a comprehensive mapping for testing
            mapping_config = {
                'institution': 'fuk',
                'domain': 'http://folkwang-uni.de/',
                'anchor_column': 'id',
                'column_delimiter': ',',
                'workspace_columns': {
                    'AkteurIn': [
                        {'name': 'id', 'type': 'anchor'},
                        {'name': 'name', 'type': 'regular'},
                        {'name': 'email', 'type': 'regular'},
                        {'name': 'phone', 'type': 'regular'}
                    ],
                    'Ereignis': [
                        {'name': 'id', 'type': 'anchor'},
                        {'name': 'title', 'type': 'regular'},
                        {'name': 'date', 'type': 'regular'},
                        {'name': 'akteur_id', 'type': 'foreign_key'}
                    ],
                    'Projekt': [
                        {'name': 'id', 'type': 'anchor'},
                        {'name': 'name', 'type': 'regular'},
                        {'name': 'description', 'type': 'regular'},
                        {'name': 'start_date', 'type': 'regular'}
                    ]
                },
                'mappings': [
                    {
                        'source_column': 'id',
                        'property': 'fuk:id',
                        'range': 'xsd:string'
                    },
                    {
                        'source_column': 'name',
                        'property': 'fuk:name',
                        'range': 'xsd:string'
                    },
                    {
                        'source_column': 'email',
                        'property': 'fuk:email',
                        'range': 'xsd:string'
                    },
                    {
                        'source_column': 'akteur_id',
                        'property': 'fuk:relatedTo',
                        'object_column': 'AkteurIn',
                        'range': 'fuk:AkteurIn'
                    }
                ],
                'fk_relationships': [
                    {
                        'source_table': 'Ereignis',
                        'source_column': 'akteur_id',
                        'target_table': 'AkteurIn',
                        'target_column': 'id'
                    }
                ],
                'external_ontologies': []
            }
            
            return Mapping.objects.create(
                name='fuk-test',
                organization_id=fuk_organization.code,
                mapping_config=mapping_config,
                created_by=None,
                source_datasets=['AkteurIn', 'Ereignis', 'Projekt']
            )
    
    @pytest.fixture
    def request_factory(self):
        """Create request factory for testing"""
        return RequestFactory()
    
    @pytest.fixture
    def authenticated_request(self, request_factory, user):
        """Create an authenticated request with session"""
        request = request_factory.get('/')
        request.user = user
        
        # Add session middleware
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        return request
    
    @pytest.fixture
    def mock_s3_files(self):
        """Mock S3 files for testing with various scenarios"""
        return {
            'metadata/AkteurIn.csv': {
                'content': 'id,name,email,phone\n1,John Doe,john@example.com,555-1234\n2,Jane Smith,jane@example.com,555-5678\n3,Bob Johnson,bob@example.com,555-9012',
                'size': 128
            },
            'metadata/Ereignis.csv': {
                'content': 'id,title,date,akteur_id\n1,Concert,2024-01-15,1\n2,Exhibition,2024-02-20,2\n3,Workshop,2024-03-10,1',
                'size': 98
            },
            'metadata/Projekt.csv': {
                'content': 'id,name,description,start_date\n1,Project Alpha,First project,2024-01-01\n2,Project Beta,Second project,2024-02-01',
                'size': 95
            },
            'metadata/EmptyFile.csv': {
                'content': '',
                'size': 0
            },
            'metadata/MalformedFile.csv': {
                'content': 'id,name,email\n1,John Doe,john@example.com\n2,Jane Smith  # Missing closing quote and comma',
                'size': 78
            },
            'metadata/MissingColumns.csv': {
                'content': 'id,name\n1,John Doe\n2,Jane Smith',
                'size': 32
            },
            'metadata/LargeFile.csv': {
                'content': 'id,name,email\n' + '\n'.join([f'{i},User{i},user{i}@example.com' for i in range(1, 10001)]),
                'size': 500 * 1024 * 1024  # 500MB simulated
            }
        }
    
    @pytest.fixture
    def mock_s3_bucket(self, mock_s3_files):
        """Set up mocked S3 bucket with test files"""
        with mock_aws():
            # Create S3 client
            s3_client = boto3.client('s3', region_name='us-east-1')
            
            # Create bucket
            bucket_name = 'arkumu-fuk-test'
            s3_client.create_bucket(Bucket=bucket_name)
            
            # Upload test files
            for file_path, file_data in mock_s3_files.items():
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_path,
                    Body=file_data['content'],
                    ContentLength=file_data['size']
                )
            
            yield bucket_name
    
    @pytest.mark.django_db
    def test_successful_end_to_end_validation_workflow(self, authenticated_request, fuk_organization, 
                                                       fuk_test_mapping, mock_s3_bucket):
        """
        Test the complete successful validation workflow from start to finish:
        1. User selects organization
        2. User browses and selects files  
        3. User chooses mapping
        4. User runs validation
        5. User receives successful results
        """
        # Step 1: User selects organization
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        
        # Verify organization is set
        current_org = view.get_current_organization(authenticated_request)
        assert current_org is not None
        assert current_org['code'] == fuk_organization.code
        
        # Step 2: User browses files
        with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
            mock_service = Mock()
            mock_bucket_service.return_value = mock_service
            mock_service.get_organization_bucket.return_value = mock_s3_bucket
            
            # Mock file listing
            mock_files = [
                {'type': 'file', 'name': 'AkteurIn.csv', 'path': 'metadata/AkteurIn.csv', 'size': 128},
                {'type': 'file', 'name': 'Ereignis.csv', 'path': 'metadata/Ereignis.csv', 'size': 98},
                {'type': 'file', 'name': 'Projekt.csv', 'path': 'metadata/Projekt.csv', 'size': 95}
            ]
            mock_service.list_bucket_contents.return_value = mock_files
            
            # User browses files
            get_request = authenticated_request
            get_request.method = 'GET'
            get_request.GET = QueryDict(f'organization={fuk_organization.code}')
            
            response = get_organization_files_for_ingest(get_request)
            assert response.status_code == 200
        
        # Step 3: User selects files
        selected_files = ['metadata/AkteurIn.csv', 'metadata/Ereignis.csv', 'metadata/Projekt.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Verify files are selected
        assert authenticated_request.session[SELECTED_FILES_SESSION_KEY] == selected_files
        
        # Step 4: User chooses mapping
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Verify mapping is set
        current_mapping = view.get_current_mapping(authenticated_request)
        assert current_mapping is not None
        assert current_mapping['id'] == fuk_test_mapping.id
        
        # Step 5: User runs validation
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            # Mock successful validation result
            mock_validation_result = PreExecutionValidationResult(
                is_valid=True,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.95
            )
            
            # Add file validation results
            for file_path in selected_files:
                file_result = FileValidationResult(
                    file_path=file_path,
                    is_valid=True,
                    file_size=128,
                    column_count=4,
                    row_count=3,
                    encoding='utf-8',
                    delimiter=','
                )
                mock_validation_result.file_validation_results.append(file_result)
            
            # Add column mapping result
            mock_validation_result.column_mapping_result = ColumnMappingValidationResult(
                mapped_columns={'id': 'fuk:id', 'name': 'fuk:name', 'email': 'fuk:email'},
                unmapped_columns=['phone'],
                missing_required_columns=[],
                type_mismatches=[],
                transformation_warnings=[],
                coverage_percentage=85.0
            )
            
            # Add relationship validation result
            mock_validation_result.relationship_validation_result = RelationshipValidationResult(
                valid_relationships=['Ereignis.akteur_id -> AkteurIn.id'],
                invalid_relationships=[],
                missing_dependencies=[],
                circular_dependencies=[],
                foreign_key_issues=[],
                orphaned_records_estimate=0
            )
            
            # Add resource estimate
            mock_validation_result.resource_estimate = ResourceEstimate(
                estimated_execution_time=45.0,
                estimated_memory_usage=256,
                estimated_disk_usage=512,
                estimated_cpu_usage=30.0,
                complexity_score=4,
                parallel_processing_recommendation=False
            )
            
            # Add some info issues
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.UNMAPPED_REQUIRED_COLUMN,
                severity=ValidationSeverity.INFO,
                category=ValidationCategory.COLUMN_MAPPING,
                message="Column 'phone' is not mapped but may contain useful data",
                column_name='phone'
            ))
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock bucket service for validation
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service_val:
                mock_bucket_service_val.return_value.get_organization_bucket.return_value = mock_s3_bucket
                
                # Mock mapping adapter
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Create validation request
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is True
                    # Note: confidence gets recalculated due to __post_init__ with INFO issues
                    assert response_data['validation_results']['overall_confidence'] > 0.9
                    assert response_data['mapping_id'] == str(fuk_test_mapping.id)
                    assert response_data['organization_code'] == fuk_organization.code
                    assert response_data['files_validated'] == 3
                    
                    # Verify validation results stored in session
                    validation_session_key = f'validation_results_{fuk_organization.code}'
                    assert validation_session_key in authenticated_request.session
                    stored_results = authenticated_request.session[validation_session_key]
                    assert stored_results['is_valid'] is True
                    assert stored_results['overall_confidence'] > 0.9
                    
                    # Verify validation was called with correct parameters
                    mock_validator_instance.validate_mapping_execution.assert_called_once()
                    call_args = mock_validator_instance.validate_mapping_execution.call_args
                    assert call_args[1]['file_paths'] == selected_files
                    assert call_args[1]['organization_code'] == fuk_organization.code
    
    @pytest.mark.django_db
    def test_validation_with_missing_files_error_handling(self, authenticated_request, fuk_organization, 
                                                          fuk_test_mapping):
        """
        Test validation workflow when some files don't exist - error handling
        """
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select files including non-existent ones
        selected_files = [
            'metadata/AkteurIn.csv',
            'metadata/NonExistentFile.csv',
            'metadata/Ereignis.csv',
            'metadata/AnotherMissingFile.csv'
        ]
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with missing file errors
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.2
            )
            
            # Add missing file errors
            for missing_file in ['metadata/NonExistentFile.csv', 'metadata/AnotherMissingFile.csv']:
                mock_validation_result.add_issue(ValidationIssue(
                    code=ValidationErrorCodes.FILE_NOT_FOUND,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"File not found in S3 bucket: {missing_file}",
                    file_path=missing_file,
                    suggested_fix="Ensure the file exists in the S3 bucket or remove it from selection"
                ))
            
            # Add file validation results for existing files
            for existing_file in ['metadata/AkteurIn.csv', 'metadata/Ereignis.csv']:
                file_result = FileValidationResult(
                    file_path=existing_file,
                    is_valid=True,
                    file_size=128,
                    column_count=4,
                    row_count=3
                )
                mock_validation_result.file_validation_results.append(file_result)
            
            # Add failed file validation results for missing files
            for missing_file in ['metadata/NonExistentFile.csv', 'metadata/AnotherMissingFile.csv']:
                file_result = FileValidationResult(
                    file_path=missing_file,
                    is_valid=False,
                    file_size=0,
                    column_count=0,
                    row_count=0
                )
                file_result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.FILE_NOT_FOUND,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"File not found: {missing_file}",
                    file_path=missing_file
                ))
                mock_validation_result.file_validation_results.append(file_result)
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is False
                    assert len(response_data['validation_results']['errors']) == 2
                    
                    # Check specific error messages
                    errors = response_data['validation_results']['errors']
                    error_codes = [error['code'] for error in errors]
                    assert all(code == ValidationErrorCodes.FILE_NOT_FOUND for code in error_codes)
                    
                    # Check that missing files are mentioned
                    error_file_paths = [error['file_path'] for error in errors]
                    assert 'metadata/NonExistentFile.csv' in error_file_paths
                    assert 'metadata/AnotherMissingFile.csv' in error_file_paths
                    
                    # Verify confidence is low
                    assert response_data['validation_results']['overall_confidence'] < 0.5
    
    @pytest.mark.django_db
    def test_validation_with_empty_files_warning(self, authenticated_request, fuk_organization, 
                                                fuk_test_mapping):
        """
        Test validation workflow with empty files - should produce warnings
        """
        # Setup
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select files including empty ones
        selected_files = ['metadata/AkteurIn.csv', 'metadata/EmptyFile.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with empty file warnings
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=True,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.7
            )
            
            # Add empty file warning
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.FILE_EMPTY,
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.FILE_STRUCTURE,
                message="File is empty or has no data rows",
                file_path="metadata/EmptyFile.csv",
                suggested_fix="Ensure the file contains valid data or remove it from selection"
            ))
            
            # Add file validation results
            valid_file_result = FileValidationResult(
                file_path='metadata/AkteurIn.csv',
                is_valid=True,
                file_size=128,
                column_count=4,
                row_count=3
            )
            mock_validation_result.file_validation_results.append(valid_file_result)
            
            empty_file_result = FileValidationResult(
                file_path='metadata/EmptyFile.csv',
                is_valid=False,
                file_size=0,
                column_count=0,
                row_count=0
            )
            empty_file_result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.FILE_EMPTY,
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.FILE_STRUCTURE,
                message="File is empty",
                file_path="metadata/EmptyFile.csv"
            ))
            mock_validation_result.file_validation_results.append(empty_file_result)
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is True
                    assert len(response_data['validation_results']['warnings']) == 1
                    
                    # Check warning details
                    warning = response_data['validation_results']['warnings'][0]
                    assert warning['code'] == ValidationErrorCodes.FILE_EMPTY
                    assert 'EmptyFile.csv' in warning['file_path']
                    assert warning['severity'] == 'warning'
                    assert warning['suggested_fix'] is not None
    
    @pytest.mark.django_db
    def test_validation_with_malformed_csv_error(self, authenticated_request, fuk_organization, 
                                                fuk_test_mapping):
        """
        Test validation workflow with malformed CSV files
        """
        # Setup
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select malformed file
        selected_files = ['metadata/MalformedFile.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with CSV parsing errors
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.1
            )
            
            # Add CSV parsing error
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.MALFORMED_CSV,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message="CSV file has malformed structure at line 3",
                file_path="metadata/MalformedFile.csv",
                line_number=3,
                details={'error': 'Unexpected end of data', 'column_count_expected': 3, 'column_count_actual': 2},
                suggested_fix="Fix CSV structure and ensure proper escaping of quotes and commas"
            ))
            
            # Add file validation result
            malformed_file_result = FileValidationResult(
                file_path='metadata/MalformedFile.csv',
                is_valid=False,
                file_size=78,
                column_count=3,
                row_count=2
            )
            malformed_file_result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.MALFORMED_CSV,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message="CSV parsing error at line 3",
                file_path="metadata/MalformedFile.csv",
                line_number=3
            ))
            mock_validation_result.file_validation_results.append(malformed_file_result)
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is False
                    assert len(response_data['validation_results']['errors']) == 1
                    
                    # Check error details
                    error = response_data['validation_results']['errors'][0]
                    assert error['code'] == ValidationErrorCodes.MALFORMED_CSV
                    assert error['line_number'] == 3
                    assert 'malformed structure' in error['message']
                    assert 'Fix CSV structure' in error['suggested_fix']
                    
                    # Verify confidence is low (gets recalculated in __post_init__)
                    assert response_data['validation_results']['overall_confidence'] < 0.8
    
    @pytest.mark.django_db
    def test_validation_with_column_mapping_issues(self, authenticated_request, fuk_organization, 
                                                  fuk_test_mapping):
        """
        Test validation workflow with column mapping issues
        """
        # Setup
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select file with missing columns
        selected_files = ['metadata/MissingColumns.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with column mapping issues
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.4
            )
            
            # Add column mapping errors
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message="Required column 'email' is missing from the file",
                file_path="metadata/MissingColumns.csv",
                column_name="email",
                suggested_fix="Add the 'email' column to the data file or update the mapping configuration"
            ))
            
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message="Required column 'phone' is missing from the file",
                file_path="metadata/MissingColumns.csv",
                column_name="phone",
                suggested_fix="Add the 'phone' column to the data file or update the mapping configuration"
            ))
            
            # Add file validation result
            file_result = FileValidationResult(
                file_path='metadata/MissingColumns.csv',
                is_valid=True,
                file_size=32,
                column_count=2,
                row_count=2,
                missing_columns=['email', 'phone']
            )
            mock_validation_result.file_validation_results.append(file_result)
            
            # Add column mapping result
            mock_validation_result.column_mapping_result = ColumnMappingValidationResult(
                mapped_columns={'id': 'fuk:id', 'name': 'fuk:name'},
                unmapped_columns=[],
                missing_required_columns=['email', 'phone'],
                type_mismatches=[],
                transformation_warnings=[],
                coverage_percentage=50.0
            )
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is False
                    assert len(response_data['validation_results']['errors']) == 2
                    
                    # Check column mapping results
                    column_mapping = response_data['validation_results']['column_mapping_result']
                    assert column_mapping['coverage_percentage'] == 50.0
                    assert len(column_mapping['missing_required_columns']) == 2
                    assert 'email' in column_mapping['missing_required_columns']
                    assert 'phone' in column_mapping['missing_required_columns']
                    
                    # Check error details
                    errors = response_data['validation_results']['errors']
                    error_codes = [error['code'] for error in errors]
                    assert all(code == ValidationErrorCodes.REQUIRED_COLUMN_MISSING for code in error_codes)
                    
                    missing_columns = [error['column_name'] for error in errors]
                    assert 'email' in missing_columns
                    assert 'phone' in missing_columns
    
    @pytest.mark.django_db
    def test_validation_with_large_file_performance_warnings(self, authenticated_request, fuk_organization, 
                                                           fuk_test_mapping):
        """
        Test validation workflow with large files that trigger performance warnings
        """
        # Setup
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select large file
        selected_files = ['metadata/LargeFile.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with performance warnings
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=True,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.9
            )
            
            # Add performance warnings
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.FILE_TOO_LARGE,
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.FILE_STRUCTURE,
                message="File is very large (500.0MB) and may impact performance",
                file_path="metadata/LargeFile.csv",
                details={'file_size_mb': 500.0, 'row_count': 10000},
                suggested_fix="Consider splitting the file into smaller chunks or processing during off-peak hours"
            ))
            
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.LONG_EXECUTION_TIME,
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.RESOURCE_ESTIMATION,
                message="Processing is estimated to take 15 minutes",
                details={'estimated_minutes': 15},
                suggested_fix="Consider running during off-peak hours or using parallel processing"
            ))
            
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.HIGH_MEMORY_USAGE,
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.RESOURCE_ESTIMATION,
                message="High memory usage expected (2GB)",
                details={'estimated_memory_gb': 2},
                suggested_fix="Ensure sufficient system memory is available"
            ))
            
            # Add file validation result
            large_file_result = FileValidationResult(
                file_path='metadata/LargeFile.csv',
                is_valid=True,
                file_size=500 * 1024 * 1024,  # 500MB
                column_count=3,
                row_count=10000
            )
            mock_validation_result.file_validation_results.append(large_file_result)
            
            # Add resource estimate
            mock_validation_result.resource_estimate = ResourceEstimate(
                estimated_execution_time=900,  # 15 minutes
                estimated_memory_usage=2048,   # 2GB
                estimated_disk_usage=1024,     # 1GB
                estimated_cpu_usage=80.0,
                complexity_score=8,
                parallel_processing_recommendation=True,
                chunking_recommendation={'recommended': True, 'chunk_size': 1000}
            )
            
            # Add execution recommendations
            mock_validation_result.execution_recommendations = [
                "Consider chunked processing for large files",
                "High memory usage expected - monitor system resources",
                "Long execution time expected - consider running during off-peak hours",
                "Parallel processing recommended for better performance"
            ]
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is True
                    assert len(response_data['validation_results']['warnings']) == 3
                    
                    # Check resource estimate
                    resource_data = response_data['validation_results']['resource_estimate']
                    assert resource_data['estimated_execution_time'] == 900
                    assert resource_data['estimated_memory_usage'] == 2048
                    assert resource_data['complexity_score'] == 8
                    assert resource_data['parallel_processing_recommendation'] is True
                    assert resource_data['chunking_recommendation']['recommended'] is True
                    
                    # Check execution recommendations
                    recommendations = response_data['validation_results']['execution_recommendations']
                    assert len(recommendations) == 4
                    assert any('chunked processing' in rec for rec in recommendations)
                    assert any('High memory usage' in rec for rec in recommendations)
                    assert any('Long execution time' in rec for rec in recommendations)
                    assert any('Parallel processing' in rec for rec in recommendations)
                    
                    # Check specific warning codes
                    warnings = response_data['validation_results']['warnings']
                    warning_codes = [w['code'] for w in warnings]
                    assert ValidationErrorCodes.FILE_TOO_LARGE in warning_codes
                    assert ValidationErrorCodes.LONG_EXECUTION_TIME in warning_codes
                    assert ValidationErrorCodes.HIGH_MEMORY_USAGE in warning_codes
    
    @pytest.mark.django_db
    def test_validation_with_relationship_errors(self, authenticated_request, fuk_organization, 
                                               fuk_test_mapping):
        """
        Test validation workflow with relationship validation errors
        """
        # Setup
        view = IngestDataView()
        view.set_current_organization(authenticated_request, fuk_organization.code)
        view.set_current_mapping(authenticated_request, fuk_test_mapping.id, 
                                fuk_test_mapping.name, fuk_organization.id)
        
        # Select files
        selected_files = ['metadata/AkteurIn.csv', 'metadata/Ereignis.csv']
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = selected_files
        
        # Mock validation with relationship errors
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.6
            )
            
            # Add relationship validation errors
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.MISSING_FOREIGN_KEY,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.RELATIONSHIP_VALIDATION,
                message="Foreign key column 'akteur_id' in Ereignis has missing references",
                details={'missing_references': ['99', '100'], 'valid_references': ['1', '2']},
                suggested_fix="Ensure all referenced IDs exist in the AkteurIn table"
            ))
            
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.CIRCULAR_DEPENDENCY,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.RELATIONSHIP_VALIDATION,
                message="Circular dependency detected in relationship chain",
                details={'cycle': ['AkteurIn', 'Ereignis', 'Projekt', 'AkteurIn']},
                suggested_fix="Review and break the circular dependency"
            ))
            
            # Add file validation results
            for file_path in selected_files:
                file_result = FileValidationResult(
                    file_path=file_path,
                    is_valid=True,
                    file_size=128,
                    column_count=4,
                    row_count=3
                )
                mock_validation_result.file_validation_results.append(file_result)
            
            # Add relationship validation result
            mock_validation_result.relationship_validation_result = RelationshipValidationResult(
                valid_relationships=['Ereignis.akteur_id -> AkteurIn.id'],
                invalid_relationships=['Projekt.akteur_id -> AkteurIn.id'],
                missing_dependencies=['AkteurIn.projekt_id -> Projekt.id'],
                circular_dependencies=[['AkteurIn', 'Ereignis', 'Projekt', 'AkteurIn']],
                foreign_key_issues=[
                    {'table': 'Ereignis', 'column': 'akteur_id', 'missing_refs': ['99', '100']}
                ],
                orphaned_records_estimate=2
            )
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = fuk_test_mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is False
                    assert len(response_data['validation_results']['errors']) == 2
                    
                    # Check relationship validation results
                    relationship_result = response_data['validation_results']['relationship_validation_result']
                    assert len(relationship_result['valid_relationships']) == 1
                    assert len(relationship_result['invalid_relationships']) == 1
                    assert len(relationship_result['circular_dependencies']) == 1
                    assert relationship_result['orphaned_records_estimate'] == 2
                    
                    # Check error details
                    errors = response_data['validation_results']['errors']
                    error_codes = [error['code'] for error in errors]
                    assert ValidationErrorCodes.MISSING_FOREIGN_KEY in error_codes
                    assert ValidationErrorCodes.CIRCULAR_DEPENDENCY in error_codes
                    
                    # Check error details
                    fk_error = next(e for e in errors if e['code'] == ValidationErrorCodes.MISSING_FOREIGN_KEY)
                    assert 'akteur_id' in fk_error['message']
                    assert 'missing_references' in fk_error['details']
                    
                    circular_error = next(e for e in errors if e['code'] == ValidationErrorCodes.CIRCULAR_DEPENDENCY)
                    assert 'Circular dependency' in circular_error['message']
                    assert 'cycle' in circular_error['details']


class TestValidationEdgeCases:
    """Test edge cases and error conditions in validation flow"""
    
    @pytest.fixture
    def user(self):
        """Create a test user"""
        username = f'testuser_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'
        return User.objects.create_user(
            username=username,
            email='test@example.com',
            password='testpass123'
        )
    
    @pytest.fixture
    def authenticated_request(self, user):
        """Create an authenticated request with session"""
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        
        # Add session middleware
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        return request
    
    @pytest.mark.django_db
    def test_validation_without_organization_selected(self, authenticated_request):
        """
        Test validation flow when no organization is selected
        """
        # Don't set organization in session
        
        # Select some files (shouldn't matter)
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Run validation
        post_request = authenticated_request
        post_request.method = 'POST'
        post_request.POST = QueryDict()
        
        response = run_pre_execution_validation(post_request)
        
        # Verify response
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert response_data['success'] is False
        assert 'No organization selected' in response_data['error']
    
    @pytest.mark.django_db
    def test_validation_without_mapping_selected(self, authenticated_request):
        """
        Test validation flow when no mapping is selected
        """
        # Create minimal organization
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        # Setup organization but don't select mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        
        # Select files
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Run validation
        post_request = authenticated_request
        post_request.method = 'POST'
        post_request.POST = QueryDict()
        
        response = run_pre_execution_validation(post_request)
        
        # Verify response
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert response_data['success'] is False
        assert 'No mapping selected' in response_data['error']
    
    @pytest.mark.django_db
    def test_validation_without_files_selected(self, authenticated_request):
        """
        Test validation flow when no files are selected
        """
        # Create minimal organization and mapping
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        mapping = Mapping.objects.create(
            name='test-mapping',
            organization_id=org.code,
            mapping_config={},
            source_datasets=['test']
        )
        
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        view.set_current_mapping(authenticated_request, mapping.id, mapping.name, org.id)
        
        # Don't select any files (empty list)
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = []
        
        # Run validation
        post_request = authenticated_request
        post_request.method = 'POST'
        post_request.POST = QueryDict()
        
        response = run_pre_execution_validation(post_request)
        
        # Verify response
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert response_data['success'] is False
        assert 'No files selected' in response_data['error']
    
    @pytest.mark.django_db
    def test_validation_service_exception(self, authenticated_request):
        """
        Test validation flow when validation service throws exception
        """
        # Create minimal organization and mapping
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        mapping = Mapping.objects.create(
            name='test-mapping',
            organization_id=org.code,
            mapping_config={'mappings': []},
            source_datasets=['test']
        )
        
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        view.set_current_mapping(authenticated_request, mapping.id, mapping.name, org.id)
        
        # Select files
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Mock validation service to raise exception
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.side_effect = Exception("Validation service error")
            
            # Mock other services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 500
                    response_data = json.loads(response.content)
                    assert response_data['success'] is False
                    assert 'Validation service error' in response_data['error']
    
    @pytest.mark.django_db
    def test_validation_with_invalid_mapping_config(self, authenticated_request):
        """
        Test validation flow with invalid mapping configuration
        """
        # Create organization and mapping with invalid config
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        mapping = Mapping.objects.create(
            name='test-mapping',
            organization_id=org.code,
            mapping_config={'invalid': 'config'},  # Invalid config
            source_datasets=['test']
        )
        
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        view.set_current_mapping(authenticated_request, mapping.id, mapping.name, org.id)
        
        # Select files
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Mock validation with configuration error
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.0
            )
            
            # Add configuration error
            mock_validation_result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.INVALID_MAPPING_CONFIG,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.CONFIGURATION,
                message="Invalid mapping configuration: missing required field 'mappings'",
                details={'missing_field': 'mappings'},
                suggested_fix="Update mapping configuration to include required fields"
            ))
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock other services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    assert response_data['validation_results']['is_valid'] is False
                    assert len(response_data['validation_results']['errors']) == 1
                    
                    # Check error details
                    error = response_data['validation_results']['errors'][0]
                    assert error['code'] == ValidationErrorCodes.INVALID_MAPPING_CONFIG
                    assert 'mapping configuration' in error['message']
                    assert 'missing_field' in error['details']
    
    @pytest.mark.django_db
    def test_validation_session_persistence(self, authenticated_request):
        """
        Test that validation results are properly stored in session
        """
        # Create organization and mapping
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        mapping = Mapping.objects.create(
            name='test-mapping',
            organization_id=org.code,
            mapping_config={'mappings': []},
            source_datasets=['test']
        )
        
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        view.set_current_mapping(authenticated_request, mapping.id, mapping.name, org.id)
        
        # Select files
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Mock successful validation
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result = PreExecutionValidationResult(
                is_valid=True,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.95
            )
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result
            
            # Mock other services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = mapping.mapping_config
                    
                    # Run validation
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response = run_pre_execution_validation(post_request)
                    
                    # Verify response
                    assert response.status_code == 200
                    response_data = json.loads(response.content)
                    assert response_data['success'] is True
                    
                    # Verify validation results are stored in session
                    validation_session_key = f'validation_results_{org.code}'
                    assert validation_session_key in authenticated_request.session
                    stored_results = authenticated_request.session[validation_session_key]
                    assert stored_results['is_valid'] is True
                    assert stored_results['overall_confidence'] > 0.9
                    assert 'validation_timestamp' in stored_results
                    assert 'validation_duration' in stored_results
    
    @pytest.mark.django_db
    def test_validation_iterative_correction_workflow(self, authenticated_request):
        """
        Test iterative validation and correction workflow
        """
        # Create organization and mapping
        org = Organization.objects.create(
            code='test',
            name='Test Organization',
            domain='test.com'
        )
        
        mapping = Mapping.objects.create(
            name='test-mapping',
            organization_id=org.code,
            mapping_config={'mappings': []},
            source_datasets=['test']
        )
        
        # Setup organization and mapping
        view = IngestDataView()
        view.set_current_organization(authenticated_request, org.code)
        view.set_current_mapping(authenticated_request, mapping.id, mapping.name, org.id)
        
        # Select files
        authenticated_request.session[SELECTED_FILES_SESSION_KEY] = ['metadata/test.csv']
        
        # Mock first validation run with errors
        with patch('arkumu.importer.services.pre_execution_validation.pre_execution_validator.PreExecutionValidator') as mock_validator:
            mock_validation_result_1 = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.3
            )
            
            # Add errors that need correction
            mock_validation_result_1.add_issue(ValidationIssue(
                code=ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message="Required column 'email' is missing",
                column_name='email',
                suggested_fix="Add email column to mapping"
            ))
            
            mock_validator_instance = Mock()
            mock_validator.return_value = mock_validator_instance
            mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result_1
            
            # Mock other services
            with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_service:
                mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
                
                with patch('arkumu.importer.services.mapping_consumer.mapping_adapter.MappingAdapter') as mock_mapping_adapter:
                    mock_adapter = Mock()
                    mock_mapping_adapter.return_value = mock_adapter
                    mock_adapter.load_mapping_config.return_value = mapping.mapping_config
                    
                    # First validation run
                    post_request = authenticated_request
                    post_request.method = 'POST'
                    post_request.POST = QueryDict()
                    
                    response1 = run_pre_execution_validation(post_request)
                    
                    # Verify first response has errors
                    assert response1.status_code == 200
                    response1_data = json.loads(response1.content)
                    assert response1_data['success'] is True
                    assert response1_data['validation_results']['is_valid'] is False
                    assert len(response1_data['validation_results']['errors']) == 1
                    
                    # User "fixes" the issue (in reality would update mapping)
                    # Mock second validation run with fewer errors
                    mock_validation_result_2 = PreExecutionValidationResult(
                        is_valid=True,
                        validation_mode=ValidationMode.STRICT,
                        overall_confidence=0.9
                    )
                    
                    # Add only a warning now
                    mock_validation_result_2.add_issue(ValidationIssue(
                        code=ValidationErrorCodes.UNMAPPED_REQUIRED_COLUMN,
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.COLUMN_MAPPING,
                        message="Column 'phone' is not mapped",
                        column_name='phone',
                        suggested_fix="Consider mapping phone column"
                    ))
                    
                    mock_validator_instance.validate_mapping_execution.return_value = mock_validation_result_2
                    
                    # Second validation run
                    response2 = run_pre_execution_validation(post_request)
                    
                    # Verify second response shows improvement
                    assert response2.status_code == 200
                    response2_data = json.loads(response2.content)
                    assert response2_data['success'] is True
                    assert response2_data['validation_results']['is_valid'] is True
                    assert len(response2_data['validation_results']['errors']) == 0
                    assert len(response2_data['validation_results']['warnings']) == 1
                    assert response2_data['validation_results']['overall_confidence'] > 0.8
                    
                    # Verify both validation results are stored in session
                    validation_session_key = f'validation_results_{org.code}'
                    stored_results = authenticated_request.session[validation_session_key]
                    assert stored_results['is_valid'] is True  # Latest result
                    assert stored_results['overall_confidence'] == 1.0  # Latest result - deterministic confidence