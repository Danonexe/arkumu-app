"""
Pytest configuration for arkumu importer services tests.
Provides fixtures for common test data and Django database setup.
"""
import pytest
import tempfile
import shutil
import os
import boto3
from moto import mock_aws
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.db import transaction
from unittest.mock import Mock, patch
from pathlib import Path

# Import models
from arkumu.users.models import Organization, User
from arkumu.importer.models import IngestSession
from arkumu.metadata.models.mappings import Mapping

# Test constants
TEST_BUCKET_NAME = 'test-arkumu-bucket'
TEST_INGEST_BUCKET = 'test-ingest-bucket'
TEST_PRODUCTION_BUCKET = 'test-production-bucket'


@pytest.fixture(scope='function')
def temp_dir():
    """Create a temporary directory for tests and clean it up afterwards"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture(scope='function')
def aws_credentials():
    """Set up AWS credentials for testing"""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['S3_BUCKET_NAME'] = TEST_BUCKET_NAME
    os.environ['AWS_INGEST_BUCKET_NAME'] = TEST_INGEST_BUCKET
    os.environ['AWS_PRODUCTION_BUCKET_NAME'] = TEST_PRODUCTION_BUCKET
    
    yield
    
    # Clean up
    os.environ.pop('AWS_ACCESS_KEY_ID', None)
    os.environ.pop('AWS_SECRET_ACCESS_KEY', None)
    os.environ.pop('AWS_SECURITY_TOKEN', None)
    os.environ.pop('AWS_SESSION_TOKEN', None)
    os.environ.pop('AWS_DEFAULT_REGION', None)
    os.environ.pop('S3_BUCKET_NAME', None)
    os.environ.pop('AWS_INGEST_BUCKET_NAME', None)
    os.environ.pop('AWS_PRODUCTION_BUCKET_NAME', None)


@pytest.fixture(scope='function')
def mock_s3(aws_credentials):
    """Set up mock AWS S3 environment"""
    with mock_aws():
        # Create S3 client with mock credentials
        s3 = boto3.client(
            's3',
            aws_access_key_id='testing',
            aws_secret_access_key='testing',
            region_name='us-east-1'
        )
        # Create test buckets
        s3.create_bucket(Bucket=TEST_BUCKET_NAME)
        s3.create_bucket(Bucket=TEST_INGEST_BUCKET)
        s3.create_bucket(Bucket=TEST_PRODUCTION_BUCKET)
        yield s3


@pytest.fixture
def test_organization():
    """Create a test organization"""
    org, created = Organization.objects.get_or_create(
        code='TEST_UNIV',
        defaults={
            'name': 'Test University',
            'domain': 'test.edu'
        }
    )
    return org


@pytest.fixture
def test_user(test_organization):
    """Create a test user"""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'test@test.edu',
            'name': 'Test User',
            'organization': test_organization,
            'role': 'researcher'
        }
    )
    return user


@pytest.fixture
def test_archivist(test_organization):
    """Create a test archivist user"""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='archivist',
        defaults={
            'email': 'archivist@test.edu',
            'name': 'Test Archivist',
            'organization': test_organization,
            'role': 'archivist'
        }
    )
    return user


@pytest.fixture
def test_manager(test_organization):
    """Create a test manager user"""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='manager',
        defaults={
            'email': 'manager@test.edu',
            'name': 'Test Manager',
            'organization': test_organization,
            'role': 'manager'
        }
    )
    return user


@pytest.fixture
def test_system_admin(test_organization):
    """Create a test system admin user"""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='sysadmin',
        defaults={
            'email': 'admin@test.edu',
            'name': 'System Administrator',
            'organization': test_organization,
            'role': 'system_admin'
        }
    )
    return user


@pytest.fixture
def test_ingest_session(test_user, test_organization):
    """Create a test ingest session"""
    return IngestSession.objects.create(
        user=test_user,
        dataset_name='test_dataset',
        organization=test_organization.code,
        s3_bucket=TEST_INGEST_BUCKET,
        s3_object_key='test/data.csv',
        delimiter=';',
        has_quoted_fields=True,
        base_uri='http://arkumu.org/test',
        total_rows=100,
        processed_rows=0,
        successful_rows=0,
        failed_rows=0
    )


@pytest.fixture
def test_mapping(test_user, test_organization):
    """Create a test mapping"""
    return Mapping.objects.create(
        name='Test Mapping',
        description='A test mapping configuration',
        organization_id=test_organization.code,
        created_by=test_user,
        mapping_config={
            'workspace_columns': {
                'col1': {'type': 'string', 'required': True},
                'col2': {'type': 'integer', 'required': False}
            },
            'relationships': [],
            'ontology_config': {}
        },
        source_datasets=['test_dataset.csv'],
        validation_status='draft'
    )


@pytest.fixture
def validated_mapping(test_user, test_organization):
    """Create a validated mapping"""
    return Mapping.objects.create(
        name='Validated Mapping',
        description='A validated mapping configuration',
        organization_id=test_organization.code,
        created_by=test_user,
        mapping_config={
            'workspace_columns': {
                'name': {'type': 'string', 'required': True},
                'age': {'type': 'integer', 'required': False},
                'location': {'type': 'string', 'required': False}
            },
            'relationships': [
                {
                    'from_column': 'name',
                    'to_column': 'location',
                    'relationship_type': 'P7'
                }
            ],
            'ontology_config': {
                'base_class': 'E21',
                'property_mappings': {
                    'name': 'P1',
                    'age': 'P3'
                }
            }
        },
        source_datasets=['validated_dataset.csv'],
        validation_status='validated'
    )


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing"""
    return [
        ['name', 'age', 'location'],
        ['John Doe', '30', 'New York'],
        ['Jane Smith', '25', 'Los Angeles'],
        ['Bob Johnson', '35', 'Chicago']
    ]


@pytest.fixture
def sample_csv_content():
    """Sample CSV content as string"""
    return """name;age;location
John Doe;30;New York
Jane Smith;25;Los Angeles
Bob Johnson;35;Chicago"""


@pytest.fixture
def complex_csv_data():
    """Complex CSV data with various data types for testing"""
    return [
        ['id', 'name', 'birth_date', 'score', 'active', 'notes'],
        ['1', 'Alice Brown', '1990-05-15', '87.5', 'true', 'Excellent student'],
        ['2', 'Charlie Davis', '1985-12-03', '92.3', 'false', 'Former student'],
        ['3', 'Diana Wilson', '1992-08-20', '78.9', 'true', 'Good progress']
    ]


@pytest.fixture
def mock_s3_file(mock_s3):
    """Mock S3 file for testing"""
    csv_content = """name;age;location
John Doe;30;New York
Jane Smith;25;Los Angeles
Bob Johnson;35;Chicago"""
    
    # Upload test file to mock S3
    mock_s3.put_object(
        Bucket=TEST_INGEST_BUCKET,
        Key='test/data.csv',
        Body=csv_content.encode('utf-8')
    )
    
    return {
        'bucket': TEST_INGEST_BUCKET,
        'key': 'test/data.csv',
        'content': csv_content
    }


@pytest.fixture
def mock_huey_task():
    """Mock Huey task for testing"""
    mock_task = Mock()
    mock_task.id = 'test-task-id'
    mock_task.result = Mock()
    mock_task.result.return_value = {'status': 'success', 'processed_rows': 100}
    return mock_task


@pytest.fixture
def mock_progress_tracker():
    """Mock progress tracker for testing"""
    mock_tracker = Mock()
    mock_tracker.update_progress = Mock()
    mock_tracker.mark_completed = Mock()
    mock_tracker.mark_failed = Mock()
    mock_tracker.get_progress = Mock(return_value={'progress': 50, 'status': 'in_progress'})
    return mock_tracker


@pytest.fixture
def test_execution_config():
    """Test execution configuration"""
    return {
        'chunk_size': 100,
        'max_retries': 3,
        'timeout': 300,
        'parallel_workers': 2,
        'validation_enabled': True,
        'create_backup': False
    }


@pytest.fixture
def test_validation_config():
    """Test validation configuration"""
    return {
        'required_columns': ['name', 'age'],
        'data_types': {
            'name': 'string',
            'age': 'integer',
            'location': 'string'
        },
        'constraints': {
            'age': {'min': 0, 'max': 150},
            'name': {'min_length': 1, 'max_length': 255}
        }
    }


@pytest.fixture
def test_import_stats():
    """Test import statistics"""
    return {
        'total_rows': 100,
        'processed_rows': 95,
        'successful_rows': 90,
        'failed_rows': 5,
        'skipped_rows': 5,
        'processing_time': 45.2,
        'errors': [
            {'row': 15, 'error': 'Invalid age value'},
            {'row': 32, 'error': 'Missing required field: name'}
        ]
    }


@pytest.fixture
def fixture_path():
    """Path to test fixtures directory"""
    return Path(__file__).parent.parent / 'fixtures'


@pytest.fixture
def mapping_fixtures_path(fixture_path):
    """Path to mapping fixtures directory"""
    return fixture_path / 'mappings'


@pytest.fixture
def data_fixtures_path(fixture_path):
    """Path to data fixtures directory"""
    return fixture_path / 'data'


# Override settings for testing
@pytest.fixture(autouse=True)
def test_settings():
    """Override Django settings for testing"""
    with override_settings(
        # Use in-memory database for faster tests
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        # Disable caching for predictable tests
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            }
        },
        # Test-specific settings
        HUEY={
            'huey_class': 'huey.MemoryHuey',
            'name': 'test_arkumu',
            'immediate': True,  # Execute tasks immediately in tests
        },
        # S3 test settings
        AWS_S3_REGION_NAME='us-east-1',
        AWS_INGEST_BUCKET_NAME=TEST_INGEST_BUCKET,
        AWS_PRODUCTION_BUCKET_NAME=TEST_PRODUCTION_BUCKET,
        # Disable logging during tests
        LOGGING_CONFIG=None,
    ):
        yield


@pytest.fixture
def isolated_db():
    """Provide isolated database transaction for each test"""
    with transaction.atomic():
        # Create a savepoint for rollback
        savepoint = transaction.savepoint()
        yield
        # Rollback to savepoint after test
        transaction.savepoint_rollback(savepoint)


@pytest.fixture
def mock_execution_engine():
    """Mock execution engine for testing"""
    mock_engine = Mock()
    mock_engine.execute_import = Mock(return_value={'status': 'success', 'processed_rows': 100})
    mock_engine.validate_mapping = Mock(return_value={'valid': True, 'errors': []})
    mock_engine.estimate_processing_time = Mock(return_value=120.0)
    return mock_engine


@pytest.fixture
def mock_file_upload_service():
    """Mock file upload service for testing"""
    mock_service = Mock()
    mock_service.upload_file = Mock(return_value={'upload_id': 'test-upload-id', 'status': 'success'})
    mock_service.get_upload_status = Mock(return_value={'status': 'completed', 'file_size': 1024})
    mock_service.delete_file = Mock(return_value={'status': 'deleted'})
    return mock_service


@pytest.fixture
def mock_mapping_adapter():
    """Mock mapping adapter for testing"""
    mock_adapter = Mock()
    mock_adapter.adapt_mapping = Mock(return_value={'adapted': True, 'config': {}})
    mock_adapter.validate_mapping = Mock(return_value={'valid': True, 'warnings': []})
    return mock_adapter


# Test data factories for creating consistent test objects
class TestDataFactory:
    """Factory for creating test data objects"""
    
    @staticmethod
    def create_ingest_session(user, organization, **kwargs):
        """Create a test ingest session with default values"""
        defaults = {
            'dataset_name': 'test_dataset',
            'organization': organization.code if hasattr(organization, 'code') else organization,
            's3_bucket': TEST_INGEST_BUCKET,
            's3_object_key': 'test/data.csv',
            'delimiter': ';',
            'has_quoted_fields': True,
            'base_uri': 'http://arkumu.org/test',
            'total_rows': 100,
            'processed_rows': 0,
            'successful_rows': 0,
            'failed_rows': 0
        }
        defaults.update(kwargs)
        return IngestSession.objects.create(user=user, **defaults)
    
    @staticmethod
    def create_mapping(user, organization, **kwargs):
        """Create a test mapping with default values"""
        defaults = {
            'name': 'Test Mapping',
            'description': 'A test mapping configuration',
            'organization_id': organization.code if hasattr(organization, 'code') else organization,
            'created_by': user,
            'mapping_config': {
                'workspace_columns': {
                    'col1': {'type': 'string', 'required': True},
                    'col2': {'type': 'integer', 'required': False}
                },
                'relationships': [],
                'ontology_config': {}
            },
            'source_datasets': ['test_dataset.csv'],
            'validation_status': 'draft'
        }
        defaults.update(kwargs)
        return Mapping.objects.create(**defaults)


@pytest.fixture
def test_data_factory():
    """Provide test data factory"""
    return TestDataFactory


@pytest.fixture
def mock_s3_service(mock_s3):
    """Create an S3UploadService instance with mock S3 client"""
    from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService
    
    service = S3UploadService(
        bucket_name=TEST_BUCKET_NAME,
        region_name='us-east-1'
    )
    # Override the S3 client with our mock
    service.s3_client = mock_s3
    return service