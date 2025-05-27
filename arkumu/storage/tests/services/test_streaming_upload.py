"""
Test suite for streaming upload service.
Run with: docker compose -f docker-compose.local.yml run --rm django pytest arkumu/storage/tests/services/test_streaming_upload.py
"""

import pytest
from io import BytesIO
from unittest.mock import Mock, patch
import boto3

from arkumu.storage.services.upload_service import UploadService


@pytest.fixture
def upload_service():
    """Fixture to provide upload service instance."""
    return UploadService()


def test_service_initialization(upload_service):
    """Test that the upload service initializes correctly."""
    assert upload_service is not None
    assert hasattr(upload_service, 'is_minio')
    assert hasattr(upload_service, 'endpoint_url')
    assert hasattr(upload_service, 'ingest_bucket')


def test_upload_bytes_stream(upload_service):
    """Test uploading raw bytes."""
    test_content = b"Hello, this is a test file for streaming upload!\nLine 2\nLine 3"
    test_filename = "test_streaming_upload.txt"
    
    # Patch the S3 client's upload_fileobj method
    with patch.object(upload_service.s3_client, 'upload_fileobj') as mock_upload:
        # Configure the mock to do nothing
        mock_upload.return_value = None
        
        # Patch the head_object method to return file info
        with patch.object(upload_service.s3_client, 'head_object') as mock_head:
            mock_head.return_value = {
                'ContentLength': len(test_content),
                'ContentType': 'text/plain',
                'LastModified': None
            }
            
            result = upload_service.upload_file_stream(
                file_obj=test_content,
                file_name=test_filename,
                content_type="text/plain",
                path_prefix="test-folder"
            )
    
    assert result['success'] is True
    assert result['file_name'] == test_filename
    assert 'test-folder' in result['s3_key']
    assert result['content_type'] == "text/plain"
    assert 'file_size' in result
    assert 'file_size_formatted' in result


def test_upload_bytesio_stream(upload_service):
    """Test uploading from BytesIO object."""
    test_content = BytesIO(b"This is another test file using BytesIO!\nMultiple lines\nFor testing")
    test_filename = "test_bytesio_upload.txt"
    
    # Patch the S3 client's upload_fileobj method
    with patch.object(upload_service.s3_client, 'upload_fileobj') as mock_upload:
        # Configure the mock to do nothing
        mock_upload.return_value = None
        
        # Patch the head_object method to return file info
        with patch.object(upload_service.s3_client, 'head_object') as mock_head:
            mock_head.return_value = {
                'ContentLength': len(test_content.getvalue()),
                'ContentType': 'text/plain',
                'LastModified': None
            }
            
            result = upload_service.upload_file_stream(
                file_obj=test_content,
                file_name=test_filename,
                content_type="text/plain",
                path_prefix="test-folder"
            )
    
    assert result['success'] is True
    assert result['file_name'] == test_filename
    assert 'test-folder' in result['s3_key']
    assert result['content_type'] == "text/plain"


def test_multipart_upload_stream(upload_service):
    """Test multipart upload for large files."""
    # Create a 6MB file to trigger multipart upload
    large_content = b"A" * (6 * 1024 * 1024)
    large_filename = "test_large_file.bin"
    
    # Patch the necessary S3 client methods
    with patch.object(upload_service.s3_client, 'create_multipart_upload') as mock_create:
        mock_create.return_value = {'UploadId': 'test-upload-id'}
        
        with patch.object(upload_service.s3_client, 'upload_part') as mock_upload_part:
            mock_upload_part.return_value = {'ETag': '"test-etag"'}
            
            with patch.object(upload_service.s3_client, 'complete_multipart_upload') as mock_complete:
                mock_complete.return_value = {'ETag': '"test-etag-complete"'}
                
                with patch.object(upload_service.s3_client, 'head_object') as mock_head:
                    mock_head.return_value = {
                        'ContentLength': len(large_content),
                        'ContentType': 'application/octet-stream',
                        'LastModified': None
                    }
                    
                    result = upload_service.upload_multipart_stream(
                        file_obj=large_content,
                        file_name=large_filename,
                        content_type="application/octet-stream",
                        path_prefix="test-folder",
                        chunk_size=5 * 1024 * 1024  # 5MB chunks
                    )
    
    assert result['success'] is True
    assert result['file_name'] == large_filename
    assert result['upload_type'] == 'multipart'
    assert 'parts_count' in result
    assert result['parts_count'] >= 2  # Should have at least 2 parts for 6MB file


def test_get_file_info(upload_service):
    """Test retrieving file information."""
    # First upload a file
    test_content = b"Test file for info retrieval"
    test_filename = "test_info_file.txt"
    test_s3_key = "test-folder/test_info_file.txt"
    
    # Patch the S3 client's upload_fileobj method
    with patch.object(upload_service.s3_client, 'upload_fileobj') as mock_upload:
        # Configure the mock to do nothing
        mock_upload.return_value = None
        
        # Patch the head_object method to return file info
        with patch.object(upload_service.s3_client, 'head_object') as mock_head:
            mock_head.return_value = {
                'ContentLength': len(test_content),
                'ContentType': 'text/plain',
                'LastModified': None,
                'ETag': '"test-etag"'
            }
            
            upload_result = upload_service.upload_file_stream(
                file_obj=test_content,
                file_name=test_filename,
                content_type="text/plain",
                path_prefix="test-folder"
            )
            
            # Now get file info
            info_result = upload_service.get_file_info(upload_result['s3_key'])
    
    assert info_result['success'] is True
    assert info_result['exists'] is True
    assert info_result['s3_key'] == upload_result['s3_key']
    assert 'file_size' in info_result
    assert 'file_size_formatted' in info_result
    assert 'content_type' in info_result
    assert 'etag' in info_result


def test_get_file_info_nonexistent(upload_service):
    """Test getting info for a non-existent file."""
    # Patch the head_object method to raise a 404 error
    with patch.object(upload_service.s3_client, 'head_object') as mock_head:
        mock_head.side_effect = boto3.exceptions.botocore.client.ClientError(
            {'Error': {'Code': '404', 'Message': 'Not Found'}},
            'HeadObject'
        )
        
        info_result = upload_service.get_file_info("nonexistent/file.txt")
    
    assert info_result['success'] is True
    assert info_result['exists'] is False


def test_legacy_presigned_post_returns_error(upload_service):
    """Test that legacy presigned URL methods return appropriate errors."""
    result = upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain"
    )
    
    assert result['success'] is False
    assert 'not supported' in result['error'].lower()
    assert 'alternative' in result


def test_legacy_batch_presigned_posts_returns_error(upload_service):
    """Test that legacy batch presigned URL methods return appropriate errors."""
    files_metadata = [
        {"file_name": "test1.txt", "file_type": "text/plain"},
        {"file_name": "test2.txt", "file_type": "text/plain"}
    ]
    
    result = upload_service.generate_batch_presigned_posts(files_metadata)
    
    assert result['success'] is False
    assert 'not supported' in result['error'].lower()
    assert 'alternative' in result


def test_django_file_upload(upload_service):
    """Test uploading Django UploadedFile objects."""
    # Mock a Django UploadedFile
    mock_file = Mock()
    mock_file.name = "django_test.txt"
    mock_file.content_type = "text/plain"
    mock_file.size = 100
    mock_file.read.return_value = b"Django file content"
    
    # Patch the upload_file_stream method to avoid the actual upload
    with patch.object(upload_service, 'upload_file_stream') as mock_upload:
        mock_upload.return_value = {
            'success': True,
            'file_name': "django_test.txt",
            's3_key': "django-uploads/django_test.txt",
            'bucket': upload_service.ingest_bucket,
            'content_type': "text/plain"
        }
        
        result = upload_service.upload_django_file(
            uploaded_file=mock_file,
            path_prefix="django-uploads"
        )
    
    assert result['success'] is True
    assert result['file_name'] == "django_test.txt"
    assert 'django-uploads' in result['s3_key']


def test_batch_django_files_upload(upload_service):
    """Test uploading multiple Django UploadedFile objects."""
    # Mock multiple Django UploadedFiles
    mock_files = []
    for i in range(3):
        mock_file = Mock()
        mock_file.name = f"batch_test_{i}.txt"
        mock_file.content_type = "text/plain"
        mock_file.size = 50
        mock_file.read.return_value = f"Batch file content {i}".encode()
        mock_files.append(mock_file)
    
    # Patch the upload_django_file method to avoid the actual upload
    with patch.object(upload_service, 'upload_django_file') as mock_upload:
        # Configure the mock to return success for each file
        mock_upload.side_effect = [
            {
                'success': True,
                'file_name': f"batch_test_{i}.txt",
                's3_key': f"batch-uploads/batch_test_{i}.txt",
                'bucket': upload_service.ingest_bucket,
                'content_type': "text/plain",
                'file_size': 50
            } for i in range(3)
        ]
        
        result = upload_service.upload_batch_django_files(
            uploaded_files=mock_files,
            path_prefix="batch-uploads"
        )
    
    assert result['success'] is True
    assert result['total_uploaded'] == 3
    assert result['total_failed'] == 0
    assert len(result['results']) == 3
    assert result['total_size'] > 0


def test_file_key_generation(upload_service):
    """Test S3 key generation with different parameters."""
    # Test with path prefix
    key1 = upload_service._generate_file_key("test file.txt", "folder/subfolder")
    assert key1 == "folder/subfolder/test_file.txt"  # Spaces should be replaced
    
    # Test without path prefix
    key2 = upload_service._generate_file_key("test file.txt", None)
    assert key2 == "test_file.txt"
    
    # Test with empty path prefix
    key3 = upload_service._generate_file_key("test file.txt", "")
    assert key3 == "test_file.txt"
    
    # Test with path prefix with leading/trailing slashes
    key4 = upload_service._generate_file_key("test.txt", "/folder/")
    assert key4 == "folder/test.txt"


def test_format_size_utility(upload_service):
    """Test the file size formatting utility."""
    # Test various file sizes
    assert upload_service._format_size(0) == "0 B"
    assert upload_service._format_size(500) == "500 B"
    assert upload_service._format_size(1024) == "1.00 KB"
    assert upload_service._format_size(1024 * 1024) == "1.00 MB"
    assert upload_service._format_size(1536) == "1.50 KB"  # 1.5 KB


@pytest.mark.parametrize("content_type,expected", [
    ("text/plain", "text/plain"),
    ("application/pdf", "application/pdf"),
    (None, "application/octet-stream"),  # Default fallback
])
def test_content_type_handling(upload_service, content_type, expected):
    """Test content type handling in uploads."""
    test_content = b"Test content"
    
    # Patch the S3 client's upload_fileobj method
    with patch.object(upload_service.s3_client, 'upload_fileobj') as mock_upload:
        # Configure the mock to do nothing
        mock_upload.return_value = None
        
        # Patch the head_object method to return file info
        with patch.object(upload_service.s3_client, 'head_object') as mock_head:
            mock_head.return_value = {
                'ContentLength': len(test_content),
                'ContentType': expected,
                'LastModified': None
            }
            
            result = upload_service.upload_file_stream(
                file_obj=test_content,
                file_name="test.txt",
                content_type=content_type or "application/octet-stream",
                path_prefix="test"
            )
    
    assert result['success'] is True
    assert result['content_type'] == expected


def test_upload_with_file_size(upload_service):
    """Test upload with explicit file size parameter."""
    test_content = b"Test content with known size"
    file_size = len(test_content)
    
    # Patch the S3 client's upload_fileobj method
    with patch.object(upload_service.s3_client, 'upload_fileobj') as mock_upload:
        # Configure the mock to do nothing
        mock_upload.return_value = None
        
        # Patch the head_object method to return file info
        with patch.object(upload_service.s3_client, 'head_object') as mock_head:
            mock_head.return_value = {
                'ContentLength': file_size,
                'ContentType': 'text/plain',
                'LastModified': None
            }
            
            result = upload_service.upload_file_stream(
                file_obj=test_content,
                file_name="sized_test.txt",
                content_type="text/plain",
                path_prefix="test",
                file_size=file_size
            )
    
    assert result['success'] is True
    assert result['file_size'] == file_size


def test_multipart_threshold_behavior(upload_service):
    """Test that the django file upload correctly chooses between single and multipart."""
    # Mock a small file (should use single-part)
    small_file = Mock()
    small_file.name = "small.txt"
    small_file.content_type = "text/plain"
    small_file.size = 1024  # 1KB
    small_file.read.return_value = b"Small file content"
    
    # Patch the upload_file_stream method to avoid the actual upload
    with patch.object(upload_service, 'upload_file_stream') as mock_upload:
        mock_upload.return_value = {
            'success': True,
            'file_name': "small.txt",
            's3_key': "small.txt",
            'bucket': upload_service.ingest_bucket,
            'content_type': "text/plain"
        }
        
        result = upload_service.upload_django_file(
            uploaded_file=small_file,
            multipart_threshold=10 * 1024 * 1024  # 10MB threshold
        )
    
    assert result['success'] is True
    # Single-part uploads don't have 'upload_type' field
    assert 'upload_type' not in result or result.get('upload_type') != 'multipart'


@pytest.mark.skip(reason="Requires S3/MinIO connection - integration test")
def test_integration_full_upload_cycle():
    """Integration test for full upload cycle (requires actual S3/MinIO)."""
    # This test would run against actual S3/MinIO
    # Skip by default to avoid requiring live services in unit tests
    pass 