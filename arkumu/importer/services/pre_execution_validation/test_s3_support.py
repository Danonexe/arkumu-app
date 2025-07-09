"""
Test S3 support in the pre-execution validator.

This test verifies that the validator can handle S3 file paths correctly
without requiring actual S3 connectivity.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from arkumu.importer.services.pre_execution_validation.pre_execution_validator import PreExecutionValidator
from arkumu.importer.services.pre_execution_validation.validation_result import ValidationMode


class TestS3Support:
    """Test S3 support in PreExecutionValidator"""
    
    def test_s3_path_detection(self):
        """Test that S3 paths are correctly identified"""
        validator = PreExecutionValidator()
        
        # S3 paths (should return True)
        s3_paths = [
            "metadata/AkteurIn.csv",
            "folder/subfolder/file.csv",
            "AkteurIn.csv",
            "data/files/test.json",
            "file.csv"
        ]
        
        for path in s3_paths:
            assert validator._is_s3_path(path) == True, f"Path {path} should be detected as S3"
        
        # Local paths (should return False)
        local_paths = [
            "/home/user/file.csv",
            "./file.csv",
            "../data/file.csv",
            "~/file.csv",
            "C:\\Users\\file.csv"
        ]
        
        for path in local_paths:
            assert validator._is_s3_path(path) == False, f"Path {path} should not be detected as S3"
    
    def test_s3_file_size_detection(self):
        """Test that S3 file sizes are correctly detected"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test S3 file
        size = validator._get_file_size("metadata/AkteurIn.csv", "rsh")
        assert size == 1024
        
        # Test local file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write("test,data\n1,2\n3,4\n")
            tmp_file_path = tmp_file.name
        
        try:
            size = validator._get_file_size(tmp_file_path, "rsh")
            assert size > 0
        finally:
            os.unlink(tmp_file_path)
    
    def test_s3_file_existence_check(self):
        """Test that S3 file existence is correctly checked"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test existing file
        exists, size = validator._check_s3_file_exists("test-bucket", "metadata/AkteurIn.csv")
        assert exists == True
        assert size == 1024
        
        # Test non-existing file
        mock_bucket_service.base_s3_service.s3_client.head_object.side_effect = Exception("Not found")
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        exists, size = validator._check_s3_file_exists("test-bucket", "metadata/NonExisting.csv")
        assert exists == False
        assert size == 0
    
    def test_s3_csv_validation(self):
        """Test S3 CSV file validation"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.get_file_content.return_value = {
            'success': True,
            'content': b'Name,Age,City\nJohn,30,New York\nJane,25,London\n'
        }
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test S3 CSV validation
        result = validator.validate_file_structure("metadata/test.csv", {}, "rsh")
        
        assert result.is_valid == True
        assert result.column_count == 3
        assert result.row_count == 2
        assert result.file_size == 1024
    
    def test_s3_json_validation(self):
        """Test S3 JSON file validation"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.get_file_content.return_value = {
            'success': True,
            'content': b'[{"name": "John", "age": 30}, {"name": "Jane", "age": 25}]'
        }
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test S3 JSON validation
        result = validator.validate_file_structure("metadata/test.json", {}, "rsh")
        
        assert result.is_valid == True
        assert result.column_count == 2
        assert result.row_count == 2
        assert result.file_size == 1024
    
    def test_s3_file_not_found(self):
        """Test handling of S3 file not found"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.base_s3_service.s3_client.head_object.side_effect = Exception("Not found")
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test file not found
        result = validator.validate_file_structure("metadata/missing.csv", {}, "rsh")
        
        assert result.is_valid == False
        assert len(result.issues) > 0
        assert "File not found" in result.issues[0].message
    
    def test_s3_file_read_error(self):
        """Test handling of S3 file read errors"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        mock_bucket_service.get_file_content.return_value = {
            'success': False
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test file read error
        result = validator.validate_file_structure("metadata/error.csv", {}, "rsh")
        
        assert result.is_valid == False
        assert len(result.issues) > 0
        assert "Cannot read file from S3" in result.issues[0].message
    
    def test_column_extraction_from_s3(self):
        """Test column extraction from S3 files"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.get_file_content.return_value = {
            'success': True,
            'content': b'Name,Age,City\nJohn,30,New York\n'
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Test column extraction from S3 CSV
        columns = validator._extract_file_columns("metadata/test.csv", "rsh")
        
        assert columns == ['Name', 'Age', 'City']
        
        # Test column extraction from S3 JSON
        mock_bucket_service.get_file_content.return_value = {
            'success': True,
            'content': b'[{"name": "John", "age": 30, "city": "New York"}]'
        }
        
        columns = validator._extract_file_columns("metadata/test.json", "rsh")
        
        assert columns == ['name', 'age', 'city']
    
    def test_mixed_local_and_s3_files(self):
        """Test handling of mixed local and S3 files"""
        # Mock bucket service
        mock_bucket_service = Mock()
        mock_bucket_service.get_organization_bucket.return_value = "test-bucket"
        mock_bucket_service.get_file_content.return_value = {
            'success': True,
            'content': b'Name,Age\nJohn,30\n'
        }
        mock_bucket_service.base_s3_service.s3_client.head_object.return_value = {
            'ContentLength': 1024
        }
        
        validator = PreExecutionValidator(bucket_service=mock_bucket_service)
        
        # Create a temporary local file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            tmp_file.write("Name,Age\nJane,25\n")
            tmp_file_path = tmp_file.name
        
        try:
            # Test S3 file
            s3_result = validator.validate_file_structure("metadata/test.csv", {}, "rsh")
            assert s3_result.is_valid == True
            assert s3_result.column_count == 2
            
            # Test local file
            local_result = validator.validate_file_structure(tmp_file_path, {}, "rsh")
            assert local_result.is_valid == True
            assert local_result.column_count == 2
            
        finally:
            os.unlink(tmp_file_path)
    
    def test_encoding_detection(self):
        """Test encoding detection from bytes"""
        validator = PreExecutionValidator()
        
        # Test UTF-8 content
        utf8_content = "Name,Age\nJohn,30\n".encode('utf-8')
        encoding = validator._detect_encoding_from_bytes(utf8_content)
        assert encoding == 'utf-8'
        
        # Test Latin-1 content
        latin1_content = "Name,Age\nJöhn,30\n".encode('latin-1')
        encoding = validator._detect_encoding_from_bytes(latin1_content)
        assert encoding in ['utf-8', 'latin-1']  # Fallback logic
    
    def test_delimiter_detection(self):
        """Test delimiter detection from string"""
        validator = PreExecutionValidator()
        
        # Test comma delimiter
        csv_content = "Name,Age,City\nJohn,30,New York\n"
        delimiter = validator._detect_delimiter_from_string(csv_content)
        assert delimiter == ','
        
        # Test semicolon delimiter
        csv_content = "Name;Age;City\nJohn;30;New York\n"
        delimiter = validator._detect_delimiter_from_string(csv_content)
        assert delimiter == ';'
        
        # Test tab delimiter
        csv_content = "Name\tAge\tCity\nJohn\t30\tNew York\n"
        delimiter = validator._detect_delimiter_from_string(csv_content)
        assert delimiter == '\t'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])