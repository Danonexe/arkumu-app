import os
import json
import logging
import pytest

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.triples import Triple

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.DEBUG)
    yield

class MockUploadService:
    """Mock upload service for testing file uploads without S3"""
    
    def __init__(self):
        self.uploaded_files = {}
        
    def upload_file(self, file_path, object_name=None, extra_args=None):
        """Mock file upload that returns a fake URL"""
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        # Use basename as object_name if not provided
        if not object_name:
            object_name = os.path.basename(file_path)
            
        # Store the file path and return a mock URL
        mock_url = f"http://mock-s3.example.com/{object_name}"
        self.uploaded_files[file_path] = mock_url
        return True, mock_url




@pytest.mark.django_db
def test_import_with_file_paths():
    """
    Test import using real CSV files with file path columns and relationship handling.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_DIR=/path/to/csv/dir FILE_COLUMNS_CONFIG=/path/to/file_columns.json RELATIONSHIP_CONFIG=/path/to/relationship_config.json FILES_BASE_DIR=/path/to/files pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v --csv-dir=/path/to/csv/dir --file-columns-config=/path/to/file_columns.json --relationship-config=/path/to/relationship_config.json --files-base-dir=/path/to/files
    """
    # First check environment variables
    csv_dir = os.environ.get('CSV_DIR')
    file_columns_config_path = os.environ.get('FILE_COLUMNS_CONFIG')
    relationship_config_path = os.environ.get('RELATIONSHIP_CONFIG')
    files_base_dir = os.environ.get('FILES_BASE_DIR')
    
    # If not found, check command line arguments
    if not csv_dir:
        import sys
        
        for i, arg in enumerate(sys.argv):
            if arg.startswith('--csv-dir='):
                csv_dir = arg.split('=', 1)[1]
            elif arg == '--csv-dir' and i+1 < len(sys.argv):
                csv_dir = sys.argv[i+1]
            elif arg.startswith('--file-columns-config='):
                file_columns_config_path = arg.split('=', 1)[1]
            elif arg == '--file-columns-config' and i+1 < len(sys.argv):
                file_columns_config_path = sys.argv[i+1]
            elif arg.startswith('--relationship-config='):
                relationship_config_path = arg.split('=', 1)[1]
            elif arg == '--relationship-config' and i+1 < len(sys.argv):
                relationship_config_path = sys.argv[i+1]
            elif arg.startswith('--files-base-dir='):
                files_base_dir = arg.split('=', 1)[1]
            elif arg == '--files-base-dir' and i+1 < len(sys.argv):
                files_base_dir = sys.argv[i+1]
    
    if not csv_dir:
        pytest.skip("CSV directory not provided. Use CSV_DIR environment variable or --csv-dir option.")
    
    # If files_base_dir not specified, use csv_dir
    files_base_dir = files_base_dir or csv_dir
    
    # Load file columns configuration if provided
    file_columns = {}
    if file_columns_config_path and os.path.exists(file_columns_config_path):
        try:
            with open(file_columns_config_path, 'r') as f:
                file_columns = json.load(f)
            print(f"Loaded file columns configuration from {file_columns_config_path}")
            print(f"File columns config: {json.dumps(file_columns, indent=2)}")
        except Exception as e:
            print(f"Error loading file columns configuration: {e}")
    else:
        print("No file columns configuration provided, using empty configuration")
    
    # Check if CSV directory exists
    if not os.path.isdir(csv_dir):
        pytest.skip(f"CSV directory not found: {csv_dir}")
    
    # List CSV files in directory
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
    if not csv_files:
        pytest.skip(f"No CSV files found in directory: {csv_dir}")
    
    print(f"Found {len(csv_files)} CSV files in {csv_dir}:")
    for csv_file in csv_files:
        print(f"- {csv_file}")
    
    # Create mock upload service
    upload_service = MockUploadService()
    
    # Count initial resources and triples
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    # Run the import
    print(f"\nStarting import from {csv_dir} with file path handling")
    print(f"Files base directory: {files_base_dir}")
    
    stats = ImportWorkflowService.import_csv_directory(
        directory_path=csv_dir,
        institution="TEST",
        base_uri="http://test.arkumu.org/data",
        delimiter=";",
        has_quoted_fields=True,
        relationship_config_path=relationship_config_path,
        file_columns=file_columns,
        files_base_directory=files_base_dir,
        upload_service=upload_service
    )
    
    # Log the statistics
    print(f"\nImport statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Resource creation details
    new_resources = Resource.objects.count() - initial_resource_count
    new_triples = Triple.objects.count() - initial_triple_count
    print(f"\nResource creation:")
    print(f"New resources created: {new_resources}")
    print(f"New triples created: {new_triples}")
    
    # Check for file uploads
    print(f"\nFiles uploaded: {stats.get('files_uploaded', 0)}")
    print(f"Upload errors: {stats.get('upload_errors', 0)}")
    
    # Sample of uploaded files
    if hasattr(upload_service, 'uploaded_files') and upload_service.uploaded_files:
        print(f"\nSample of uploaded files ({len(upload_service.uploaded_files)} total):")
        for i, (file_path, url) in enumerate(list(upload_service.uploaded_files.items())[:5]):
            print(f"- {file_path} → {url}")
        if len(upload_service.uploaded_files) > 5:
            print(f"... and {len(upload_service.uploaded_files) - 5} more")
    
    # Sample of created triples with file URLs
    file_url_triples = Triple.objects.filter(
        predicate__uri="http://purl.org/dc/terms/hasFormat",
        object__value__startswith="http://mock-s3"
    )
    if file_url_triples.exists():
        print(f"\nSample of file URL triples ({file_url_triples.count()} total):")
        for triple in file_url_triples[:5]:
            print(f"- {triple.subject.uri} → {triple.object.value}")
        if file_url_triples.count() > 5:
            print(f"... and {file_url_triples.count() - 5} more")
    
    # Basic assertions
    assert new_resources > 0, "No resources were created"
    assert new_triples > 0, "No triples were created"
    
    # If file columns were specified, check that files were uploaded
    if any(file_columns.values()):
        assert stats.get('files_uploaded', 0) > 0, "No files were uploaded"
        assert file_url_triples.count() > 0, "No file URL triples were created"




