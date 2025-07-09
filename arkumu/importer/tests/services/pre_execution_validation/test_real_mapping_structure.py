"""
Test for real mapping structure validation issues.

This test reproduces the exact issue seen in production where:
- workspace_columns has 337 datasets
- selected_datasets is empty []
- workspace_columns values are strings, not dictionaries
"""

import pytest
import json
from unittest.mock import Mock, patch

from arkumu.importer.services.pre_execution_validation.pre_execution_validator import PreExecutionValidator
from arkumu.importer.services.pre_execution_validation.validation_result import (
    ValidationSeverity,
    ValidationMode
)


class TestRealMappingStructure:
    """Test validation with the actual production mapping structure"""
    
    @pytest.fixture
    def real_mapping_config(self):
        """Create a mapping config that matches the real production structure"""
        # Based on the logs showing 337 datasets with German column names
        workspace_columns = {}
        
        # Add datasets with string values (not dicts) as shown in the error
        for i in range(337):
            dataset_name = f"Dataset_{i}"
            workspace_columns[dataset_name] = f"arkumu_type_{i}"  # String value, not dict!
        
        # Add some real column names from the logs
        real_columns = [
            'Deutscher Name der Rolle (Breadcrumb)',
            'GND-Nummer (männlich)',
            'wählt ""ist Urheber:in"" automatisch aus',
            'Verknüpftes Projekt',
            'Schlagwort-ID',
            'ISO-639-1-Code'
        ]
        
        for idx, col in enumerate(real_columns):
            workspace_columns[col] = f"mapped_type_{idx}"
        
        return {
            'version': '1.1',
            'metadata': {},
            'created_at': '2024-01-01',
            'entity_mappings': {},
            'organization_id': 'fuk',
            'fk_relationships': {},
            'workspace_columns': workspace_columns,
            'workspace_summary': {},
            'workspace_datasets': {},
            'external_ontologies': {},
            'relationship_contexts': {},
            'selected_datasets': [],  # Empty as in production
            '_metadata': {
                'mapping_id': 'test-id',
                'mapping_name': 'test-mapping',
                'organization': 'fuk'
            }
        }
    
    @pytest.fixture
    def mock_file_columns(self):
        """Mock file columns that would be extracted from CSV files"""
        return [
            'Deutscher Name der Rolle (Breadcrumb)',
            'Englischer Name der Rolle (Breadcrumb)',
            'Synonyme',
            'Wikidata-ID',
            'GND-Nummer (männlich)',
            'GND-Nummer (weiblich)',
            'AAT-ID',
            'GND-Nummer (Gruppe)',
            'wählt ""ist Urheber:in"" automatisch aus',
            'wählt ""besitzt Leistungsschutzrechte"" automatisch aus',
            'Sammlung-ID',
            'Deutscher Name der Sammlung',
            'Englischer Name der Sammlung',
            'Sammlungsart',
            'Deutsche Beschreibung',
            'Englische Beschreibung',
            'Verknüpftes Projekt',
            'Verknüpftes Ereignis',
            'Verknüpftes Equipment und Software',
            'Verknüpftes Physisches Objekt',
            'Verknüpfter Informationsträger',
            'Verknüpftes Digitales Objekt',
            'Schlagwort-ID',
            'Deutsches Wikidata-Label',
            'Wikidata-ID',
            'Sprache-ID',
            'Deutscher Name der Sprache',
            'Englischer Name der Sprache',
            'ISO-639-2(B)-Code',
            'ISO-639-2(T)-Code',
            'ISO-639-1-Code'
        ]
    
    def test_validate_column_mapping_with_string_values(self, real_mapping_config, mock_file_columns):
        """Test that validation handles workspace_columns with string values"""
        validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
        
        # This should now work without errors
        result = validator.validate_column_mapping(
            file_columns=mock_file_columns,
            mapping_columns=real_mapping_config,
            organization_code='fuk'
        )
        
        # Should successfully handle the string values
        assert result is not None
        # With string values as workspace_columns, it should find mappings
        # where the key (dataset name) matches file columns
        matching_cols = [col for col in mock_file_columns if col in real_mapping_config['workspace_columns']]
        expected_mapped_count = len(matching_cols)
        
        assert len(result.mapped_columns) == expected_mapped_count
        if expected_mapped_count > 0:
            assert result.coverage_percentage > 0
    
    def test_validate_column_mapping_with_fixed_structure(self, mock_file_columns):
        """Test validation with properly structured workspace_columns"""
        # Create a proper mapping structure
        workspace_columns = {}
        
        # Each column should have a dict value with arkumu_type
        for col in mock_file_columns[:10]:  # Just test first 10
            workspace_columns[col] = {
                'arkumu_type': col,  # Map to itself
                'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                'is_anchor': False,
                'is_multi_value': False
            }
        
        mapping_config = {
            'workspace_columns': workspace_columns,
            'selected_datasets': [],  # Empty means use all
            '_metadata': {
                'mapping_id': 'test-id',
                'mapping_name': 'test-mapping',
                'organization': 'fuk'
            }
        }
        
        validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
        
        # This should work without errors
        result = validator.validate_column_mapping(
            file_columns=mock_file_columns,
            mapping_columns=mapping_config,
            organization_code='fuk'
        )
        
        # Should find the mapped columns
        assert len(result.mapped_columns) == 10
        assert result.coverage_percentage > 0
        
        # Should identify unmapped columns 
        assert len(result.unmapped_columns) > 0  # Should have some unmapped columns
        
        # Basic validation that it works without the old error
        assert result is not None
    
    def test_full_validation_with_real_structure(self, real_mapping_config):
        """Test full validation with the problematic real structure"""
        validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
        
        # Mock file paths
        file_paths = [
            'Rolle.csv',
            'Sammlung.csv', 
            'Schlagwort.csv',
            'Sprache.csv'
        ]
        
        # Mock file reading to return column data
        def mock_extract_columns(file_path, org_code):
            if 'Rolle' in file_path:
                return [
                    'Rolle-ID',
                    'Deutscher Name der Rolle (Breadcrumb)',
                    'Englischer Name der Rolle (Breadcrumb)',
                    'GND-Nummer (männlich)'
                ]
            elif 'Sammlung' in file_path:
                return [
                    'Sammlung-ID',
                    'Deutscher Name der Sammlung',
                    'Sammlungsart'
                ]
            elif 'Schlagwort' in file_path:
                return [
                    'Schlagwort-ID',
                    'Deutsches Wikidata-Label',
                    'Wikidata-ID'
                ]
            elif 'Sprache' in file_path:
                return [
                    'Sprache-ID',
                    'Deutscher Name der Sprache',
                    'ISO-639-1-Code'
                ]
            return []
        
        with patch.object(validator, '_extract_file_columns', side_effect=mock_extract_columns):
            with patch.object(validator, '_is_s3_path', return_value=False):
                with patch('os.path.exists', return_value=True):
                    with patch('os.access', return_value=True):
                        with patch('os.path.getsize', return_value=1024):
                            result = validator.validate_mapping_execution(
                                mapping_config=real_mapping_config,
                                file_paths=file_paths,
                                organization_code='fuk'
                            )
        
        # The validation should complete successfully with the new mixin logic
        assert result is not None
        assert result.overall_confidence == 0.0  # Due to no mappings being found
        
        # Should have column mapping result 
        assert result.column_mapping_result is not None
        assert result.column_mapping_result.coverage_percentage == 0.0  # No mappings found
        
        # Should have file validation results
        assert len(result.file_validation_results) == 4
        
        # The old error should no longer occur - the validator now handles string values properly
        no_attribute_errors = [
            issue for issue in result.all_issues 
            if "'str' object has no attribute 'get'" in issue.message
        ]
        assert len(no_attribute_errors) == 0  # This error should be fixed
    
    def test_workspace_columns_type_variations(self):
        """Test different variations of workspace_columns structures"""
        validator = PreExecutionValidator()
        
        # Test 1: workspace_columns is a list (not dict)
        mapping_with_list = {
            'workspace_columns': ['col1', 'col2', 'col3'],
            'selected_datasets': []
        }
        
        # Should handle gracefully
        result = validator.validate_column_mapping(
            file_columns=['col1', 'col2'],
            mapping_columns=mapping_with_list
        )
        assert len(result.mapped_columns) == 0
        
        # Test 2: workspace_columns has mixed values (some strings, some dicts)
        mapping_with_mixed = {
            'workspace_columns': {
                'col1': 'string_value',  # String
                'col2': {'arkumu_type': 'type2'},  # Dict
                'col3': None,  # None
                'col4': ['list', 'value']  # List
            },
            'selected_datasets': []
        }
        
        # Should handle the dict value correctly
        result = validator.validate_column_mapping(
            file_columns=['col1', 'col2', 'col3', 'col4'],
            mapping_columns=mapping_with_mixed
        )
        
        # Both col1 (string) and col2 (dict with arkumu_type) should be mapped
        assert len(result.mapped_columns) == 2
        assert 'col1' in result.mapped_columns
        assert 'col2' in result.mapped_columns
        assert result.mapped_columns['col1'] == 'string_value'
        assert result.mapped_columns['col2'] == 'type2'