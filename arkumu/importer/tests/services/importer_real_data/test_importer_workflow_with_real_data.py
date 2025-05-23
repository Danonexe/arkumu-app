import os
import json
import logging
import pytest
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.conf import settings

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService
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


class ImportWorkflowWithRealDataTest(TestCase):
    """Test the import workflow with real data and file path handling"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data directory and files"""
        super().setUpClass()
        
        # Create a temporary directory for test data
        cls.test_data_dir = tempfile.mkdtemp()
        
        # Create test CSV files
        cls._create_test_csv_files()
        
        # Create test files to be referenced in CSVs
        cls._create_test_files()
        
        # Create file columns configuration
        cls.file_columns_config = {
            "artifacts": ["image_path", "document_path"],
            "people": ["photo_path"]
        }
        
        # Save configuration to file
        cls.config_path = os.path.join(cls.test_data_dir, "file_columns_config.json")
        with open(cls.config_path, 'w') as f:
            json.dump(cls.file_columns_config, f, indent=2)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data"""
        super().tearDownClass()
        
        # Remove temporary directory
        shutil.rmtree(cls.test_data_dir)
    
    @classmethod
    def _create_test_csv_files(cls):
        """Create test CSV files for import testing"""
        # Create artifacts.csv
        artifacts_csv = os.path.join(cls.test_data_dir, "artifacts.csv")
        with open(artifacts_csv, 'w') as f:
            f.write("id;name;description;image_path;document_path\n")
            f.write("1;Artifact 1;A test artifact;images/artifact1.jpg;documents/artifact1.pdf\n")
            f.write("2;Artifact 2;Another test artifact;images/artifact2.jpg;documents/artifact2.pdf\n")
            f.write("3;Artifact 3;Third test artifact;images/artifact3.jpg;\n")
        
        # Create people.csv
        people_csv = os.path.join(cls.test_data_dir, "people.csv")
        with open(people_csv, 'w') as f:
            f.write("id;name;age;photo_path\n")
            f.write("1;John Doe;30;images/john.jpg\n")
            f.write("2;Jane Smith;25;images/jane.jpg\n")
            f.write("3;Bob Johnson;40;\n")
        
        # Create artifact_people.csv (relationship table)
        rel_csv = os.path.join(cls.test_data_dir, "artifact_people.csv")
        with open(rel_csv, 'w') as f:
            f.write("id;artifact_id;person_id;role\n")
            f.write("1;1;1;Creator\n")
            f.write("2;1;2;Owner\n")
            f.write("3;2;2;Creator\n")
            f.write("4;3;3;Owner\n")
    
    @classmethod
    def _create_test_files(cls):
        """Create test files to be referenced in CSVs"""
        # Create directories
        os.makedirs(os.path.join(cls.test_data_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(cls.test_data_dir, "documents"), exist_ok=True)
        
        # Create image files
        for filename in ["artifact1.jpg", "artifact2.jpg", "artifact3.jpg", "john.jpg", "jane.jpg"]:
            with open(os.path.join(cls.test_data_dir, "images", filename), 'w') as f:
                f.write(f"Mock image content for {filename}")
        
        # Create document files
        for filename in ["artifact1.pdf", "artifact2.pdf"]:
            with open(os.path.join(cls.test_data_dir, "documents", filename), 'w') as f:
                f.write(f"Mock PDF content for {filename}")
    
    def setUp(self):
        """Set up for each test"""
        # Create mock upload service
        self.upload_service = MockUploadService()
        
        # Create relationship config
        self.relationship_config = {
            "artifact_people": [
                {"column": "artifact_id", "target_table": "artifacts"},
                {"column": "person_id", "target_table": "people"}
            ]
        }
        
        # Save relationship config to file
        self.rel_config_path = os.path.join(self.test_data_dir, "relationship_config.json")
        with open(self.rel_config_path, 'w') as f:
            json.dump(self.relationship_config, f, indent=2)
    
    def test_single_csv_import_with_file_paths(self):
        """Test importing a single CSV with file paths"""
        # Import artifacts.csv
        csv_path = os.path.join(self.test_data_dir, "artifacts.csv")
        
        stats = ImportWorkflowService.import_csv(
            csv_path=csv_path,
            institution="TEST",
            base_uri="http://test.arkumu.org/data",
            delimiter=";",
            has_quoted_fields=False,
            file_columns=self.file_columns_config["artifacts"],
            files_base_directory=self.test_data_dir,
            upload_service=self.upload_service
        )
        
        # Check stats
        self.assertIn("resources_created", stats)
        self.assertIn("triples_created", stats)
        self.assertIn("files_uploaded", stats)
        
        # Check that files were uploaded
        self.assertEqual(stats["files_uploaded"], 5)  # 3 images + 2 documents
        
        # Check that resources were created
        dataset_uri = "http://test.arkumu.org/data/datasets/artifacts"
        self.assertTrue(Resource.objects.filter(uri=dataset_uri).exists())
        
        # Check that triples with file URLs were created
        image_triples = Triple.objects.filter(
            predicate__uri="http://purl.org/dc/terms/hasFormat",
            object__value__startswith="http://mock-s3"
        )
        self.assertGreater(image_triples.count(), 0)
    
    def test_directory_import_with_file_paths(self):
        """Test importing a directory of CSVs with file paths"""
        stats = ImportWorkflowService.import_csv_directory(
            directory_path=self.test_data_dir,
            institution="TEST",
            base_uri="http://test.arkumu.org/data",
            delimiter=";",
            has_quoted_fields=False,
            relationship_config_path=self.rel_config_path,
            file_columns=self.file_columns_config,
            files_base_directory=self.test_data_dir,
            upload_service=self.upload_service
        )
        
        # Check stats
        self.assertIn("files_processed", stats)
        self.assertIn("resources_created", stats)
        self.assertIn("triples_created", stats)
        self.assertIn("files_uploaded", stats)
        self.assertIn("relationships_created", stats)
        
        # Check that files were processed
        self.assertEqual(stats["files_processed"], 3)  # 3 CSV files
        
        # Check that files were uploaded
        self.assertEqual(stats["files_uploaded"], 7)  # 5 images + 2 documents
        
        # Check that resources were created for all datasets
        datasets = ["artifacts", "people", "artifact_people"]
        for dataset in datasets:
            dataset_uri = f"http://test.arkumu.org/data/datasets/{dataset}"
            self.assertTrue(Resource.objects.filter(uri=dataset_uri).exists())
        
        # Check that relationships were created
        self.assertGreater(stats["relationships_created"], 0)
    
    def test_resolve_file_path(self):
        """Test file path resolution"""
        # Test with relative path
        path = "images/artifact1.jpg"
        resolved = ImportWorkflowService._resolve_file_path(self.test_data_dir, path)
        expected = os.path.join(self.test_data_dir, path)
        self.assertEqual(resolved, expected)
        self.assertTrue(os.path.exists(resolved))
        
        # Test with Windows-style path
        path = "images\\artifact2.jpg"
        resolved = ImportWorkflowService._resolve_file_path(self.test_data_dir, path)
        expected = os.path.join(self.test_data_dir, "images", "artifact2.jpg")
        self.assertEqual(resolved, expected)
        self.assertTrue(os.path.exists(resolved))
        
        # Test with non-existent file
        path = "images/nonexistent.jpg"
        resolved = ImportWorkflowService._resolve_file_path(self.test_data_dir, path)
        self.assertFalse(os.path.exists(resolved))

@pytest.mark.django_db
def test_import_with_file_paths():
    """
    Test import using real CSV files with file path columns.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_DIR=/path/to/csv/dir FILE_COLUMNS_CONFIG=/path/to/file_columns.json FILES_BASE_DIR=/path/to/files pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v --csv-dir=/path/to/csv/dir --file-columns-config=/path/to/file_columns.json --files-base-dir=/path/to/files
    """
    # First check environment variables
    csv_dir = os.environ.get('CSV_DIR')
    file_columns_config_path = os.environ.get('FILE_COLUMNS_CONFIG')
    files_base_dir = os.environ.get('FILES_BASE_DIR')
    
    # If not found, check command line arguments
    if not csv_dir or not file_columns_config_path:
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

@pytest.mark.django_db
def test_import_single_csv_with_file_paths():
    """
    Test import using a single real CSV file with file path columns.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_PATH=/path/to/file.csv FILE_COLUMNS=/path/to/file_columns.json FILES_BASE_DIR=/path/to/files pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_single_csv_with_file_paths -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_single_csv_with_file_paths -v --csv-path=/path/to/file.csv --file-columns=column1,column2 --files-base-dir=/path/to/files
    """
    # First check environment variables
    csv_path = os.environ.get('CSV_PATH')
    file_columns_str = os.environ.get('FILE_COLUMNS')
    files_base_dir = os.environ.get('FILES_BASE_DIR')
    
    # If not found, check command line arguments
    if not csv_path:
        import sys
        
        for i, arg in enumerate(sys.argv):
            if arg.startswith('--csv-path='):
                csv_path = arg.split('=', 1)[1]
            elif arg == '--csv-path' and i+1 < len(sys.argv):
                csv_path = sys.argv[i+1]
            elif arg.startswith('--file-columns='):
                file_columns_str = arg.split('=', 1)[1]
            elif arg == '--file-columns' and i+1 < len(sys.argv):
                file_columns_str = sys.argv[i+1]
            elif arg.startswith('--files-base-dir='):
                files_base_dir = arg.split('=', 1)[1]
            elif arg == '--files-base-dir' and i+1 < len(sys.argv):
                files_base_dir = sys.argv[i+1]
    
    if not csv_path:
        pytest.skip("CSV file path not provided. Use CSV_PATH environment variable or --csv-path option.")
    
    # Parse file columns
    file_columns = []
    if file_columns_str:
        if file_columns_str.startswith('[') and file_columns_str.endswith(']'):
            # JSON array format
            try:
                file_columns = json.loads(file_columns_str)
            except json.JSONDecodeError:
                file_columns = file_columns_str.strip('[]').split(',')
        else:
            # Comma-separated list
            file_columns = [col.strip() for col in file_columns_str.split(',')]
    
    # If files_base_dir not specified, use directory of CSV file
    if not files_base_dir and csv_path:
        files_base_dir = os.path.dirname(csv_path)
    
    # Check if CSV file exists
    if not os.path.isfile(csv_path):
        pytest.skip(f"CSV file not found: {csv_path}")
    
    print(f"Using CSV file: {csv_path}")
    print(f"File columns: {file_columns}")
    print(f"Files base directory: {files_base_dir}")
    
    # Create mock upload service
    upload_service = MockUploadService()
    
    # Count initial resources and triples
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    # Extract dataset name from file path
    dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
    
    # Run the import
    print(f"\nStarting import of {csv_path} with file path handling")
    
    stats = ImportWorkflowService.import_csv(
        csv_path=csv_path,
        dataset_name=dataset_name,
        institution="TEST",
        base_uri="http://test.arkumu.org/data",
        delimiter=";",
        has_quoted_fields=True,
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
    if file_columns:
        assert stats.get('files_uploaded', 0) > 0, "No files were uploaded"


if __name__ == '__main__':
    unittest.main()
