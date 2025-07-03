import os
import json
import logging
import pytest

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy
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
    Test import using real CSV files with file path columns.
    All data is imported as literals without relationship resolution.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_DIR=/path/to/csv/dir FILE_COLUMNS_CONFIG=/path/to/file_columns.json FILES_BASE_DIR=/path/to/files pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/importer_real_data/test_importer_workflow_with_real_data.py::test_import_with_file_paths -v --csv-dir=/path/to/csv/dir --file-columns-config=/path/to/file_columns.json --files-base-dir=/path/to/files
    """
    # First check environment variables
    csv_dir = os.environ.get('CSV_DIR')
    file_columns_config_path = os.environ.get('FILE_COLUMNS_CONFIG')
    relationship_config_path = os.environ.get('RELATIONSHIP_CONFIG')  # Legacy - no longer used
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
                relationship_config_path = arg.split('=', 1)[1]  # Legacy - no longer used
            elif arg == '--relationship-config' and i+1 < len(sys.argv):
                relationship_config_path = sys.argv[i+1]  # Legacy - no longer used
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
    print(f"\nStarting import from {csv_dir} (using SmartBulkUpdater - Legacy Version)")
    print(f"Files base directory: {files_base_dir}")
    print(f"Note: All data will be imported with full triple creation using SmartBulkUpdater (Legacy):")
    print(f"  ✅ Standard bulk operations")
    print(f"  ✅ Multi-value detection and splitting")
    print(f"  ✅ Efficient resource and triple handling")
    
    stats = ImportWorkflowService.import_csv_directory(
        directory_path=csv_dir,
        institution="TEST",
        base_uri="http://test.arkumu.org/data",
        delimiter=";",
        has_quoted_fields=True,
        relationship_config_path=relationship_config_path,
        file_columns=file_columns,
        files_base_directory=files_base_dir,
        upload_service=upload_service,
        use_smart_updater=True,
        use_polars=False,  # 🚀 USE LEGACY SMARTBULKUPDATER VERSION!
        update_strategy=UpdateStrategy.SKIP_EXISTING,
        link_row_cells=True
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
    print(f"Data imported with SmartBulkUpdater, including structural and linking triples.")
    
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
    assert new_triples > 0, "No triples were created. SmartBulkUpdater should create structural and linking triples."
    
    # If file columns were specified, check that files were uploaded
    if any(file_columns.values()):
        assert stats.get('files_uploaded', 0) > 0, "No files were uploaded"
        assert file_url_triples.count() > 0, "No file URL triples were created"
    
    # Query and display the first row of the first dataset
    print(f"\n🔍 FIRST ROW ANALYSIS:")
    
    # Debug: Show what resources were actually created
    print(f"\n🔍 DEBUG - Analyzing created resources:")
    print(f"Total resources in database: {Resource.objects.count()}")
    
    # Show sample of IRI resources
    iri_resources = Resource.objects.filter(resource_type="IRI").order_by('uri')[:10]
    print(f"Sample IRI resources ({iri_resources.count()} total):")
    for res in iri_resources:
        print(f"  - {res.uri}")
    
    # Show sample of LITERAL resources  
    literal_resources = Resource.objects.filter(resource_type="LITERAL").order_by('id')[:5]
    print(f"\nSample LITERAL resources ({Resource.objects.filter(resource_type='LITERAL').count()} total):")
    for res in literal_resources:
        value_preview = res.value[:30] + "..." if res.value and len(res.value) > 30 else res.value
        print(f"  - {res.name}: {value_preview}")
    
    # Get the first dataset (alphabetically)
    first_csv_file = sorted(csv_files)[0]
    first_dataset_name = os.path.splitext(first_csv_file)[0]
    
    print(f"\n📋 Examining first row of dataset: {first_dataset_name}")
    
    # Debug: Try different URI patterns
    dataset_uri_patterns = [
        f"http://test.arkumu.org/data/TEST/datasets/{first_dataset_name}/",
        f"http://test.arkumu.org/data/TEST/datasets/{first_dataset_name}",
        f"http://test.arkumu.org/data/datasets/{first_dataset_name}/",
        f"http://test.arkumu.org/data/datasets/{first_dataset_name}",
    ]
    
    cell_resources = None
    used_pattern = None
    
    for pattern in dataset_uri_patterns:
        test_resources = Resource.objects.filter(
            uri__startswith=pattern,
            resource_type="IRI"
        )
        print(f"Pattern '{pattern}': {test_resources.count()} matches")
        if test_resources.exists() and cell_resources is None:
            cell_resources = test_resources.order_by('uri')
            used_pattern = pattern
            break
    
    if cell_resources and cell_resources.exists():
        print(f"\n✅ Found {cell_resources.count()} cell resources using pattern: {used_pattern}")
        
        # Show first few cell URIs
        print("First few cell URIs:")
        for cell in cell_resources[:5]:
            print(f"  - {cell.uri}")
        
        # Extract row IDs from URIs and get the first one
        row_ids = set()
        for cell in cell_resources:
            # URI format: .../datasets/{dataset}/{column}/{row_id}
            uri_parts = cell.uri.split('/')
            if len(uri_parts) >= 3:
                row_id = uri_parts[-1]
                row_ids.add(row_id)
        
        if row_ids:
            first_row_id = sorted(row_ids)[0]
            print(f"\n📍 First row ID: {first_row_id}")
            print(f"All row IDs: {sorted(list(row_ids))[:10]}...")  # Show first 10
            
            # Get all cells for this row
            first_row_cells = Resource.objects.filter(
                uri__startswith=used_pattern,
                uri__endswith=f"/{first_row_id}",
                resource_type="IRI"
            ).order_by('uri')
            
            print(f"\n📊 Found {first_row_cells.count()} cells in first row:")
            
            # For each cell, get its value through triples
            for cell in first_row_cells:
                # Extract column name from URI
                uri_parts = cell.uri.split('/')
                column_name = uri_parts[-2] if len(uri_parts) >= 2 else "unknown"
                
                # Find the value triple for this cell
                value_triple = Triple.objects.filter(
                    subject=cell,
                    predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
                ).first()
                
                if value_triple:
                    value = value_triple.object.value
                    # Truncate long values for display
                    display_value = value[:50] + "..." if len(value) > 50 else value
                    print(f"  📋 {column_name}: {display_value}")
                    assert value_triple.object.value is not None and value_triple.object.value != "", f"Cell {cell.uri} for column {column_name} should have a value."
                else:
                    print(f"  ❌ {column_name}: <no value found>")
                    assert value_triple is not None, f"No value triple found for cell {cell.uri} (column: {column_name}). SmartBulkUpdater should create these."
        else:
            print("❌ No row IDs found in dataset")
    else:
        print("❌ No cell resources found for this dataset with any pattern")
        
        # Additional debug: Show what URIs actually exist
        print("\n🔍 Additional debug - All IRI URIs containing the dataset name:")
        dataset_related = Resource.objects.filter(
            uri__icontains=first_dataset_name,
            resource_type="IRI"
        )[:10]
        for res in dataset_related:
            print(f"  - {res.uri}")
    
    print(f"\n✅ SUCCESS: Import completed with SmartBulkUpdater (Legacy)!")
    print(f"📊 {new_resources} resources and {new_triples} triples created")
    print(f"🔗 Data imported with SmartBulkUpdater (Legacy), including structural, value, and linking triples.")




