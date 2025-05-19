"""Tests that demonstrate using the JSONMappingImporter with a single row of real data,
reading the primary class from the mapping, and displaying all created RDF entities."""

import pytest
import logging
import os
from arkumu.metadata.models import Resource, Triple, ResourceType
from arkumu.importer.services.importer import JSONMappingImporter # Assuming this is the correct path

# Configure logging for tests - can be shared from a conftest.py or defined here
@pytest.fixture(autouse=True)
def configure_logging_single_row():
    """Configure logging for single-row tests."""
    logging.basicConfig(level=logging.INFO) # Or logging.DEBUG for more importer output
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.DEBUG)
    yield

def _print_all_created_data(title="Created Data"):
    """Helper function to print all Resource and Triple objects."""
    print(f"\n--- {title} ---")
    
    resources = Resource.objects.all()
    print(f"\nTotal Resources created: {resources.count()}")
    for i, res in enumerate(resources):
        print(f"Resource {i+1}/{resources.count()}: URI='{res.uri}', Type='{res.resource_type}', Source='{res.source}', SourceField='{res.source_field}'")

    triples = Triple.objects.all()
    print(f"\nTotal Triples created: {triples.count()}")
    for i, t in enumerate(triples):
        subject_uri = t.subject.uri
        predicate_uri = t.predicate.uri
        object_val = t.object.uri if t.object.resource_type == ResourceType.IRI else f"'{t.object.literal_value}' (Lang: {t.object.literal_language}, Type: {t.object.literal_datatype})"
        print(f"Triple {i+1}/{triples.count()}: S='{subject_uri}', P='{predicate_uri}', O={object_val}")
    print("--- End of Data ---\n")


@pytest.mark.django_db
def test_import_single_row_from_mapping_and_show_details(external_csv_data, external_mapping_importer):
    """
    Test import of a single data row using external CSV and mapping files,
    determining primary_class from the mapping, and showing all created data.
    
    Requires environment variables or command line arguments for file paths:
    CSV_TEST_FILE=/path/to/data.csv MAPPING_TEST_FILE=/path/to/mapping.json
    or --external-csv=/path/to/data.csv --external-mapping=/path/to/mapping.json
    """
    # Get file paths (copied from test_with_real_data.py)
    csv_path = os.environ.get('CSV_TEST_FILE')
    mapping_path = os.environ.get('MAPPING_TEST_FILE')
    
    if not csv_path or not mapping_path:
        # Attempt to get from command line if pytest.config is available, otherwise skip
        # This is a simplified version for brevity; a robust CLI arg parser would be in conftest or shared fixture
        try:
            config = pytest.config
            csv_path = csv_path or config.getoption("external_csv", None)
            mapping_path = mapping_path or config.getoption("external_mapping", None)
        except AttributeError: # pytest.config might not be set if not run via pytest CLI with those options
            pass 

        if not csv_path or not mapping_path:
            print("Debug: Skipping test because external file paths (CSV or Mapping) are missing.")
            print(f"Debug: CSV Path: {csv_path}")
            print(f"Debug: Mapping Path: {mapping_path}")
            pytest.skip("External file paths (CSV_TEST_FILE, MAPPING_TEST_FILE or --external-csv, --external-mapping) not provided.")

    print(f"\n--- Test Setup ---")
    print(f"Using CSV file: {csv_path}")
    print(f"Using Mapping file: {mapping_path}")

    # ---- Add directory listing for debugging ----
    try:
        print(f"Debug: Listing contents of /external_data/fuk/ inside the container:")
        external_fuk_dir = "/external_data/fuk/"
        if os.path.exists(external_fuk_dir) and os.path.isdir(external_fuk_dir):
            for item in os.listdir(external_fuk_dir):
                print(f"Debug: Found in /external_data/fuk/: {item}")
        else:
            print(f"Debug: Directory /external_data/fuk/ does not exist or is not a directory inside the container.")
        if os.path.exists("/external_data/") and os.path.isdir("/external_data/"):
            print(f"Debug: Listing contents of /external_data/ inside the container:")
            for item in os.listdir("/external_data/"):
                print(f"Debug: Found in /external_data/: {item}")
        else:
            print(f"Debug: Directory /external_data/ does not exist or is not a directory.")

    except Exception as e_ls:
        print(f"Debug: Error trying to list directory /external_data/fuk/: {e_ls}")
    # ---- End of directory listing ----

    # Load the data and importer
    try:
        csv_data = external_csv_data(csv_path)
        if not csv_data:
            print(f"Debug: Skipping test because CSV data from '{csv_path}' is empty or could not be loaded.")
            pytest.skip("CSV data is empty or could not be loaded.")
        
        importer = external_mapping_importer(mapping_path)
        
    except FileNotFoundError as e:
        print(f"Debug: Skipping test due to FileNotFoundError during setup: {e}")
        pytest.skip(f"File not found during setup: {e}")
    except Exception as e:
        print(f"Debug: Failing test due to an unexpected error during setup: {e}")
        pytest.fail(f"Error during setup: {e}")

    # Determine primary_class from the mapping config
    print(f"Debug: Attempting to determine primary_class from mapping config: {importer.mapping_config}")
    primary_class = importer.mapping_config.get('primary_subject_class')
    
    if not primary_class:
        print("Debug: 'primary_subject_class' not found directly in mapping config. Trying 'domain' key.")
        primary_class = importer.mapping_config.get('domain') # Use 'domain' as the fallback

    if not primary_class:
        # Optional: Fallback for old structure if 'mappings' is a dict with one key
        print("Debug: 'domain' key also not found or is empty. Checking old 'mappings' dict structure.")
        mappings_config_dict = importer.mapping_config.get('mappings')
        if isinstance(mappings_config_dict, dict) and len(mappings_config_dict) == 1:
            primary_class = list(mappings_config_dict.keys())[0]
            print(f"Debug: Inferred '{primary_class}' as primary class from single key in 'mappings' dictionary (old structure). ")
            print(f"Warning: Neither 'primary_subject_class' nor 'domain' found. Inferred '{primary_class}'.")
        else:
            print("Debug: Skipping because 'primary_subject_class', 'domain' not found, and could not infer from 'mappings' dict structure.")
            print(f"Debug: importer.mapping_config.get('primary_subject_class'): {importer.mapping_config.get('primary_subject_class')}")
            print(f"Debug: importer.mapping_config.get('domain'): {importer.mapping_config.get('domain')}")
            print(f"Debug: 'mappings' content in config: {importer.mapping_config.get('mappings')}")
            pytest.skip("Primary class could not be determined from mapping_config ('primary_subject_class' or 'domain'). Skipping test.")
    else:
        print(f"Debug: Found primary class: '{primary_class}' (either from 'primary_subject_class' or 'domain').")

    print(f"Determined primary class from mapping: '{primary_class}'")

    # Take only the first row of data
    single_row_data = csv_data[0]
    print(f"Processing single CSV row: {single_row_data}")
    print(f"CSV columns: {list(single_row_data.keys())}")
    print(f"--- End Test Setup ---\n")

    # Clear any existing data from other tests if DB is not reset per test method
    # Resource.objects.all().delete()
    # Triple.objects.all().delete()

    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()
    
    # Import the single data row
    print(f"Starting import for single row with primary class: {primary_class}...")
    stats = importer.import_data([single_row_data], primary_subject_class_short_name=primary_class)
    
    print(f"\n--- Import Results ---")
    print(f"Import statistics for single row: Total={stats['total_rows']}, Successful={stats['successful_rows']}, Failed={stats['failed_rows']}")
    if stats['errors']:
        print("Errors during import:")
        for error_info in stats['errors']:
            print(f"- Row {error_info['row']}: {error_info['error']} (Data: {error_info.get('data')})")

    # Print all created resources and triples
    _print_all_created_data("Data Created from Single Row Import")

    # Assert that at least the import attempt was made
    assert stats['total_rows'] == 1, "Import stats did not reflect processing one row."

    # Further assertions can be added here if specific outcomes are expected
    # For example, assert stats['successful_rows'] == 1 if the row is expected to succeed.
    # Or check Resource.objects.count() > initial_resource_count if creation is expected.

    if stats['successful_rows'] == 1:
        assert Resource.objects.count() > initial_resource_count, "Successful import of one row did not create any resources."
        assert Triple.objects.count() > initial_triple_count, "Successful import of one row did not create any triples."
    else:
        print("Warning: The single row import was not successful. Check errors above.")

    # Generate a Turtle representation of the RDF graph
    print("\n--- Turtle Representation of RDF Graph ---")
    
    # Define common prefixes
    prefixes = {
        'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
        'owl': 'http://www.w3.org/2002/07/owl#',
        'xsd': 'http://www.w3.org/2001/XMLSchema#',
        'crm': 'http://cidoc-crm.org/cidoc-crm/'
    }
    
    # Print prefixes
    for prefix, uri in prefixes.items():
        print(f"@prefix {prefix}: <{uri}> .")
    print("")
    
    # Group triples by subject for cleaner Turtle representation
    subjects = {}
    for t in Triple.objects.all():
        if t.subject.uri not in subjects:
            subjects[t.subject.uri] = []
        subjects[t.subject.uri].append(t)
    
    # Process each subject and its predicates
    for subject_uri, triples in subjects.items():
        print(f"<{subject_uri}>")
        
        # Group by predicate for multi-valued properties
        predicates = {}
        for t in triples:
            if t.predicate.uri not in predicates:
                predicates[t.predicate.uri] = []
            predicates[t.predicate.uri].append(t.object)
        
        # Sort predicates with rdf:type first, then alphabetically
        sorted_predicates = sorted(predicates.keys(), 
                                  key=lambda p: (0 if p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' else 1, p))
        
        # Process each predicate
        for i, predicate_uri in enumerate(sorted_predicates):
            is_last_predicate = i == len(sorted_predicates) - 1
            
            # Format the predicate using the shortest prefix possible
            short_predicate = predicate_uri
            for prefix, uri in prefixes.items():
                if predicate_uri.startswith(uri):
                    short_predicate = predicate_uri.replace(uri, f"{prefix}:")
                    break
            
            # Start the predicate line
            if len(predicates[predicate_uri]) == 1:
                # Single value
                obj = predicates[predicate_uri][0]
                if obj.resource_type == ResourceType.IRI:
                    print(f"    {short_predicate}  <{obj.uri}>{';' if not is_last_predicate else '.'}")
                else:  # Literal
                    literal_repr = f'"{obj.literal_value}"'
                    
                    # Special case for rdf:type that should point to a CIDOC class
                    if predicate_uri == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' and 'CIDOC-CRM Class:' in obj.literal_value:
                        cidoc_class = obj.literal_value.replace('CIDOC-CRM Class: ', '')
                        literal_repr = f"crm:{cidoc_class}"
                    elif obj.literal_language:
                        literal_repr += f"@{obj.literal_language}"
                    elif obj.literal_datatype:
                        short_datatype = obj.literal_datatype
                        for prefix, uri in prefixes.items():
                            if obj.literal_datatype.startswith(uri):
                                short_datatype = obj.literal_datatype.replace(uri, f"{prefix}:")
                                break
                        literal_repr += f"^^{short_datatype}"
                    print(f"    {short_predicate}  {literal_repr}{';' if not is_last_predicate else '.'}")
            else:
                # Multiple values for same predicate
                print(f"    {short_predicate}")
                for j, obj in enumerate(predicates[predicate_uri]):
                    is_last_value = j == len(predicates[predicate_uri]) - 1
                    if obj.resource_type == ResourceType.IRI:
                        print(f"        <{obj.uri}>{' ;' if is_last_value and not is_last_predicate else ' ,' if not is_last_value else ' .'}")
                    else:  # Literal
                        literal_repr = f'"{obj.literal_value}"'
                        
                        # Special case for rdf:type that should point to a CIDOC class
                        if predicate_uri == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type' and 'CIDOC-CRM Class:' in obj.literal_value:
                            cidoc_class = obj.literal_value.replace('CIDOC-CRM Class: ', '')
                            literal_repr = f"crm:{cidoc_class}"
                        elif obj.literal_language:
                            literal_repr += f"@{obj.literal_language}"
                        elif obj.literal_datatype:
                            short_datatype = obj.literal_datatype
                            for prefix, uri in prefixes.items():
                                if obj.literal_datatype.startswith(uri):
                                    short_datatype = obj.literal_datatype.replace(uri, f"{prefix}:")
                                    break
                            literal_repr += f"^^{short_datatype}"
                        print(f"        {literal_repr}{' ;' if is_last_value and not is_last_predicate else ' ,' if not is_last_value else ' .'}")
        print("")
    
    print("--- End of Turtle Representation ---")

    print(f"--- Test End ---\n")


