import tempfile
import shutil
import pytest
import boto3
from moto import mock_aws
import os
import json
from io import BytesIO
from unittest.mock import Mock, patch


from arkumu.storage.services.upload_service import UploadService
from arkumu.storage.models import UploadSession, S3FileObject

# Use a static bucket name for testing
TEST_BUCKET_NAME = 'test-bucket'
TEST_FOLDER_NAME = 'test-folder'
TEST_ORG_BUCKET_NAME = 'test-org-fuk' # Simulate organization-specific bucket

@pytest.fixture
def mock_s3():
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
        s3.create_bucket(Bucket=TEST_ORG_BUCKET_NAME)
        
        # Configure bucket policy to allow all operations
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadGetObject",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{TEST_BUCKET_NAME}",
                        f"arn:aws:s3:::{TEST_BUCKET_NAME}/*",
                        f"arn:aws:s3:::{TEST_ORG_BUCKET_NAME}",
                        f"arn:aws:s3:::{TEST_ORG_BUCKET_NAME}/*"
                    ]
                }
            ]
        }
        s3.put_bucket_policy(Bucket=TEST_BUCKET_NAME, Policy=json.dumps(bucket_policy))
        s3.put_bucket_policy(Bucket=TEST_ORG_BUCKET_NAME, Policy=json.dumps(bucket_policy))
        
        # Configure CORS
        cors_configuration = {
            'CORSRules': [{
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': ['ETag']
            }]
        }
        s3.put_bucket_cors(Bucket=TEST_BUCKET_NAME, CORSConfiguration=cors_configuration)
        s3.put_bucket_cors(Bucket=TEST_ORG_BUCKET_NAME, CORSConfiguration=cors_configuration)
        yield s3

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests and clean it up afterwards"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_upload_service(mock_s3):
    """Create an UploadService instance with mock settings"""
    service = UploadService(skip_bucket_check=True)
    # Override the bucket names for testing
    service.ingest_bucket = TEST_BUCKET_NAME
    service.production_bucket = TEST_BUCKET_NAME
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    return service

@pytest.fixture
def mock_bucket_service():
    """Mock bucket service for testing organization buckets"""
    service = Mock()
    service.get_organization_bucket.return_value = TEST_ORG_BUCKET_NAME
    service.ensure_organization_bucket_exists.return_value = {'success': True}
    return service

@pytest.fixture
def mock_user():
    """Mock user for testing upload sessions."""
    user = Mock()
    user.username = "test_user"
    user.id = 1
    return user

@pytest.fixture
def mock_upload_session():
    """Create a mock upload session for testing."""
    session = Mock(spec=UploadSession)
    session.id = "test-session-id"
    session.status = "in_progress"
    session.user = Mock()
    session.user.username = "test_user"
    session.folder_name = "test-folder"
    session.total_files = 0
    session.mark_completed = Mock()
    session.mark_failed = Mock()
    session.save = Mock()
    return session

@pytest.fixture
def mock_s3_file_object():
    """Create a mock S3FileObject for testing."""
    file_obj = Mock(spec=S3FileObject)
    file_obj.session = Mock()
    file_obj.session.id = "test-session-id"
    file_obj.file_name = "test.txt"
    file_obj.original_path = "test.txt"
    file_obj.s3_key = "test-folder/test.txt"
    file_obj.mark_completed = Mock()
    file_obj.mark_failed = Mock()
    return file_obj

def test_presigned_post_and_upload(mock_upload_service):
    """Test generating a presigned post URL and uploading a file"""
    # Generate a presigned post URL for a single file
    result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain"
    )
    
    # Check basic presigned URL functionality
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["file_name"] == "test.txt", "File name should be preserved"
    assert result["upload_type"] == "multipart", "Upload type should be multipart by default"
    
    # Test with path prefix
    result_with_prefix = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        path_prefix="folder/subfolder"
    )
    assert result_with_prefix["s3_key"] == "folder/subfolder/test.txt", "S3 key should include the path prefix"

def test_batch_operations_with_organization_bucket(mock_upload_service, mock_bucket_service):
    """Test batch operations with organization-specific bucket"""
    # Patch the bucket service getter to return our mock
    with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_svc:
        mock_bucket_svc.return_value = mock_bucket_service
        
        # Create test files
        files = []
        for i in range(3):
            mock_file = Mock()
            mock_file.name = f"org_test_{i}.txt"
            mock_file.content_type = "text/plain"
            mock_file.size = 100
            mock_file.read.return_value = f"Organization test content {i}".encode()
            files.append(mock_file)
        
        # Test batch upload with organization parameter
        result = mock_upload_service.upload_batch_django_files_optimized(
            uploaded_files=files,
            path_prefix="org-test",
            bucket_name=TEST_ORG_BUCKET_NAME
        )
        
        # Verify the result and bucket usage
        assert result["success"] is True
        assert len(result["results"]) == 3
        mock_bucket_service.get_organization_bucket.assert_not_called()  # Should use the bucket name directly

def test_upload_session_tracking_with_organization(mock_upload_service, mock_bucket_service, mock_upload_session, mock_s3_file_object):
    """Test upload session tracking with organization-specific bucket"""
    # Patch the bucket service getter
    with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket_svc:
        mock_bucket_svc.return_value = mock_bucket_service
        
        # Patch S3FileObject.create_from_upload
        with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_s3_file_object):
            # Mock file for upload
            mock_file = Mock()
            mock_file.name = "session_org_test.txt"
            mock_file.content_type = "text/plain"
            mock_file.size = 100
            mock_file.read.return_value = b"Session organization test content"
            
            # Set organization in the session
            mock_upload_session.institution = "fuk"
            mock_upload_session.s3_bucket = ""
            
            # Upload with session and organization
            result = mock_upload_service.upload_django_file(
                uploaded_file=mock_file,
                path_prefix="session-org-test",
                bucket_name=TEST_ORG_BUCKET_NAME,
                session=mock_upload_session
            )
            
            # Verify the session was updated with organization bucket
            assert result["success"] is True
            mock_upload_session.save.assert_called()
            mock_s3_file_object.mark_completed.assert_called_once()

def test_multipart_upload_complete_workflow(mock_s3, mock_upload_service, mock_upload_session, mock_s3_file_object):
    """Test a complete multipart upload workflow with session tracking"""
    # Initialize multipart upload
    file_name = "multipart_test.dat"
    path_prefix = "multipart"
    s3_key = f"{path_prefix}/{file_name}"
    
    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type="application/octet-stream",
        path_prefix=path_prefix
    )
    
    assert init_result["success"] is True
    upload_id = init_result["upload_id"]
    
    # Get URLs for parts
    urls_result = mock_upload_service.get_upload_part_urls(
        s3_key=s3_key,
        upload_id=upload_id,
        part_count=2
    )
    
    assert urls_result["success"] is True
    
    # Upload parts
    parts = []
    part_size = 5 * 1024 * 1024  # 5MB
    
    for i, part_url in enumerate(urls_result["presigned_urls"]):
        part_number = part_url["part_number"]
        part_content = b"X" * part_size
        
        # Upload directly with S3 client
        response = mock_s3.upload_part(
            Bucket=TEST_BUCKET_NAME,
            Key=s3_key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=part_content
        )
        
        parts.append({
            "part_number": part_number,
            "etag": response["ETag"]
        })
    
    # Patch S3FileObject creation
    with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_s3_file_object):
        # Complete the upload with session tracking
        complete_result = mock_upload_service.complete_multipart_upload(
            s3_key=s3_key,
            upload_id=upload_id,
            parts=parts,
            session=mock_upload_session
        )
        
        # Verify completion and session tracking
        assert complete_result["success"] is True
        mock_s3_file_object.mark_completed.assert_called_once()

def test_upload_failure_handling(mock_upload_service, mock_upload_session, mock_s3_file_object):
    """Test handling of upload failures with session tracking"""
    # Set up failure scenario
    with patch.object(mock_upload_service.s3_client, 'upload_fileobj', side_effect=Exception("Simulated upload failure")):
        with patch('arkumu.storage.models.S3FileObject.create_from_upload', return_value=mock_s3_file_object):
            # Create test file
            mock_file = Mock()
            mock_file.name = "failing_file.txt"
            mock_file.content_type = "text/plain"
            mock_file.read.return_value = b"This upload will fail"
            
            # Try to upload
            result = mock_upload_service.upload_django_file(
                uploaded_file=mock_file,
                path_prefix="failure-test",
                session=mock_upload_session
            )
            
            # Verify failure was properly tracked
            assert result["success"] is False
            mock_s3_file_object.mark_failed.assert_called_once()
            mock_upload_session.mark_failed.assert_not_called()  # Only mark session failed if all files fail
