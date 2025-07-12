import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from django.contrib.auth import get_user_model
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.mapping.mapping_import_service import MappingImportService

User = get_user_model()


@pytest.fixture
def mock_s3_service():
    """Mock S3UploadService for testing."""
    mock_service = Mock()
    mock_service.s3_client = Mock()
    mock_service.bucket_name = 'test-bucket'
    return mock_service


@pytest.fixture
def mapping_import_service(mock_s3_service):
    """Create MappingImportService with mocked S3 service."""
    return MappingImportService(s3_service=mock_s3_service)


@pytest.fixture
def sample_mapping_json():
    """Sample valid mapping JSON data."""
    return {
        "name": "Test Product Mapping",
        "description": "Test mapping for products",
        "mapping_config": {
            "datasets": ["products"],
            "columns": {
                "product_id": {"type": "anchor", "cidoc_property": "P1_is_identified_by"},
                "product_name": {"type": "regular", "cidoc_property": "P1_is_identified_by"}
            }
        },
        "source_datasets": ["products"],
        "metadata": {
            "exported_at": "2025-07-12T10:30:00Z",
            "exported_by": "test@example.com",
            "version": "1.0"
        }
    }


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


class TestMappingImportService:
    """Test cases for MappingImportService."""
    
    def test_init_with_s3_service(self, mock_s3_service):
        """Test initialization with provided S3 service."""
        service = MappingImportService(s3_service=mock_s3_service)
        assert service.s3_service == mock_s3_service
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.S3UploadService')
    def test_init_without_s3_service(self, mock_s3_class):
        """Test initialization without S3 service creates new instance."""
        service = MappingImportService()
        mock_s3_class.assert_called_once()
        assert service.s3_service is not None
    
    def test_list_available_mapping_files_success(self, mapping_import_service, mock_s3_service):
        """Test successful listing of mapping files."""
        # Mock S3 response with proper datetime objects
        mock_response = {
            'Contents': [
                {
                    'Key': 'org1/metadata/mapping1.json',
                    'Size': 1024,
                    'LastModified': datetime(2025, 7, 12, 10, 30, 0)
                },
                {
                    'Key': 'org1/metadata/mapping2.json',
                    'Size': 2048,
                    'LastModified': datetime(2025, 7, 12, 11, 0, 0)
                },
                {
                    'Key': 'org1/metadata/data.csv',  # Should be filtered out
                    'Size': 512,
                    'LastModified': datetime(2025, 7, 12, 9, 0, 0)
                }
            ]
        }
        mock_s3_service.s3_client.list_objects_v2.return_value = mock_response
        
        result = mapping_import_service.list_available_mapping_files('org1')
        
        # Verify S3 call
        mock_s3_service.s3_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket',
            Prefix='org1/metadata/'
        )
        
        # Verify results
        assert len(result) == 2
        assert all(file['name'].endswith('.json') for file in result)
        assert result[0]['name'] == 'mapping2.json'  # Sorted by last modified (newest first)
        assert result[1]['name'] == 'mapping1.json'
    
    def test_list_available_mapping_files_no_contents(self, mapping_import_service, mock_s3_service):
        """Test listing when no files exist."""
        mock_s3_service.s3_client.list_objects_v2.return_value = {}
        
        result = mapping_import_service.list_available_mapping_files('org1')
        
        assert result == []
    
    def test_list_available_mapping_files_s3_error(self, mapping_import_service, mock_s3_service):
        """Test handling of S3 errors."""
        mock_s3_service.s3_client.list_objects_v2.side_effect = Exception("S3 connection error")
        
        result = mapping_import_service.list_available_mapping_files('org1')
        
        assert result == []
    
    def test_validate_mapping_file_valid(self, mapping_import_service, sample_mapping_json):
        """Test validation of valid mapping file."""
        file_content = json.dumps(sample_mapping_json)
        
        is_valid, message, data = mapping_import_service.validate_mapping_file(file_content)
        
        assert is_valid is True
        assert message == "Valid mapping file"
        assert data == sample_mapping_json
    
    def test_validate_mapping_file_invalid_json(self, mapping_import_service):
        """Test validation of invalid JSON."""
        file_content = "invalid json content"
        
        is_valid, message, data = mapping_import_service.validate_mapping_file(file_content)
        
        assert is_valid is False
        assert "Invalid JSON format" in message
        assert data is None
    
    def test_validate_mapping_file_missing_required_fields(self, mapping_import_service):
        """Test validation with missing required fields."""
        invalid_data = {"description": "Missing name and mapping_config"}
        file_content = json.dumps(invalid_data)
        
        is_valid, message, data = mapping_import_service.validate_mapping_file(file_content)
        
        assert is_valid is False
        assert "Missing required fields" in message
        assert data is None
    
    def test_validate_mapping_file_invalid_name_type(self, mapping_import_service, sample_mapping_json):
        """Test validation with invalid name type."""
        sample_mapping_json['name'] = 123  # Should be string
        file_content = json.dumps(sample_mapping_json)
        
        is_valid, message, data = mapping_import_service.validate_mapping_file(file_content)
        
        assert is_valid is False
        assert "Field 'name' must be a non-empty string" in message
        assert data is None
    
    def test_validate_mapping_file_too_large(self, mapping_import_service, sample_mapping_json):
        """Test validation with oversized mapping config."""
        # Create a large mapping config (>1MB)
        large_config = {"data": "x" * (1024 * 1024 + 1)}
        sample_mapping_json['mapping_config'] = large_config
        file_content = json.dumps(sample_mapping_json)
        
        is_valid, message, data = mapping_import_service.validate_mapping_file(file_content)
        
        assert is_valid is False
        assert "Mapping configuration is too large" in message
        assert data is None
    
    @pytest.mark.django_db
    def test_import_mapping_from_json_success(self, mapping_import_service, sample_mapping_json, user):
        """Test successful mapping import."""
        success, message, mapping = mapping_import_service.import_mapping_from_json(
            sample_mapping_json, 'org1', user
        )
        
        assert success is True
        assert "Successfully imported mapping" in message
        assert mapping is not None
        assert mapping.name == sample_mapping_json['name']
        assert mapping.organization_id == 'org1'
        assert mapping.created_by == user
        assert mapping.validation_status == 'draft'
    
    @pytest.mark.django_db
    def test_import_mapping_from_json_name_conflict(self, mapping_import_service, sample_mapping_json, user):
        """Test import with name conflict resolution."""
        original_name = sample_mapping_json['name']
        
        # Create existing mapping with same name
        Mapping.objects.create(
            name=original_name,
            organization_id='org1',
            mapping_config={},
            created_by=user
        )
        
        success, message, mapping = mapping_import_service.import_mapping_from_json(
            sample_mapping_json, 'org1', user
        )
        
        assert success is True
        assert mapping.name != original_name
        assert "(Imported 1)" in mapping.name
    
    @pytest.mark.django_db
    def test_batch_import_mappings_success(self, mapping_import_service, mock_s3_service, sample_mapping_json, user):
        """Test successful batch import."""
        file_keys = ['org1/metadata/mapping1.json', 'org1/metadata/mapping2.json']
        
        # Mock S3 get_object responses
        mock_responses = []
        for i, key in enumerate(file_keys):
            mapping_data = sample_mapping_json.copy()
            mapping_data['name'] = f"Test Mapping {i+1}"
            
            mock_response = Mock()
            mock_body = Mock()
            mock_body.read.return_value = json.dumps(mapping_data).encode('utf-8')
            mock_response.__getitem__ = Mock(return_value=mock_body)  # Handle ['Body'] access
            mock_responses.append(mock_response)
        
        mock_s3_service.s3_client.get_object.side_effect = mock_responses
        
        results = mapping_import_service.batch_import_mappings(file_keys, 'org1', user)
        
        assert results['total_files'] == 2
        assert len(results['successful_imports']) == 2
        assert len(results['failed_imports']) == 0
        assert len(results['imported_mappings']) == 2
    
    @pytest.mark.django_db
    def test_batch_import_mappings_partial_failure(self, mapping_import_service, mock_s3_service, sample_mapping_json, user):
        """Test batch import with some failures."""
        file_keys = ['org1/metadata/valid.json', 'org1/metadata/invalid.json']
        
        # Mock S3 responses - one valid, one invalid
        valid_response = Mock()
        valid_body = Mock()
        valid_body.read.return_value = json.dumps(sample_mapping_json).encode('utf-8')
        valid_response.__getitem__ = Mock(return_value=valid_body)
        
        invalid_response = Mock()
        invalid_body = Mock()
        invalid_body.read.return_value = b"invalid json"
        invalid_response.__getitem__ = Mock(return_value=invalid_body)
        
        mock_s3_service.s3_client.get_object.side_effect = [valid_response, invalid_response]
        
        results = mapping_import_service.batch_import_mappings(file_keys, 'org1', user)
        
        assert results['total_files'] == 2
        assert len(results['successful_imports']) == 1
        assert len(results['failed_imports']) == 1
        assert len(results['imported_mappings']) == 1
    
    def test_batch_import_mappings_s3_error(self, mapping_import_service, mock_s3_service, user):
        """Test batch import with S3 access error."""
        file_keys = ['org1/metadata/mapping1.json']
        mock_s3_service.s3_client.get_object.side_effect = Exception("S3 access denied")
        
        results = mapping_import_service.batch_import_mappings(file_keys, 'org1', user)
        
        assert results['total_files'] == 1
        assert len(results['successful_imports']) == 0
        assert len(results['failed_imports']) == 1
        assert "S3 access denied" in results['failed_imports'][0]['error']
    
    def test_download_file_content_success(self, mapping_import_service, mock_s3_service):
        """Test successful file content download."""
        file_content = "test file content"
        mock_response = Mock()
        mock_body = Mock()
        mock_body.read.return_value = file_content.encode('utf-8')
        mock_response.__getitem__ = Mock(return_value=mock_body)
        mock_s3_service.s3_client.get_object.return_value = mock_response
        
        success, content = mapping_import_service.download_file_content('test/file.json')
        
        assert success is True
        assert content == file_content
        mock_s3_service.s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test/file.json'
        )
    
    def test_download_file_content_error(self, mapping_import_service, mock_s3_service):
        """Test file download with S3 error."""
        mock_s3_service.s3_client.get_object.side_effect = Exception("File not found")
        
        success, content = mapping_import_service.download_file_content('test/missing.json')
        
        assert success is False
        assert "File not found" in content