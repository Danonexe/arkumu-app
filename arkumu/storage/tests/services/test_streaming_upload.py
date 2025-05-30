"""
Minimal test suite for streaming upload functionality.
"""

import pytest
from unittest.mock import Mock, patch

from arkumu.storage.services.upload_service import UploadService
from arkumu.storage.models import UploadSession, S3FileObject

# Import test constants
from .test_constants import TEST_ORG_BUCKETS, TEST_BUCKET_NAME

@pytest.fixture
def upload_service():
    return UploadService()

@pytest.fixture
def mock_session():
    session = Mock(spec=UploadSession)
    session.id = "test-id"
    session.user = Mock(username="test_user")
    session.mark_completed = Mock()
    session.mark_failed = Mock()
    session.save = Mock()
    return session

@pytest.fixture
def mock_file_object():
    file_obj = Mock(spec=S3FileObject)
    file_obj.mark_completed = Mock()
    file_obj.mark_failed = Mock()
    return file_obj

@pytest.fixture
def mock_bucket_service():
    service = Mock()
    service.get_organization_bucket.return_value = TEST_ORG_BUCKETS['fuk']
    return service

def test_upload_django_file_basic(upload_service):
    """Test basic Django file upload."""
    # Setup
    mock_file = Mock()
    mock_file.name = "test.txt"
    mock_file.content_type = "text/plain"
    mock_file.size = 100
    mock_file.read = Mock(return_value=b"Test content")
    
    # Mock the underlying upload method
    with patch.object(upload_service, 'upload_file_stream') as mock_upload:
        mock_upload.return_value = {
            'success': True, 
            's3_key': 'test/test.txt',
            'file_size': 100,
            'content_type': 'text/plain'
        }
        
        result = upload_service.upload_django_file(
            uploaded_file=mock_file,
            path_prefix="test"
        )
    
    # Verify
    assert result['success'] is True
    assert result['s3_key'] == 'test/test.txt'
    mock_upload.assert_called_once()

def test_upload_django_file_with_multipart(upload_service):
    """Test Django file upload with multipart for large files."""
    # Setup - large file that triggers multipart
    mock_file = Mock()
    mock_file.name = "large_file.dat"
    mock_file.content_type = "application/octet-stream"
    mock_file.size = 15 * 1024 * 1024  # 15MB
    mock_file.read = Mock(return_value=b"Large file content")
    
    # Mock the underlying multipart upload method
    with patch.object(upload_service, 'upload_multipart_stream') as mock_multipart:
        mock_multipart.return_value = {
            'success': True, 
            's3_key': 'large/large_file.dat',
            'file_size': 15 * 1024 * 1024,
            'content_type': 'application/octet-stream'
        }
        
        result = upload_service.upload_django_file(
            uploaded_file=mock_file,
            path_prefix="large",
            use_multipart=True,
            multipart_threshold=10 * 1024 * 1024  # 10MB threshold
        )
    
    # Verify multipart was used
    assert result['success'] is True
    mock_multipart.assert_called_once()

def test_upload_batch_django_files_optimized(upload_service):
    """Test batch upload with optimized method."""
    # Setup
    mock_files = []
    for i in range(3):
        mock_file = Mock()
        mock_file.name = f"file{i}.txt"
        mock_file.content_type = "text/plain" 
        mock_file.size = 100
        mock_file.chunks = Mock(return_value=[b"test content"])
        mock_files.append(mock_file)
    
    # Mock the underlying optimized upload method
    with patch.object(upload_service, 'upload_files_optimized') as mock_optimized:
        mock_optimized.return_value = {
            'success': True,
            'success_count': 3,
            'error_count': 0,
            'total_files': 3,
            'results': [
                {'success': True, 'file_name': f'file{i}.txt', 's3_key': f'batch/file{i}.txt'}
                for i in range(3)
            ]
        }
        
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=mock_files,
            path_prefix="batch",
            bucket_name=TEST_BUCKET_NAME
        )
    
    # Verify
    assert result['success'] is True
    assert result['success_count'] == 3
    assert result['error_count'] == 0
    mock_optimized.assert_called_once()

def test_upload_batch_django_files_with_structure(upload_service):
    """Test batch upload with folder structure preservation."""
    # Setup
    mock_files = []
    file_paths = ['project/src/main.js', 'project/docs/README.md']
    
    for i, path in enumerate(file_paths):
        mock_file = Mock()
        mock_file.name = path.split('/')[-1]  # Just filename
        mock_file.content_type = "text/plain"
        mock_file.size = 100
        mock_file.seek = Mock()
        mock_files.append(mock_file)
    
    # Mock the underlying custom key upload method
    with patch.object(upload_service, '_upload_file_to_custom_key') as mock_custom:
        mock_custom.return_value = {
            'success': True,
            's3_key': 'data/project/src/main.js',
            'file_size': 100
        }
        
        result = upload_service.upload_batch_django_files_with_structure(
            uploaded_files=mock_files,
            base_path="data",
            bucket_name=TEST_BUCKET_NAME,
            file_paths=file_paths
        )
    
    # Verify
    assert result['success'] is True
    assert result['success_count'] == 2
    assert result['error_count'] == 0
    assert len(result['results']) == 2
    
    # Verify custom upload was called for each file
    assert mock_custom.call_count == 2

def test_upload_with_organization_bucket(upload_service, mock_bucket_service):
    """Test upload with organization-specific bucket."""
    # Setup
    mock_file = Mock()
    mock_file.name = "org_file.txt"
    mock_file.content_type = "text/plain"
    mock_file.size = 100
    mock_file.chunks = Mock(return_value=[b"test content"])  # Properly mock chunks()
    
    # Test using organization bucket directly
    org_bucket = TEST_ORG_BUCKETS['fuk']
    
    with patch.object(upload_service, 'upload_files_optimized') as mock_optimized:
        mock_optimized.return_value = {
            'success': True,
            'success_count': 1,
            'error_count': 0,
            'results': [{'success': True, 'file_name': 'org_file.txt', 'bucket': org_bucket}]
        }
        
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=[mock_file],
            path_prefix="org",
            bucket_name=org_bucket
        )
    
    # Verify organization bucket was used
    assert result['success'] is True
    assert result['results'][0]['bucket'] == org_bucket 