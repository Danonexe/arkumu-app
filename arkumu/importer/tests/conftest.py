import pytest
import os
import csv
import json
import logging

@pytest.fixture
def external_csv_data():
    """
    Fixture to load CSV data from an external file.
    
    Handles semicolon-separated CSV files (used in arkumu-metadata).
    
    Usage:
        def test_with_real_data(external_csv_data):
            data = external_csv_data('/path/to/external/file.csv')
            # Use the data for testing
    """
    def _load_csv(file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"External data file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as csv_file:
            # Use semicolon as delimiter (standard for arkumu-metadata files)
            csv_reader = csv.DictReader(csv_file, delimiter=';')
            return list(csv_reader)
    
    return _load_csv

@pytest.fixture
def external_json_data():
    """
    Fixture to load JSON data from an external file.
    
    Usage:
        def test_with_real_data(external_json_data):
            data = external_json_data('/path/to/external/file.json')
            # Use the data for testing
    """
    def _load_json(file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"External data file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as json_file:
            return json.load(json_file)
    
    return _load_json

@pytest.fixture
def external_mapping_importer(external_json_data):
    """
    Fixture to create a JSONMappingImporter with an external mapping file.
    
    Usage:
        def test_with_real_mapping(external_mapping_importer):
            importer = external_mapping_importer('/path/to/external/mapping.json')
            # Use the importer for testing
    """
    from arkumu.importer.services.importer import JSONMappingImporter
    
    def _create_importer(mapping_file_path, **kwargs):
        # Check if file exists first
        if not os.path.exists(mapping_file_path):
            raise FileNotFoundError(f"External mapping file not found: {mapping_file_path}")
        
        return JSONMappingImporter(mapping_file_path=mapping_file_path, **kwargs)
    
    return _create_importer 