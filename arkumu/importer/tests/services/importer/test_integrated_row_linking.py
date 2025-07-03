#!/usr/bin/env python3
"""
Simple test script to verify the integrated row linking functionality.
This creates a small CSV and imports it with the new bulk_import module.
"""

import tempfile
import csv
import os
import sys
import pytest
from django.db import transaction

# Add the arkumu directory to the Python path for testing
sys.path.insert(0, '/opt/app')

@pytest.fixture
def test_csv():
    """Create a small test CSV file"""
    test_data = [
        {'id': '1', 'name': 'Alice', 'age': '25', 'city': 'Berlin'},
        {'id': '2', 'name': 'Bob', 'age': '30', 'city': 'Munich'},
        {'id': '3', 'name': 'Charlie', 'age': '35', 'city': 'Hamburg'}
    ]
    
    # Create temporary CSV file
    fd, csv_path = tempfile.mkstemp(suffix='.csv', prefix='test_import_')
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'name', 'age', 'city'], delimiter=';')
        writer.writeheader()
        writer.writerows(test_data)
    
    os.close(fd)
    yield csv_path
    
    # Clean up after test is complete
    os.unlink(csv_path)

@pytest.fixture(autouse=True)
def setup_django():
    """Set up Django for all tests"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arkumu.settings.test')
    import django
    django.setup()

@pytest.mark.django_db(transaction=True)
def test_with_row_resources_and_linking(test_csv):
    """Test with row resources and linking enabled"""
    from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars, UpdateStrategy
    import csv
    
    # Read CSV data
    csv_data = []
    with open(test_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        csv_data = list(reader)
    
    # Test with row resources and linking enabled
    updater = SmartBulkUpdaterPolars(
        default_strategy=UpdateStrategy.UPDATE_VALUES,
        institution="TEST",
        link_row_cells=True,
        link_topology="row"
    )
    
    bulk_stats = updater.import_csv_with_smart_updates(csv_data, "test_dataset_with_rows")
    
    # Convert to expected dict format
    stats = {
        "rows_processed": bulk_stats.rows_processed,
        "cells_processed": bulk_stats.cells_processed,
        "resources_created": bulk_stats.resources_created,
        "triples_created": bulk_stats.triples_created,
        "row_links_created": bulk_stats.row_links_created,
        "errors": bulk_stats.errors,
        "truncated_values": bulk_stats.truncated_values
    }
    
    # Print stats to debug
    print(f"Import stats: {stats}")
    
    # Verify results based on the stats returned by the function
    assert stats['resources_created'] > 0, "No resources were created according to stats"
    assert stats['row_links_created'] > 0, "No row links were created according to stats"
    assert stats['rows_processed'] == 3, "Expected 3 rows to be processed"
    assert stats['cells_processed'] == 12, "Expected 12 cells to be processed (3 rows × 4 columns)"
    assert stats['errors'] == 0, "Import had errors"
    assert stats['truncated_values'] == 0, "Import had truncated values"

@pytest.mark.django_db(transaction=True)
def test_without_row_resources(test_csv):
    """Test without row resources (cells only)"""
    from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars, UpdateStrategy
    import csv
    
    # Read CSV data
    csv_data = []
    with open(test_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        csv_data = list(reader)
    
    # Test without row resources
    updater = SmartBulkUpdaterPolars(
        default_strategy=UpdateStrategy.UPDATE_VALUES,
        institution="TEST",
        link_row_cells=False,
        link_topology="row"
    )
    
    bulk_stats = updater.import_csv_with_smart_updates(csv_data, "test_dataset_cells_only")
    
    # Convert to expected dict format
    stats = {
        "rows_processed": bulk_stats.rows_processed,
        "cells_processed": bulk_stats.cells_processed,
        "resources_created": bulk_stats.resources_created,
        "triples_created": bulk_stats.triples_created,
        "row_links_created": bulk_stats.row_links_created,
        "errors": bulk_stats.errors,
        "truncated_values": bulk_stats.truncated_values
    }
    
    # Print stats to debug
    print(f"Import stats (cells only): {stats}")
    
    # Verify results based on the stats returned by the function
    assert stats['resources_created'] > 0, "No resources were created according to stats"
    assert stats['row_links_created'] == 0, "Row links were created when they shouldn't be"
    assert stats['rows_processed'] == 3, "Expected 3 rows to be processed"
    assert stats['cells_processed'] == 12, "Expected 12 cells to be processed (3 rows × 4 columns)"
    assert stats['errors'] == 0, "Import had errors"
    assert stats['truncated_values'] == 0, "Import had truncated values" 