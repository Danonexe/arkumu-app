import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService


class TestS3UploadService:
    """Test suite for S3UploadService"""

    def test_init_with_custom_params(self):
        """Test S3UploadService initialization with custom parameters"""
        service = S3UploadService(
            aws_access_key_id='test_key',
            aws_secret_access_key='test_secret',
            region_name='us-west-2',
            bucket_name='test-bucket',
            base_url='https://test.example.com'
        )
        
        assert service.region_name == 'us-west-2'
        assert service.bucket_name == 'test-bucket'
        assert service.base_url == 'https://test.example.com'

    def test_init_with_defaults(self):
        """Test S3UploadService initialization with default parameters"""
        with patch('boto3.client'):
            service = S3UploadService()
            
            assert service.region_name == 'us-east-1'
            assert service.bucket_name == 'arkumu-files'
            assert service.base_url == 'https://s3.amazonaws.com/arkumu-files'

    @patch('boto3.client')
    @patch('os.path.exists')
    def test_upload_file_success(self, mock_exists, mock_boto_client):
        """Test successful file upload"""
        mock_exists.return_value = True
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        success, result = service.upload_file('/path/to/test.txt', 'test.txt')
        
        assert success is True
        assert result == 'https://s3.amazonaws.com/arkumu-files/test.txt'
        
        mock_s3_client.upload_file.assert_called_once_with(
            '/path/to/test.txt',
            'arkumu-files',
            'test.txt',
            ExtraArgs={'ACL': 'public-read'}
        )

    @patch('boto3.client')
    @patch('os.path.exists')
    def test_upload_file_not_found(self, mock_exists, mock_boto_client):
        """Test file upload when file doesn't exist"""
        mock_exists.return_value = False
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        success, result = service.upload_file('/path/to/nonexistent.txt')
        
        assert success is False
        assert result == "File not found: /path/to/nonexistent.txt"
        mock_s3_client.upload_file.assert_not_called()

    @patch('boto3.client')
    @patch('os.path.exists')
    @patch('os.path.basename')
    def test_upload_file_auto_object_name(self, mock_basename, mock_exists, mock_boto_client):
        """Test file upload with automatic object name generation"""
        mock_exists.return_value = True
        mock_basename.return_value = 'auto_name.txt'
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        success, result = service.upload_file('/path/to/file.txt')
        
        assert success is True
        assert result == 'https://s3.amazonaws.com/arkumu-files/auto_name.txt'
        
        mock_s3_client.upload_file.assert_called_once_with(
            '/path/to/file.txt',
            'arkumu-files',
            'auto_name.txt',
            ExtraArgs={'ACL': 'public-read'}
        )

    @patch('boto3.client')
    @patch('os.path.exists')
    def test_upload_file_with_extra_args(self, mock_exists, mock_boto_client):
        """Test file upload with custom extra arguments"""
        mock_exists.return_value = True
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        extra_args = {'ContentType': 'text/plain', 'ACL': 'private'}
        service = S3UploadService()
        success, result = service.upload_file('/path/to/test.txt', 'test.txt', extra_args)
        
        assert success is True
        
        mock_s3_client.upload_file.assert_called_once_with(
            '/path/to/test.txt',
            'arkumu-files',
            'test.txt',
            ExtraArgs=extra_args
        )

    @patch('boto3.client')
    @patch('os.path.exists')
    def test_upload_file_client_error(self, mock_exists, mock_boto_client):
        """Test file upload with S3 client error"""
        mock_exists.return_value = True
        mock_s3_client = Mock()
        mock_s3_client.upload_file.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket does not exist'}},
            'upload_file'
        )
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        success, result = service.upload_file('/path/to/test.txt', 'test.txt')
        
        assert success is False
        assert 'NoSuchBucket' in result

    @patch('boto3.client')
    @patch('os.path.isdir')
    @patch('os.walk')
    def test_upload_files_from_directory_success(self, mock_walk, mock_isdir, mock_boto_client):
        """Test successful directory upload"""
        mock_isdir.return_value = True
        mock_walk.return_value = [
            ('/test/dir', [], ['file1.txt', 'file2.txt'])
        ]
        
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        
        # Mock the upload_file method
        def mock_upload_file(file_path, object_name):
            return True, f"https://s3.amazonaws.com/arkumu-files/{object_name}"
        
        service.upload_file = Mock(side_effect=mock_upload_file)
        
        results = service.upload_files_from_directory('/test/dir', prefix='uploads')
        
        assert len(results) == 2
        assert '/test/dir/file1.txt' in results
        assert '/test/dir/file2.txt' in results

    @patch('boto3.client')
    @patch('os.path.isdir')
    def test_upload_files_from_directory_not_found(self, mock_isdir, mock_boto_client):
        """Test directory upload when directory doesn't exist"""
        mock_isdir.return_value = False
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        results = service.upload_files_from_directory('/nonexistent/dir')
        
        assert results == {}

    @patch('boto3.client')
    @patch('os.path.isdir')
    @patch('os.walk')
    def test_upload_files_non_recursive(self, mock_walk, mock_isdir, mock_boto_client):
        """Test directory upload with recursive=False"""
        mock_isdir.return_value = True
        mock_walk.return_value = [
            ('/test/dir', ['subdir'], ['file1.txt']),
            ('/test/dir/subdir', [], ['file2.txt'])
        ]
        
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client
        
        service = S3UploadService()
        
        # Mock the upload_file method
        def mock_upload_file(file_path, object_name):
            return True, f"https://s3.amazonaws.com/arkumu-files/{object_name}"
        
        service.upload_file = Mock(side_effect=mock_upload_file)
        
        results = service.upload_files_from_directory('/test/dir', recursive=False)
        
        # Should only upload files from the top directory
        assert len(results) == 1
        assert '/test/dir/file1.txt' in results

    @patch('os.path.exists')
    def test_resolve_file_path_found(self, mock_exists):
        """Test file path resolution when file exists"""
        def mock_exists_side_effect(path):
            return path == '/base/dir/files/test.txt'
        
        mock_exists.side_effect = mock_exists_side_effect
        
        service = S3UploadService()
        result = service.resolve_file_path('/base/dir', 'test.txt')
        
        assert result == '/base/dir/files/test.txt'

    @patch('os.path.exists')
    def test_resolve_file_path_not_found(self, mock_exists):
        """Test file path resolution when file doesn't exist"""
        mock_exists.return_value = False
        
        service = S3UploadService()
        result = service.resolve_file_path('/base/dir', 'nonexistent.txt')
        
        # Should return the first candidate path
        expected = os.path.join('/base/dir', 'nonexistent.txt')
        assert result == expected

    @patch('os.path.exists')
    def test_resolve_file_path_with_cleaning(self, mock_exists):
        """Test file path resolution with path cleaning"""
        def mock_exists_side_effect(path):
            return path == '/base/dir/clean/path.txt'
        
        mock_exists.side_effect = mock_exists_side_effect
        
        service = S3UploadService()
        result = service.resolve_file_path('/base/dir', '  /clean\\path.txt  ')
        
        assert result == '/base/dir/clean/path.txt'

    def test_resolve_file_path_candidates(self):
        """Test that resolve_file_path tries multiple candidate paths"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            
            service = S3UploadService()
            service.resolve_file_path('/base/dir', 'test.txt')
            
            # Should try multiple candidate paths
            expected_calls = [
                '/base/dir/test.txt',
                '/base/dir/files/test.txt', 
                '/base/dir/../files/test.txt'
            ]
            
            actual_calls = [call[0][0] for call in mock_exists.call_args_list]
            for expected_path in expected_calls:
                assert expected_path in actual_calls


@pytest.mark.integration
class TestS3UploadServiceIntegration:
    """Integration tests for S3UploadService with moto"""

    def test_upload_with_moto(self, mock_s3_service):
        """Test file upload using moto S3 mock"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write('test content')
            tmp_file_path = tmp_file.name
        
        try:
            service = mock_s3_service
            success, result = service.upload_file(tmp_file_path, 'test-upload.txt')
            
            assert success is True
            assert 'test-upload.txt' in result
        finally:
            os.unlink(tmp_file_path)

    def test_upload_directory_with_moto(self, mock_s3_service):
        """Test directory upload using moto S3 mock"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test files
            test_files = ['file1.txt', 'file2.txt']
            for filename in test_files:
                file_path = os.path.join(tmp_dir, filename)
                with open(file_path, 'w') as f:
                    f.write(f'content of {filename}')
            
            service = mock_s3_service
            results = service.upload_files_from_directory(tmp_dir, prefix='test-upload')
            
            assert len(results) == 2
            for filename in test_files:
                file_path = os.path.join(tmp_dir, filename)
                assert file_path in results
                assert 'test-upload' in results[file_path]