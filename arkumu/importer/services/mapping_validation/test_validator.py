"""
Unit tests for the MappingValidator service.

This module provides tests for the centralized validation service to ensure
it correctly validates column mappings, relationships, and file structures.
"""

import unittest
from unittest.mock import MagicMock, patch
from .validator import MappingValidator


class TestMappingValidator(unittest.TestCase):
    """Test cases for MappingValidator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = MappingValidator()
    
    def test_validate_column_mappings_dict_format(self):
        """Test column mapping validation with dict format workspace columns."""
        workspace_columns = {
            'org::dataset::name': {'name': 'name', 'type': 'string'},
            'org::dataset::age': {'name': 'age', 'type': 'integer'},
            'org::dataset::email': {'name': 'email', 'type': 'string'}
        }
        file_columns = ['name', 'age', 'city']
        
        result = MappingValidator.validate_column_mappings(workspace_columns, file_columns)
        
        self.assertEqual(len(result['mapped_columns']), 2)
        self.assertIn('name', result['mapped_columns'])
        self.assertIn('age', result['mapped_columns'])
        self.assertEqual(result['unmapped_columns'], ['city'])
        self.assertEqual(result['missing_required_columns'], ['email'])
        self.assertEqual(result['coverage_percentage'], 66.67)  # 2 out of 3 columns mapped
    
    def test_validate_column_mappings_list_format(self):
        """Test column mapping validation with list format workspace columns."""
        workspace_columns = [
            {'id': 'org::dataset::name', 'name': 'name', 'type': 'string'},
            {'id': 'org::dataset::age', 'name': 'age', 'type': 'integer'},
            {'id': 'org::dataset::email', 'name': 'email', 'type': 'string'}
        ]
        file_columns = ['name', 'age', 'city']
        
        result = MappingValidator.validate_column_mappings(workspace_columns, file_columns)
        
        self.assertEqual(len(result['mapped_columns']), 2)
        self.assertIn('name', result['mapped_columns'])
        self.assertIn('age', result['mapped_columns'])
        self.assertEqual(result['unmapped_columns'], ['city'])
        self.assertEqual(result['missing_required_columns'], ['email'])
    
    def test_validate_relationships(self):
        """Test relationship validation."""
        workspace_columns = {
            'org::dataset::person_id': {'name': 'person_id', 'type': 'integer'},
            'org::dataset::company_id': {'name': 'company_id', 'type': 'integer'}
        }
        fk_relationships = {
            'org::dataset::company_id': {
                'target_dataset': 'companies',
                'target_column': 'id',
                'display_column': 'name'
            },
            'invalid_fk': {
                'target_dataset': '',  # Missing target dataset
                'target_column': 'id'
            }
        }
        
        issues = MappingValidator.validate_relationships(workspace_columns, fk_relationships)
        
        # Should have issues for missing target dataset and column not in workspace
        self.assertEqual(len(issues), 2)
        issue_codes = [issue['code'] for issue in issues]
        self.assertIn('FK_COLUMN_NOT_FOUND', issue_codes)
        self.assertIn('FK_MISSING_TARGET_DATASET', issue_codes)
    
    def test_validate_mapping_completeness(self):
        """Test mapping completeness validation."""
        # Valid mapping config
        valid_config = {
            'workspace_columns': {'col1': {'name': 'col1'}},
            'organization_id': '123'
        }
        
        result = MappingValidator.validate_mapping_completeness(valid_config)
        self.assertTrue(result['is_complete'])
        self.assertEqual(len(result['missing_components']), 0)
        self.assertEqual(len(result['issues']), 0)
        
        # Invalid mapping config - missing required components
        invalid_config = {
            'workspace_columns': {},  # Empty
            # Missing organization_id
        }
        
        result = MappingValidator.validate_mapping_completeness(invalid_config)
        self.assertFalse(result['is_complete'])
        self.assertIn('organization_id', result['missing_components'])
        self.assertTrue(len(result['issues']) > 0)
    
    def test_validate_data_types(self):
        """Test data type validation."""
        workspace_columns = {
            'org::dataset::age': {'name': 'age', 'type': 'integer'},
            'org::dataset::score': {'name': 'score', 'type': 'float'},
            'org::dataset::active': {'name': 'active', 'type': 'boolean'}
        }
        sample_data = [
            {'age': '25', 'score': '95.5', 'active': 'true'},
            {'age': 'invalid', 'score': '88.0', 'active': 'false'}
        ]
        
        issues = MappingValidator.validate_data_types(workspace_columns, sample_data)
        
        # Should have type mismatch issues for invalid age
        self.assertTrue(len(issues) > 0)
        type_mismatch_issues = [issue for issue in issues if issue['code'] == 'TYPE_MISMATCH']
        self.assertTrue(len(type_mismatch_issues) > 0)
    
    @patch('arkumu.importer.services.mapping_validation.validator.BucketService')
    def test_validate_file_structure_s3(self, mock_bucket_service):
        """Test file structure validation for S3 files."""
        # Mock S3 file exists and has size
        mock_instance = mock_bucket_service.return_value
        mock_instance.get_organization_bucket.return_value = 'test-bucket'
        
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_s3_client.head_object.return_value = {'ContentLength': 1024}
        mock_instance.get_s3_client.return_value = mock_s3_client
        
        validator = MappingValidator()
        issues = validator.validate_file_structure('metadata/test.csv', 'test-org')
        
        # Should have no issues for valid file
        error_issues = [issue for issue in issues if issue['severity'] == 'ERROR']
        self.assertEqual(len(error_issues), 0)
    
    @patch('os.path.exists')
    @patch('os.access')
    @patch('os.path.getsize')
    def test_validate_file_structure_local(self, mock_getsize, mock_access, mock_exists):
        """Test file structure validation for local files."""
        # Mock local file exists, is readable, and has size
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_getsize.return_value = 1024
        
        validator = MappingValidator()
        issues = validator.validate_file_structure('/path/to/test.csv', 'test-org')
        
        # Should have no issues for valid file
        error_issues = [issue for issue in issues if issue['severity'] == 'ERROR']
        self.assertEqual(len(error_issues), 0)
    
    def test_validate_file_structure_invalid_format(self):
        """Test file structure validation with invalid file format."""
        validator = MappingValidator()
        issues = validator.validate_file_structure('/path/to/test.txt', 'test-org')
        
        # Should have warning for unsupported format (txt is actually supported, but let's test with .pdf)
        issues = validator.validate_file_structure('/path/to/test.pdf', 'test-org')
        warning_issues = [issue for issue in issues if issue['severity'] == 'WARNING']
        self.assertTrue(len(warning_issues) > 0)


if __name__ == '__main__':
    unittest.main()