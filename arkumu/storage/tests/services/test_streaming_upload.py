"""
Minimal test suite for streaming upload with session tracking.
"""

import pytest
from unittest.mock import Mock, patch

from arkumu.storage.services.upload_service import UploadService
from arkumu.storage.models import UploadSession, S3FileObject

# Test constants
TEST_ORG_BUCKET = 'fuk-bucket'

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
    service.get_organization_bucket.return_value = TEST_ORG_BUCKET
    return service

def test_upload_with_session(upload_service, mock_session, mock_file_object):
    """Test single file upload with session tracking."""
    # Setup
    mock_file = Mock(name="test.txt", content_type="text/plain", size=100, read=lambda: b"Test")
    
    # Mock upload
    with patch.object(upload_service, 'upload_file_stream', return_value={'success': True, 's3_key': 'test/test.txt'}):
        with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_file_object):
            result = upload_service.upload_django_file(
                uploaded_file=mock_file,
                path_prefix="test",
                session=mock_session
            )
    
    # Verify
    assert result['success'] is True
    mock_file_object.mark_completed.assert_called_once()
    mock_session.save.assert_called()

def test_upload_with_organization(upload_service, mock_session, mock_file_object, mock_bucket_service):
    """Test upload with organization bucket."""
    # Setup
    mock_file = Mock(name="org.txt", content_type="text/plain", size=100, read=lambda: b"Test")
    
    # Mock services
    with patch('arkumu.storage.services.bucket_service.BucketService', return_value=mock_bucket_service):
        with patch.object(upload_service, 'upload_file_stream', return_value={'success': True, 's3_key': 'org/org.txt'}):
            with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_file_object):
                result = upload_service.upload_django_file(
                    uploaded_file=mock_file,
                    path_prefix="org",
                    bucket_name=TEST_ORG_BUCKET,
                    session=mock_session
                )
    
    # Verify
    assert result['success'] is True
    mock_file_object.mark_completed.assert_called_once()

def test_batch_upload_with_session(upload_service, mock_session, mock_file_object):
    """Test batch upload with session tracking."""
    # Setup
    mock_files = [Mock(name=f"file{i}.txt", content_type="text/plain", size=100, read=lambda: b"Test") for i in range(2)]
    
    # Mock upload
    with patch.object(upload_service, 'upload_file_stream', return_value={'success': True, 's3_key': 'batch/file.txt'}):
        with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_file_object):
            result = upload_service.upload_batch_django_files_optimized(
                uploaded_files=mock_files,
                path_prefix="batch",
                session=mock_session
            )
    
    # Verify
    assert result['success'] is True
    assert mock_file_object.mark_completed.call_count == 2 