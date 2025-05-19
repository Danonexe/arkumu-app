"""Tests that demonstrate using the JSONMappingImporter with real data files."""

import pytest
import logging
import os
from arkumu.metadata.models import Resource, Triple, ResourceType

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.DEBUG)
    yield

@pytest.mark.django_db
def test_import_with_external_files(external_csv_data, external_mapping_importer):
    """
    Test import using external CSV and mapping files.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_TEST_FILE=/path/to/data.csv MAPPING_TEST_FILE=/path/to/mapping.json pytest arkumu/importer/tests/services/test_with_real_data.py::test_import_with_external_files -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/test_with_real_data.py::test_import_with_external_files -v --external-csv=/path/to/data.csv --external-mapping=/path/to/mapping.json
    """
    # First check environment variables
    csv_path = os.environ.get('CSV_TEST_FILE')
    mapping_path = os.environ.get('MAPPING_TEST_FILE')
    
    # If not found, check command line arguments
    if not csv_path or not mapping_path:
        pytest.importorskip("sys")
        import sys
        
        for i, arg in enumerate(sys.argv):
            if arg.startswith('--external-csv='):
                csv_path = arg.split('=', 1)[1]
            elif arg == '--external-csv' and i+1 < len(sys.argv):
                csv_path = sys.argv[i+1]
            elif arg.startswith('--external-mapping='):
                mapping_path = arg.split('=', 1)[1]
            elif arg == '--external-mapping' and i+1 < len(sys.argv):
                mapping_path = sys.argv[i+1]
    
    if not csv_path or not mapping_path:
        pytest.skip("External file paths not provided. Use environment variables or command line options.")
    
    # Load the data
    try:
        csv_data = external_csv_data(csv_path)
        importer = external_mapping_importer(mapping_path)
        
        # Log some information about the data being processed
        print(f"\nProcessing CSV data with {len(csv_data)} rows")
        print(f"Sample CSV row: {csv_data[0] if csv_data else 'No data'}")
        print(f"CSV columns: {list(csv_data[0].keys()) if csv_data else 'No columns'}")
        print(f"Mapping file: {mapping_path}")
        
    except FileNotFoundError as e:
        pytest.skip(str(e))
    
    # Count the initial resources and triples
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    # Import the data
    primary_class = "E7_Activity"  # Adjust based on your mapping
    print(f"\nStarting import with primary class: {primary_class}")
    
    stats = importer.import_data(csv_data, primary_subject_class_short_name=primary_class)
    
    # Log the statistics
    print(f"\nImport statistics:")
    print(f"Total rows: {stats['total_rows']}")
    print(f"Successful rows: {stats['successful_rows']}")
    print(f"Failed rows: {stats['failed_rows']}")
    
    # Resource creation details
    new_resources = Resource.objects.count() - initial_resource_count
    new_triples = Triple.objects.count() - initial_triple_count
    print(f"\nResource creation:")
    print(f"New resources created: {new_resources}")
    print(f"New triples created: {new_triples}")
    print(f"Avg triples per resource: {new_triples / new_resources if new_resources else 0:.2f}")
    
    # Sample of what was created
    if new_resources > 0:
        # Get a sample of the created resources
        sample_resources = Resource.objects.order_by('-id')[:5]
        print(f"\nSample of created resources:")
        for res in sample_resources:
            print(f"- {res.uri} (type: {res.resource_type})")
            # Show triples for this resource
            subject_triples = Triple.objects.filter(subject=res)[:3]
            if subject_triples:
                print(f"  Subject triples ({subject_triples.count()} total):")
                for triple in subject_triples[:3]:
                    print(f"    {triple.predicate.uri} → {triple.object.uri if triple.object.resource_type == ResourceType.IRI else triple.object.literal_value}")
                if subject_triples.count() > 3:
                    print(f"    ... and {subject_triples.count() - 3} more")
                
            # Also show where this resource is used as an object
            object_triples = Triple.objects.filter(object=res)[:3]
            if object_triples:
                print(f"  Object triples ({object_triples.count()} total):")
                for triple in object_triples[:3]:
                    print(f"    {triple.subject.uri} → {triple.predicate.uri}")
                if object_triples.count() > 3:
                    print(f"    ... and {object_triples.count() - 3} more")
    
    # Check that resources and triples were created
    assert Resource.objects.count() > initial_resource_count
    assert Triple.objects.count() > initial_triple_count
    
    # If there were errors, log them
    if stats['errors']:
        for error in stats['errors']:
            print(f"Error in row {error['row']}: {error['error']}")
    
    # Verify the expected success rate
    success_rate = stats['successful_rows'] / stats['total_rows'] if stats['total_rows'] > 0 else 0
    print(f"Import success rate: {success_rate:.1%}")
    
    # Basic validation - adjust thresholds based on your data quality expectations
    assert success_rate >= 0.8, f"Import success rate too low: {success_rate:.1%}"


@pytest.mark.django_db
def test_import_with_multiple_sources(external_csv_data, external_mapping_importer):
    """
    Test import using multiple related data sources.
    
    This test shows how to handle imports with related lookups across tables.
    
    Using environment variables:
    PRIMARY_DATA_FILE=/path/to/events.csv RELATED_DATA_FILE=/path/to/participants.csv MAPPING_FILE=/path/to/mapping.json pytest arkumu/importer/tests/services/test_with_real_data.py::test_import_with_multiple_sources -v
    
    Using command line arguments:
    pytest arkumu/importer/tests/services/test_with_real_data.py::test_import_with_multiple_sources -v --primary-data=/path/to/events.csv --related-data=/path/to/participants.csv --mapping=/path/to/mapping.json
    """
    # First check environment variables
    primary_data_path = os.environ.get('PRIMARY_DATA_FILE')
    related_data_path = os.environ.get('RELATED_DATA_FILE')
    mapping_path = os.environ.get('MAPPING_FILE')
    
    # If not found, check command line arguments
    if not primary_data_path or not related_data_path or not mapping_path:
        pytest.importorskip("sys")
        import sys
        
        for i, arg in enumerate(sys.argv):
            if arg.startswith('--primary-data='):
                primary_data_path = arg.split('=', 1)[1]
            elif arg.startswith('--related-data='):
                related_data_path = arg.split('=', 1)[1]
            elif arg.startswith('--mapping='):
                mapping_path = arg.split('=', 1)[1]
    
    if not primary_data_path or not related_data_path or not mapping_path:
        pytest.skip("Required file paths not provided. Use environment variables or command line options.")
    
    # Load the data
    try:
        primary_data = external_csv_data(primary_data_path)
        related_data = external_csv_data(related_data_path)
        
        # Log info about the data files
        print(f"\nProcessing primary CSV data with {len(primary_data)} rows")
        print(f"Processing related CSV data with {len(related_data)} rows")
        print(f"Primary data columns: {list(primary_data[0].keys()) if primary_data else 'No columns'}")
        print(f"Related data columns: {list(related_data[0].keys()) if related_data else 'No columns'}")
        print(f"Mapping file: {mapping_path}")
        
        # Create the importer with related_sources
        related_sources = {
            "participants": related_data  # The key should match the name in the mapping
        }
        
        print(f"Related sources: {list(related_sources.keys())}")
        
        importer = external_mapping_importer(
            mapping_path, 
            related_sources=related_sources
        )
    except FileNotFoundError as e:
        pytest.skip(str(e))
    
    # Count initial resources/triples
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    # Import the data
    primary_class = "E7_Activity"  # Adjust based on your mapping
    print(f"\nStarting import with primary class: {primary_class}")
    
    stats = importer.import_data(primary_data, primary_subject_class_short_name=primary_class)
    
    # Display import statistics
    print(f"\nImport statistics:")
    print(f"Total rows: {stats['total_rows']}")
    print(f"Successful rows: {stats['successful_rows']}")
    print(f"Failed rows: {stats['failed_rows']}")
    
    # Resource creation details
    new_resources = Resource.objects.count() - initial_resource_count
    new_triples = Triple.objects.count() - initial_triple_count
    print(f"\nResource creation:")
    print(f"New resources created: {new_resources}")
    print(f"New triples created: {new_triples}")
    print(f"Avg triples per resource: {new_triples / new_resources if new_resources else 0:.2f}")
    
    # Sample of what was created
    if new_resources > 0:
        # Get a sample of newly created resources from related data
        # Look for resources with related lookup URIs 
        sample_resources = Resource.objects.order_by('-id')[:5]
        print(f"\nSample of created resources:")
        for res in sample_resources:
            print(f"- {res.uri} (type: {res.resource_type})")
            # Show triples for this resource
            subject_triples = Triple.objects.filter(subject=res)[:3]
            if subject_triples:
                print(f"  Subject triples ({subject_triples.count()} total):")
                for triple in subject_triples[:3]:
                    print(f"    {triple.predicate.uri} → {triple.object.uri if triple.object.resource_type == ResourceType.IRI else triple.object.literal_value}")
                if subject_triples.count() > 3:
                    print(f"    ... and {subject_triples.count() - 3} more")
    
    # Check that things were created
    assert Resource.objects.count() > 0
    assert Triple.objects.count() > 0
    
    # Print any errors 
    if stats['errors']:
        print("\nErrors encountered:")
        for error in stats['errors']:
            print(f"Error in row {error['row']}: {error['error']}") 