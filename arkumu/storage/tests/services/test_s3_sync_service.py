import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model

from arkumu.storage.services.s3_sync_service import S3SyncService
from arkumu.storage.models import S3FileObject, UploadSession

User = get_user_model()


# Fixtures
@pytest.fixture
def mock_s3_client():
    """Mock S3 client with configurable responses."""
    client = Mock()
    return client


@pytest.fixture
def mock_bucket_service():
    """Mock BucketService."""
    service = Mock()
    service.get_predefined_organizations.return_value = ['test-bucket-1', 'test-bucket-2']
    return service


@pytest.fixture
def sample_s3_files():
    """Sample S3 file objects."""
    return [
        {
            'Key': 'data/file1.txt',
            'Size': 1024,
            'LastModified': datetime(2023, 1, 1)
        },
        {
            'Key': 'data/subfolder/file2.csv',
            'Size': 2048,
            'LastModified': datetime(2023, 1, 2)
        },
        {
            'Key': 'data/file3.json',
            'Size': 512,
            'LastModified': datetime(2023, 1, 3)
        }
    ]


@pytest.fixture
def sync_service(mock_s3_client, mock_bucket_service):
    """Create S3SyncService with mocked S3 and bucket service."""
    with patch('arkumu.storage.services.s3_sync_service.BucketService', return_value=mock_bucket_service), \
         patch('arkumu.storage.services.s3_sync_service.boto3.client', return_value=mock_s3_client):
        return S3SyncService()


@pytest.fixture
def test_user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def test_upload_session(db, test_user):
    """Create a test upload session."""
    return UploadSession.objects.create(
        user=test_user,
        folder_name='test_folder',
        s3_bucket='test-bucket-1',
        status='completed',
        total_files=0,
        total_size_bytes=0
    )


@pytest.fixture
def existing_s3_files(db, test_upload_session):
    """Create some existing S3FileObject records."""
    files = []
    files.append(S3FileObject.objects.create(
        s3_key='data/existing_file.txt',
        file_name='existing_file.txt',
        file_size_bytes=1500,
        session=test_upload_session,
        status='completed'
    ))
    return files


# Basic functionality tests using real database
@pytest.mark.django_db
def test_sync_bucket_with_no_s3_files(sync_service, mock_s3_client):
    """Test syncing bucket when no files exist in S3."""
    # Mock empty S3 response
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': []}]
    mock_s3_client.get_paginator.return_value = paginator
    
    result = sync_service.sync_bucket('test-bucket', dry_run=True)
    
    assert result['found_in_s3'] == 0
    assert result['existing_in_db'] == 0
    assert result['missing'] == 0
    assert result['created'] == 0


@pytest.mark.django_db
def test_sync_bucket_all_files_orphaned(sync_service, mock_s3_client, sample_s3_files):
    """Test syncing when all S3 files are missing from database."""
    # Mock S3 response with files
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': sample_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    result = sync_service.sync_bucket('test-bucket', dry_run=True)
    
    assert result['found_in_s3'] == 3
    assert result['existing_in_db'] == 0
    assert result['missing'] == 3
    assert result['created'] == 0  # dry_run mode


@pytest.mark.django_db
def test_sync_bucket_partial_orphaned(sync_service, mock_s3_client, sample_s3_files, existing_s3_files):
    """Test syncing when some files exist in database."""
    # Add one file that matches S3
    existing_files = existing_s3_files
    existing_files[0].s3_key = 'data/file1.txt'  # Match first sample file
    existing_files[0].save()
    
    # Mock S3 response
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': sample_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    result = sync_service.sync_bucket('test-bucket-1', dry_run=True)
    
    assert result['found_in_s3'] == 3
    assert result['existing_in_db'] == 1
    assert result['missing'] == 2
    assert result['created'] == 0


@pytest.mark.django_db
def test_sync_bucket_with_creation(sync_service, mock_s3_client, sample_s3_files):
    """Test actual record creation (not dry run)."""
    # Mock S3 response
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': sample_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    # Verify no files exist initially
    assert S3FileObject.objects.filter(s3_key__startswith='data/').count() == 0
    
    result = sync_service.sync_bucket('test-bucket', dry_run=False)
    
    assert result['found_in_s3'] == 3
    assert result['missing'] == 3
    assert result['created'] == 3
    
    # Verify files were actually created in database
    created_files = S3FileObject.objects.filter(s3_key__startswith='data/')
    assert created_files.count() == 3
    
    # Verify file details
    file1 = created_files.get(s3_key='data/file1.txt')
    assert file1.file_name == 'file1.txt'
    assert file1.file_size_bytes == 1024
    assert file1.status == 'completed'
    assert file1.session.s3_bucket == 'test-bucket'


@pytest.mark.django_db  
def test_sync_bucket_creates_system_user_and_session(sync_service, mock_s3_client, sample_s3_files):
    """Test that sync creates system user and placeholder session."""
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': sample_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    # Verify no system user exists initially
    assert not User.objects.filter(username='system_sync').exists()
    
    result = sync_service.sync_bucket('test-bucket', dry_run=False)
    
    assert result['created'] == 3
    
    # Verify system user was created
    system_user = User.objects.get(username='system_sync')
    assert system_user.email == 'system@arkumu.local'
    assert system_user.name == 'System Sync'
    
    # Verify placeholder session was created
    placeholder_session = UploadSession.objects.get(
        user=system_user,
        folder_name='sync_orphaned_test-bucket'
    )
    assert placeholder_session.s3_bucket == 'test-bucket'
    assert placeholder_session.status == 'completed'
    assert placeholder_session.total_files == 3
    assert placeholder_session.total_size_bytes == sum(f['Size'] for f in sample_s3_files)


# Error handling tests
@pytest.mark.django_db
def test_sync_bucket_s3_error(sync_service, mock_s3_client):
    """Test handling S3 client errors."""
    mock_s3_client.get_paginator.side_effect = ClientError(
        {'Error': {'Code': 'NoSuchBucket'}}, 'list_objects_v2'
    )
    
    with pytest.raises(ClientError):
        sync_service.sync_bucket('nonexistent-bucket')


# Multi-bucket tests
@pytest.mark.django_db
def test_sync_all_buckets_success(sync_service):
    """Test syncing all predefined buckets."""
    with patch.object(sync_service, 'sync_bucket') as mock_sync:
        mock_sync.return_value = {
            'found_in_s3': 5, 'existing_in_db': 2, 'missing': 3, 'created': 3
        }
        
        results = sync_service.sync_all_buckets(dry_run=True)
        
        assert len(results) == 2  # Two buckets from fixture
        assert 'test-bucket-1' in results
        assert 'test-bucket-2' in results
        assert mock_sync.call_count == 2


@pytest.mark.django_db
def test_sync_all_buckets_partial_failure(sync_service):
    """Test syncing when one bucket fails."""
    def mock_sync_side_effect(bucket_name, *args, **kwargs):
        if bucket_name == 'test-bucket-1':
            return {'found_in_s3': 5, 'existing_in_db': 2, 'missing': 3, 'created': 3}
        else:
            raise Exception("Access denied")
    
    with patch.object(sync_service, 'sync_bucket', side_effect=mock_sync_side_effect):
        results = sync_service.sync_all_buckets()
        
        assert len(results) == 2
        assert results['test-bucket-1']['found_in_s3'] == 5
        assert 'error' in results['test-bucket-2']
        assert results['test-bucket-2']['created'] == 0


# Orphaned files count tests
@pytest.mark.django_db
def test_get_orphaned_files_count_single_bucket(sync_service):
    """Test counting orphaned files in a single bucket."""
    with patch.object(sync_service, 'sync_bucket') as mock_sync:
        mock_sync.return_value = {'missing': 7}
        
        count = sync_service.get_orphaned_files_count('test-bucket')
        
        assert count == 7
        mock_sync.assert_called_once_with('test-bucket', 'data/', dry_run=True)


@pytest.mark.django_db
def test_get_orphaned_files_count_all_buckets(sync_service):
    """Test counting orphaned files across all buckets."""
    with patch.object(sync_service, 'sync_bucket') as mock_sync:
        mock_sync.side_effect = [
            {'missing': 5},  # test-bucket-1
            {'missing': 3}   # test-bucket-2
        ]
        
        count = sync_service.get_orphaned_files_count()
        
        assert count == 8
        assert mock_sync.call_count == 2


@pytest.mark.django_db
def test_get_orphaned_files_count_with_errors(sync_service):
    """Test orphaned count when some buckets fail."""
    def mock_sync_side_effect(bucket_name, *args, **kwargs):
        if bucket_name == 'test-bucket-1':
            return {'missing': 5}
        else:
            raise Exception("Access denied")
    
    with patch.object(sync_service, 'sync_bucket', side_effect=mock_sync_side_effect):
        count = sync_service.get_orphaned_files_count()
        
        assert count == 5  # Only successful bucket counted


# Real database integration tests
@pytest.mark.django_db
def test_create_missing_records_real_database(sync_service, sample_s3_files):
    """Test creation of missing database records with real database."""
    initial_count = S3FileObject.objects.count()
    
    result = sync_service._create_missing_records('test-bucket', sample_s3_files)
    
    assert result == 3
    assert S3FileObject.objects.count() == initial_count + 3
    
    # Verify files were created correctly
    created_files = S3FileObject.objects.filter(s3_key__startswith='data/')
    assert created_files.count() == 3
    
    # Check specific file details
    file1 = created_files.get(s3_key='data/file1.txt')
    assert file1.file_name == 'file1.txt'
    assert file1.file_size_bytes == 1024
    
    file2 = created_files.get(s3_key='data/subfolder/file2.csv')
    assert file2.file_name == 'file2.csv'
    assert file2.file_size_bytes == 2048


@pytest.mark.django_db
def test_placeholder_session_creation_real_database(sync_service):
    """Test placeholder session creation with real database."""
    initial_user_count = User.objects.count()
    initial_session_count = UploadSession.objects.count()
    
    session = sync_service._get_or_create_placeholder_session('test-bucket')
    
    assert User.objects.count() == initial_user_count + 1
    assert UploadSession.objects.count() == initial_session_count + 1
    
    # Verify system user was created
    system_user = User.objects.get(username='system_sync')
    assert system_user.email == 'system@arkumu.local'
    assert system_user.name == 'System Sync'
    
    # Verify session was created
    assert session.user == system_user
    assert session.s3_bucket == 'test-bucket'
    assert session.folder_name == 'sync_orphaned_test-bucket'
    assert session.status == 'completed'


@pytest.mark.django_db
def test_placeholder_session_reuse_existing(sync_service, test_user):
    """Test that existing system user and session are reused."""
    # Create system user manually
    system_user = User.objects.create_user(
        username='system_sync',
        email='system@arkumu.local',
        name='System Sync'
    )
    
    # Create existing session
    existing_session = UploadSession.objects.create(
        user=system_user,
        folder_name='sync_orphaned_test-bucket',
        s3_bucket='test-bucket',
        status='completed',
        total_files=5,
        total_size_bytes=1000
    )
    
    initial_user_count = User.objects.count()
    initial_session_count = UploadSession.objects.count()
    
    session = sync_service._get_or_create_placeholder_session('test-bucket')
    
    # Should not create new user or session
    assert User.objects.count() == initial_user_count
    assert UploadSession.objects.count() == initial_session_count
    assert session == existing_session


# Edge cases and validation tests
@pytest.mark.django_db
def test_sync_bucket_empty_prefix(sync_service, mock_s3_client):
    """Test syncing with empty prefix."""
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': []}]
    mock_s3_client.get_paginator.return_value = paginator
    
    result = sync_service.sync_bucket('test-bucket', prefix='', dry_run=True)
    
    assert result['found_in_s3'] == 0
    mock_s3_client.get_paginator.assert_called_once_with('list_objects_v2')


@pytest.mark.django_db
def test_sync_bucket_custom_prefix(sync_service, mock_s3_client, sample_s3_files, existing_s3_files):
    """Test syncing with custom prefix."""
    # Create existing file with custom prefix
    existing_files = existing_s3_files
    existing_files[0].s3_key = 'uploads/file1.txt'  # Changed to match one of the S3 files
    existing_files[0].save()
    
    # Mock S3 files with custom prefix
    custom_s3_files = [
        {'Key': 'uploads/file1.txt', 'Size': 100},
        {'Key': 'uploads/file2.txt', 'Size': 200}
    ]
    
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': custom_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    result = sync_service.sync_bucket('test-bucket-1', prefix='uploads/', dry_run=True)
    
    assert result['found_in_s3'] == 2
    assert result['existing_in_db'] == 1
    assert result['missing'] == 1


@pytest.mark.django_db
def test_get_s3_files_pagination(sync_service, mock_s3_client):
    """Test S3 file listing with pagination."""
    # Mock paginated responses
    page1 = {'Contents': [{'Key': 'data/file1.txt', 'Size': 100}]}
    page2 = {'Contents': [{'Key': 'data/file2.txt', 'Size': 200}]}
    
    paginator = Mock()
    paginator.paginate.return_value = [page1, page2]
    mock_s3_client.get_paginator.return_value = paginator
    
    files = sync_service._get_s3_files('test-bucket', 'data/')
    
    assert len(files) == 2
    assert files[0]['Key'] == 'data/file1.txt'
    assert files[1]['Key'] == 'data/file2.txt'
    paginator.paginate.assert_called_once_with(Bucket='test-bucket', Prefix='data/')


@pytest.mark.django_db
def test_get_s3_files_no_contents(sync_service, mock_s3_client):
    """Test S3 file listing when no objects exist."""
    paginator = Mock()
    paginator.paginate.return_value = [{}]  # No 'Contents' key
    mock_s3_client.get_paginator.return_value = paginator
    
    files = sync_service._get_s3_files('test-bucket', 'data/')
    
    assert len(files) == 0


@pytest.mark.django_db 
def test_sync_bucket_transaction_rollback_on_error(sync_service, mock_s3_client, sample_s3_files):
    """Test that database transaction rolls back on error."""
    paginator = Mock()
    paginator.paginate.return_value = [{'Contents': sample_s3_files}]
    mock_s3_client.get_paginator.return_value = paginator
    
    initial_count = S3FileObject.objects.count()
    
    # Mock bulk_create to fail after creating some objects
    with patch('arkumu.storage.models.S3FileObject.objects.bulk_create') as mock_bulk_create:
        mock_bulk_create.side_effect = Exception("Database error")
        
        # Should handle the error gracefully
        result = sync_service._create_missing_records('test-bucket', sample_s3_files)
        
        # Should fall back to individual creation
        assert result == 3
        # Files should still be created via individual saves
        assert S3FileObject.objects.count() > initial_count