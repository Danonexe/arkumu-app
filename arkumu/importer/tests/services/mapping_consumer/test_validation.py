"""
Tests for mapping consumer validation service.

Tests the ValidationService class which validates mapping configurations
for execution readiness.
"""

import pytest
from unittest.mock import Mock, patch

from arkumu.importer.services.mapping_consumer.validation import ValidationService, ValidationResult


class TestValidationResult:
    """Test suite for ValidationResult class"""

    def test_validation_result_creation(self):
        """Test ValidationResult creation"""
        result = ValidationResult(
            is_valid=True,
            errors=['Error 1', 'Error 2'],
            warnings=['Warning 1'],
            summary='Test summary'
        )
        
        assert result.is_valid is True
        assert result.errors == ['Error 1', 'Error 2']
        assert result.warnings == ['Warning 1']
        assert result.summary == 'Test summary'

    def test_add_error(self):
        """Test adding errors to validation result"""
        result = ValidationResult(is_valid=True)
        
        result.add_error('Test error')
        
        assert result.is_valid is False
        assert 'Test error' in result.errors
        assert len(result.errors) == 1

    def test_add_warning(self):
        """Test adding warnings to validation result"""
        result = ValidationResult(is_valid=True)
        
        result.add_warning('Test warning')
        
        assert result.is_valid is True  # Warnings don't affect validity
        assert 'Test warning' in result.warnings
        assert len(result.warnings) == 1

    def test_has_issues(self):
        """Test checking if result has issues"""
        # No issues
        result = ValidationResult(is_valid=True)
        assert result.has_issues() is False
        
        # With errors
        result.add_error('Error')
        assert result.has_issues() is True
        
        # With warnings only
        result = ValidationResult(is_valid=True)
        result.add_warning('Warning')
        assert result.has_issues() is True


class TestValidationService:
    """Test suite for ValidationService class"""

    @pytest.fixture
    def validation_service(self):
        """Create a ValidationService instance"""
        return ValidationService()

    @pytest.fixture
    def valid_mapping_config(self):
        """Valid mapping configuration for testing"""
        return {
            'version': '1.1',
            '_metadata': {
                'mapping_id': 1,
                'mapping_name': 'Test Mapping',
                'organization': 'TEST_ORG'
            },
            'workspace_columns': {
                'people': {
                    'name': {
                        'arkumu_type': 'Person.name',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                        'is_anchor': True,
                        'is_multi_value': False,
                        'confidence': 0.95
                    },
                    'age': {
                        'arkumu_type': 'Person.age',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#integer',
                        'is_anchor': False,
                        'is_multi_value': False,
                        'confidence': 0.90
                    },
                    'tags': {
                        'arkumu_type': 'Person.tags',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                        'is_anchor': False,
                        'is_multi_value': True,
                        'multi_value_separator': ',',
                        'confidence': 0.80
                    },
                    'orcid_id': {
                        'arkumu_type': 'Person.orcid',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                        'is_anchor': False,
                        'is_multi_value': False,
                        'is_external_ontology': True,
                        'external_ontology': {
                            'ontology_type': 'orcid',
                            'uri_template': 'https://orcid.org/{identifier}'
                        },
                        'confidence': 0.85
                    },
                    'location_id': {
                        'arkumu_type': 'Person.location',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                        'is_anchor': False,
                        'is_multi_value': False,
                        'confidence': 0.80
                    },
                    'start_date': {
                        'arkumu_type': 'Person.start_date',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#date',
                        'is_anchor': False,
                        'is_multi_value': False,
                        'confidence': 0.75
                    },
                    'end_date': {
                        'arkumu_type': 'Person.end_date',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#date',
                        'is_anchor': False,
                        'is_multi_value': False,
                        'confidence': 0.75
                    }
                },
                'locations': {
                    'city': {
                        'arkumu_type': 'Location.city',
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                        'is_anchor': True,
                        'is_multi_value': False,
                        'confidence': 0.90
                    }
                }
            },
            'selected_datasets': ['people', 'locations'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'location_id',
                    'source_dataset': 'people',
                    'target_column': 'id',
                    'target_dataset': 'locations',
                    'relationship_type': 'resides_in',
                    'direction': 'outgoing',
                    'is_multi_value': False,
                    'multi_value_separator': ',',
                    'confidence': 0.80
                }
            },
            'relationship_contexts': {
                'context_1': {
                    'primary_fk': 'fk_1',
                    'secondary_fk': 'fk_1',
                    'context_columns': ['start_date', 'end_date'],
                    'context_type': 'temporal',
                    'dataset_name': 'people'
                }
            },
            'external_ontologies': {
                'orcid_1': {
                    'column_name': 'orcid_id',
                    'dataset_name': 'people',
                    'ontology_type': 'orcid',
                    'uri_template': 'https://orcid.org/{identifier}',
                    'identifier_column': 'orcid_id',
                    'validation_enabled': True
                }
            },
            'import_strategy': {
                'update_strategy': 'SKIP_EXISTING',
                'bulk_size': 1000,
                'multi_value_threshold': 0.2,
                'enable_progress_tracking': True,
                'batch_processing': True,
                'processing_strategy': 'entity_centric'
            }
        }

    def test_validate_mapping_config_valid(self, validation_service, valid_mapping_config):
        """Test validation of valid mapping configuration"""
        result = validation_service.validate_mapping_config(valid_mapping_config)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.summary is not None
        assert '2 datasets' in result.summary
        assert '8 columns' in result.summary
        assert '1 FK relationships' in result.summary

    def test_validate_basic_structure_missing_required_fields(self, validation_service):
        """Test validation of basic structure with missing required fields"""
        config = {'version': '1.1'}  # Missing workspace_columns and selected_datasets
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('Missing required field: workspace_columns' in error for error in result.errors)
        assert any('Missing required field: selected_datasets' in error for error in result.errors)

    def test_validate_basic_structure_unknown_version(self, validation_service, valid_mapping_config):
        """Test validation with unknown version"""
        valid_mapping_config['version'] = '2.0'
        
        result = validation_service.validate_mapping_config(valid_mapping_config)
        
        assert any('Unknown configuration version: 2.0' in warning for warning in result.warnings)

    def test_validate_basic_structure_missing_metadata(self, validation_service, valid_mapping_config):
        """Test validation with missing metadata"""
        del valid_mapping_config['_metadata']
        
        result = validation_service.validate_mapping_config(valid_mapping_config)
        
        assert any('Missing mapping metadata' in warning for warning in result.warnings)

    def test_validate_workspace_columns_empty(self, validation_service):
        """Test validation with empty workspace columns"""
        config = {
            'workspace_columns': {},
            'selected_datasets': ['test']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('No workspace columns configured' in error for error in result.errors)

    def test_validate_workspace_columns_invalid_format(self, validation_service):
        """Test validation with invalid workspace columns format"""
        config = {
            'workspace_columns': {
                'dataset1': 'invalid_format'  # Should be dict
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('Invalid columns configuration for dataset' in error for error in result.errors)

    def test_validate_workspace_columns_missing_arkumu_type(self, validation_service):
        """Test validation with missing arkumu_type"""
        config = {
            'workspace_columns': {
                'dataset1': {
                    'col1': {
                        'datatype': 'http://www.w3.org/2001/XMLSchema#string'
                        # Missing arkumu_type
                    }
                }
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('Missing arkumu_type for column' in warning for warning in result.warnings)

    def test_validate_workspace_columns_multi_value_empty_separator(self, validation_service):
        """Test validation with multi-value column having empty separator"""
        config = {
            'workspace_columns': {
                'dataset1': {
                    'col1': {
                        'arkumu_type': 'Entity.col1',
                        'is_multi_value': True,
                        'multi_value_separator': ''  # Empty separator
                    }
                }
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('has empty separator' in warning for warning in result.warnings)

    def test_validate_workspace_columns_external_ontology_missing_config(self, validation_service):
        """Test validation with external ontology missing configuration"""
        config = {
            'workspace_columns': {
                'dataset1': {
                    'col1': {
                        'arkumu_type': 'Entity.col1',
                        'is_external_ontology': True,
                        'external_ontology': {}  # Missing required fields
                    }
                }
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('missing ontology_type' in error for error in result.errors)
        assert any('missing uri_template' in error for error in result.errors)

    def test_validate_workspace_columns_no_anchor_columns(self, validation_service):
        """Test validation with no anchor columns"""
        config = {
            'workspace_columns': {
                'dataset1': {
                    'col1': {
                        'arkumu_type': 'Entity.col1',
                        'is_anchor': False
                    }
                }
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('has no anchor columns' in warning for warning in result.warnings)

    def test_validate_workspace_columns_too_many_anchor_columns(self, validation_service):
        """Test validation with too many anchor columns"""
        config = {
            'workspace_columns': {
                'dataset1': {
                    'col1': {'arkumu_type': 'Entity.col1', 'is_anchor': True},
                    'col2': {'arkumu_type': 'Entity.col2', 'is_anchor': True},
                    'col3': {'arkumu_type': 'Entity.col3', 'is_anchor': True},
                    'col4': {'arkumu_type': 'Entity.col4', 'is_anchor': True}
                }
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('may impact performance' in warning for warning in result.warnings)

    def test_validate_selected_datasets_empty(self, validation_service):
        """Test validation with no selected datasets"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': []
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('No datasets selected for processing' in error for error in result.errors)

    def test_validate_selected_datasets_missing_columns(self, validation_service):
        """Test validation with selected dataset having no columns"""
        config = {
            'workspace_columns': {},
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('has no column configuration' in error for error in result.errors)

    def test_validate_selected_datasets_unselected_with_columns(self, validation_service):
        """Test validation with dataset having columns but not selected"""
        config = {
            'workspace_columns': {
                'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}},
                'dataset2': {'col2': {'arkumu_type': 'Entity.col2'}}
            },
            'selected_datasets': ['dataset1']
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('has columns but is not selected' in warning for warning in result.warnings)

    def test_validate_fk_relationships_missing_required_fields(self, validation_service):
        """Test validation of FK relationships with missing required fields"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'col1',
                    # Missing other required fields
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('missing required field' in error for error in result.errors)

    def test_validate_fk_relationships_nonexistent_source_column(self, validation_service):
        """Test validation of FK relationships with non-existent source column"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1', 'dataset2'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'nonexistent_col',
                    'source_dataset': 'dataset1',
                    'target_column': 'id',
                    'target_dataset': 'dataset2',
                    'relationship_type': 'relates_to'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('references non-existent source column' in error for error in result.errors)

    def test_validate_fk_relationships_unselected_target_dataset(self, validation_service):
        """Test validation of FK relationships with unselected target dataset"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'col1',
                    'source_dataset': 'dataset1',
                    'target_column': 'id',
                    'target_dataset': 'unselected_dataset',
                    'relationship_type': 'relates_to'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('references unselected target dataset' in warning for warning in result.warnings)

    def test_validate_fk_relationships_multi_value_empty_separator(self, validation_service):
        """Test validation of multi-value FK with empty separator"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1', 'dataset2'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'col1',
                    'source_dataset': 'dataset1',
                    'target_column': 'id',
                    'target_dataset': 'dataset2',
                    'relationship_type': 'relates_to',
                    'is_multi_value': True,
                    'multi_value_separator': ''
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('has empty separator' in warning for warning in result.warnings)

    def test_validate_relationship_contexts_missing_required_fields(self, validation_service):
        """Test validation of relationship contexts with missing fields"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'relationship_contexts': {
                'context_1': {
                    'primary_fk': 'fk_1'
                    # Missing other required fields
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('missing required field' in error for error in result.errors)

    def test_validate_relationship_contexts_nonexistent_fk(self, validation_service):
        """Test validation of relationship contexts with non-existent FK"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {},
            'relationship_contexts': {
                'context_1': {
                    'primary_fk': 'nonexistent_fk',
                    'secondary_fk': 'another_nonexistent_fk',
                    'context_columns': ['col1'],
                    'dataset_name': 'dataset1'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('references non-existent primary FK' in error for error in result.errors)
        assert any('references non-existent secondary FK' in error for error in result.errors)

    def test_validate_relationship_contexts_nonexistent_context_column(self, validation_service):
        """Test validation of relationship contexts with non-existent context column"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {'fk_1': {}},
            'relationship_contexts': {
                'context_1': {
                    'primary_fk': 'fk_1',
                    'secondary_fk': 'fk_1',
                    'context_columns': ['nonexistent_col'],
                    'dataset_name': 'dataset1'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('references non-existent context column' in error for error in result.errors)

    def test_validate_external_ontologies_missing_required_fields(self, validation_service):
        """Test validation of external ontologies with missing fields"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'external_ontologies': {
                'ont_1': {
                    'column_name': 'col1'
                    # Missing other required fields
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('missing required field' in error for error in result.errors)

    def test_validate_external_ontologies_nonexistent_column(self, validation_service):
        """Test validation of external ontologies with non-existent column"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'external_ontologies': {
                'ont_1': {
                    'column_name': 'nonexistent_col',
                    'dataset_name': 'dataset1',
                    'ontology_type': 'orcid',
                    'uri_template': 'https://orcid.org/{identifier}'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert result.is_valid is False
        assert any('references non-existent column' in error for error in result.errors)

    def test_validate_external_ontologies_missing_identifier_placeholder(self, validation_service):
        """Test validation of external ontologies with missing identifier placeholder"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'external_ontologies': {
                'ont_1': {
                    'column_name': 'col1',
                    'dataset_name': 'dataset1',
                    'ontology_type': 'orcid',
                    'uri_template': 'https://orcid.org/missing_placeholder'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('missing {identifier} placeholder' in warning for warning in result.warnings)

    def test_validate_external_ontologies_unknown_type(self, validation_service):
        """Test validation of external ontologies with unknown type"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'external_ontologies': {
                'ont_1': {
                    'column_name': 'col1',
                    'dataset_name': 'dataset1',
                    'ontology_type': 'unknown_type',
                    'uri_template': 'https://example.org/{identifier}'
                }
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('uses unknown type' in warning for warning in result.warnings)

    def test_validate_import_strategy_unknown_update_strategy(self, validation_service):
        """Test validation of import strategy with unknown update strategy"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'import_strategy': {
                'update_strategy': 'UNKNOWN_STRATEGY'
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('Unknown update strategy' in warning for warning in result.warnings)

    def test_validate_import_strategy_invalid_bulk_size(self, validation_service):
        """Test validation of import strategy with invalid bulk size"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'import_strategy': {
                'bulk_size': 'invalid'
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('Invalid bulk size' in warning for warning in result.warnings)

    def test_validate_import_strategy_bulk_size_out_of_range(self, validation_service):
        """Test validation of import strategy with bulk size out of range"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'import_strategy': {
                'bulk_size': 20000  # Too large
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('may impact performance' in warning for warning in result.warnings)

    def test_validate_import_strategy_invalid_multi_value_threshold(self, validation_service):
        """Test validation of import strategy with invalid multi-value threshold"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'import_strategy': {
                'multi_value_threshold': 1.5  # Out of range
            }
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('should be between 0 and 1' in warning for warning in result.warnings)

    def test_validate_import_strategy_missing(self, validation_service):
        """Test validation with missing import strategy"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1']
            # Missing import_strategy
        }
        
        result = validation_service.validate_mapping_config(config)
        
        assert any('No import strategy configured' in warning for warning in result.warnings)

    def test_quick_validate_valid(self, validation_service, valid_mapping_config):
        """Test quick validation of valid configuration"""
        result = validation_service.quick_validate(valid_mapping_config)
        assert result is True

    def test_quick_validate_missing_workspace_columns(self, validation_service):
        """Test quick validation with missing workspace columns"""
        config = {'selected_datasets': ['dataset1']}
        result = validation_service.quick_validate(config)
        assert result is False

    def test_quick_validate_missing_selected_datasets(self, validation_service):
        """Test quick validation with missing selected datasets"""
        config = {'workspace_columns': {'dataset1': {'col1': {}}}}
        result = validation_service.quick_validate(config)
        assert result is False

    def test_quick_validate_selected_dataset_no_columns(self, validation_service):
        """Test quick validation with selected dataset having no columns"""
        config = {
            'workspace_columns': {},
            'selected_datasets': ['dataset1']
        }
        result = validation_service.quick_validate(config)
        assert result is False

    def test_quick_validate_exception_handling(self, validation_service):
        """Test quick validation exception handling"""
        # Invalid config that will cause exception
        config = None
        result = validation_service.quick_validate(config)
        assert result is False

    def test_validation_exception_handling(self, validation_service):
        """Test main validation exception handling"""
        # Create config that will cause exception during validation
        with patch.object(validation_service, '_validate_basic_structure', side_effect=Exception('Test error')):
            config = {'workspace_columns': {}, 'selected_datasets': []}
            result = validation_service.validate_mapping_config(config)
            
            assert result.is_valid is False
            assert any('Validation failed: Test error' in error for error in result.errors)

    def test_generate_validation_summary_valid_no_warnings(self, validation_service):
        """Test validation summary generation for valid config with no warnings"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {}
        }
        
        result = ValidationResult(is_valid=True)
        validation_service._generate_validation_summary(config, result)
        
        assert 'valid and ready for execution' in result.summary

    def test_generate_validation_summary_valid_with_warnings(self, validation_service):
        """Test validation summary generation for valid config with warnings"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {}
        }
        
        result = ValidationResult(is_valid=True)
        result.add_warning('Test warning')
        validation_service._generate_validation_summary(config, result)
        
        assert 'valid with 1 warnings' in result.summary

    def test_generate_validation_summary_invalid(self, validation_service):
        """Test validation summary generation for invalid config"""
        config = {
            'workspace_columns': {'dataset1': {'col1': {'arkumu_type': 'Entity.col1'}}},
            'selected_datasets': ['dataset1'],
            'fk_relationships': {}
        }
        
        result = ValidationResult(is_valid=False)
        result.add_error('Test error')
        result.add_warning('Test warning')
        validation_service._generate_validation_summary(config, result)
        
        assert 'has 1 errors and 1 warnings' in result.summary

    def test_validation_statistics_in_summary(self, validation_service, valid_mapping_config):
        """Test that validation summary includes statistics"""
        result = validation_service.validate_mapping_config(valid_mapping_config)
        
        # Check that summary includes statistics
        assert '2 datasets' in result.summary
        assert '8 columns' in result.summary
        assert '1 FK relationships' in result.summary


class TestValidationIntegration:
    """Integration tests for validation service"""

    def test_comprehensive_validation_workflow(self):
        """Test comprehensive validation workflow"""
        validation_service = ValidationService()
        
        # Create a complex mapping configuration
        complex_config = {
            'version': '1.1',
            '_metadata': {
                'mapping_id': 1,
                'mapping_name': 'Complex Mapping',
                'organization': 'TEST_ORG'
            },
            'workspace_columns': {
                'people': {
                    'id': {'arkumu_type': 'Person.id', 'is_anchor': True},
                    'name': {'arkumu_type': 'Person.name'},
                    'tags': {'arkumu_type': 'Person.tags', 'is_multi_value': True, 'multi_value_separator': '|'},
                    'orcid': {'arkumu_type': 'Person.orcid', 'is_external_ontology': True,
                             'external_ontology': {'ontology_type': 'orcid', 'uri_template': 'https://orcid.org/{identifier}'}}
                },
                'organizations': {
                    'id': {'arkumu_type': 'Organization.id', 'is_anchor': True},
                    'name': {'arkumu_type': 'Organization.name'}
                }
            },
            'selected_datasets': ['people', 'organizations'],
            'fk_relationships': {
                'fk_1': {
                    'source_column': 'org_id',
                    'source_dataset': 'people',
                    'target_column': 'id',
                    'target_dataset': 'organizations',
                    'relationship_type': 'works_for'
                }
            },
            'external_ontologies': {
                'orcid_1': {
                    'column_name': 'orcid',
                    'dataset_name': 'people',
                    'ontology_type': 'orcid',
                    'uri_template': 'https://orcid.org/{identifier}'
                }
            },
            'import_strategy': {
                'update_strategy': 'UPDATE_VALUES',
                'bulk_size': 500
            }
        }
        
        # Add the org_id column that the FK references
        complex_config['workspace_columns']['people']['org_id'] = {
            'arkumu_type': 'Person.organization'
        }
        
        result = validation_service.validate_mapping_config(complex_config)
        
        # Should be valid despite complexity
        assert result.is_valid is True
        assert result.summary is not None
        
        # Quick validate should also pass
        assert validation_service.quick_validate(complex_config) is True