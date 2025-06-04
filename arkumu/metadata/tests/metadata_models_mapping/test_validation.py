"""
Test suite for ValidationService

Tests data quality checks, semantic validation, and integrity verification
for entities, relationships, and transformations.
"""

import pytest
from typing import Dict, Any, List
from datetime import datetime
from unittest.mock import Mock, patch

from arkumu.metadata.services.metadata_models_mapping.validation import (
    ValidationService, ValidationResult, ValidationIssue,
    ValidationLevel, ValidationCategory
)


@pytest.fixture
def validation_service():
    """Create a ValidationService instance for testing"""
    return ValidationService()

@pytest.fixture
def valid_entity():
    """Create a valid entity for testing"""
    return {
        'id': 'entity:123',
        'type': 'arkumu:Person',
        'source_value': 'John Doe',
        'properties': {
            'name': 'John Doe',
            'age': 30,
            'email': 'john@example.com'
        }
    }

@pytest.fixture
def valid_relationship():
    """Create a valid relationship for testing"""
    return {
        'id': 'rel:456',
        'source_entity': 'entity:123',
        'target_entity': 'entity:789',
        'predicate': 'arkumu:knows',
        'metadata': {
            'since': '2020-01-01',
            'context': 'work'
        }
    }

@pytest.fixture
def valid_dataset():
    """Create a valid dataset for testing"""
    return {
        'entities': {
            'entity:123': {
                'id': 'entity:123',
                'type': 'arkumu:Person',
                'properties': {'name': 'John Doe'}
            },
            'entity:789': {
                'id': 'entity:789',
                'type': 'arkumu:Person',
                'properties': {'name': 'Jane Smith'}
            }
        },
        'relationships': [
            {
                'source_entity': 'entity:123',
                'target_entity': 'entity:789',
                'predicate': 'arkumu:knows'
            }
        ]
    }


class TestValidationService:
    """Test cases for ValidationService"""
    pass


class TestEntityValidation:
    """Test entity validation functionality"""
    
    def test_validate_valid_entity(self, validation_service, valid_entity):
        """Test validation of a valid entity"""
        result = validation_service.validate_entity(valid_entity)
        
        assert result.is_valid is True
        assert result.score == 1.0
        assert len(result.issues) == 0
        assert result.metadata['entity_id'] == 'entity:123'
        assert result.metadata['entity_type'] == 'arkumu:Person'
    
    def test_validate_entity_missing_required_fields(self, validation_service):
        """Test validation when required fields are missing"""
        entity = {'properties': {'name': 'Test'}}
        result = validation_service.validate_entity(entity)
        
        assert result.is_valid is False
        assert result.score < 1.0
        assert len(result.issues) >= 2  # Missing id and type
        
        # Check for specific errors
        error_codes = [issue.code for issue in result.issues]
        assert 'MISSING_REQUIRED_FIELD' in error_codes
    
    def test_validate_entity_invalid_id(self, validation_service):
        """Test validation with invalid entity ID"""
        entity = {
            'id': 'entity@#$%',  # Invalid characters
            'type': 'arkumu:Person'
        }
        result = validation_service.validate_entity(entity)
        
        assert result.is_valid is False
        assert any(issue.code == 'INVALID_ENTITY_ID' for issue in result.issues)
    
    def test_validate_entity_malformed_uri(self, validation_service):
        """Test validation with malformed URI"""
        entity = {
            'id': ':invalid',  # Malformed URI
            'type': 'arkumu:Person'
        }
        result = validation_service.validate_entity(entity)
        
        assert len([i for i in result.issues if i.code == 'MALFORMED_URI']) == 1
    
    def test_validate_entity_unrecognized_type(self, validation_service):
        """Test validation with unrecognized type namespace"""
        entity = {
            'id': 'entity:123',
            'type': 'unknown:Type'  # Unrecognized namespace
        }
        result = validation_service.validate_entity(entity)
        
        assert result.is_valid is True  # Warning only
        assert any(issue.code == 'UNRECOGNIZED_TYPE_NAMESPACE' for issue in result.issues)
        assert any(issue.level == ValidationLevel.WARNING for issue in result.issues)
    
    def test_validate_entity_invalid_property_names(self, validation_service):
        """Test validation with invalid property names"""
        entity = {
            'id': 'entity:123',
            'type': 'arkumu:Person',
            'properties': {
                '123invalid': 'value',  # Starts with number
                'valid_property': 'value',
                'also-invalid': 'value'  # Contains hyphen
            }
        }
        result = validation_service.validate_entity(entity)
        
        property_issues = [i for i in result.issues if i.code == 'INVALID_PROPERTY_NAME']
        assert len(property_issues) == 2
    
    def test_validate_entity_empty_properties(self, validation_service):
        """Test validation with empty property values"""
        entity = {
            'id': 'entity:123',
            'type': 'arkumu:Person',
            'properties': {
                'name': 'John',
                'email': '',  # Empty value
                'phone': None  # None value
            }
        }
        result = validation_service.validate_entity(entity)
        
        empty_issues = [i for i in result.issues if i.code == 'EMPTY_PROPERTY_VALUE']
        assert len(empty_issues) == 2
        assert all(issue.level == ValidationLevel.INFO for issue in empty_issues)
    
    def test_validate_entity_inconsistent_names(self, validation_service):
        """Test validation with inconsistent name values"""
        entity = {
            'id': 'entity:123',
            'type': 'arkumu:Person',
            'source_value': 'John Doe',
            'properties': {
                'name': 'John Smith',  # Different from source_value
                'age': 30
            }
        }
        result = validation_service.validate_entity(entity)
        
        assert any(issue.code == 'INCONSISTENT_NAME_VALUES' for issue in result.issues)


class TestRelationshipValidation:
    """Test relationship validation functionality"""
    
    def test_validate_valid_relationship(self, validation_service, valid_relationship):
        """Test validation of a valid relationship"""
        result = validation_service.validate_relationship(valid_relationship)
        
        assert result.is_valid is True
        assert result.score == 1.0
        assert len(result.issues) == 0
    
    def test_validate_relationship_missing_fields(self, validation_service):
        """Test validation with missing required fields"""
        relationship = {
            'predicate': 'arkumu:knows'
            # Missing source_entity and target_entity
        }
        result = validation_service.validate_relationship(relationship)
        
        assert result.is_valid is False
        missing_field_issues = [i for i in result.issues if i.code == 'MISSING_REQUIRED_FIELD']
        assert len(missing_field_issues) == 2
    
    def test_validate_relationship_self_reference(self, validation_service):
        """Test validation with self-referencing relationship"""
        relationship = {
            'source_entity': 'entity:123',
            'target_entity': 'entity:123',  # Same as source
            'predicate': 'arkumu:knows'
        }
        result = validation_service.validate_relationship(relationship)
        
        assert result.is_valid is True  # Warning only
        assert any(issue.code == 'SELF_REFERENCE' for issue in result.issues)
    
    def test_validate_relationship_unrecognized_predicate(self, validation_service):
        """Test validation with unrecognized predicate namespace"""
        relationship = {
            'source_entity': 'entity:123',
            'target_entity': 'entity:456',
            'predicate': 'custom:predicate'  # Unrecognized namespace
        }
        result = validation_service.validate_relationship(relationship)
        
        assert any(issue.code == 'UNRECOGNIZED_PREDICATE_NAMESPACE' for issue in result.issues)
    
    def test_validate_relationship_empty_metadata(self, validation_service):
        """Test validation with empty metadata values"""
        relationship = {
            'source_entity': 'entity:123',
            'target_entity': 'entity:456',
            'predicate': 'arkumu:knows',
            'metadata': {
                'context': 'work',
                'description': '',  # Empty
                'notes': None  # None
            }
        }
        result = validation_service.validate_relationship(relationship)
        
        empty_metadata_issues = [i for i in result.issues if i.code == 'EMPTY_METADATA_VALUE']
        assert len(empty_metadata_issues) == 2


class TestDatasetValidation:
    """Test dataset validation functionality"""
    
    def test_validate_valid_dataset(self, validation_service, valid_dataset):
        """Test validation of a valid dataset"""
        result = validation_service.validate_dataset(valid_dataset)
        
        assert result.is_valid is True
        assert result.score > 0.8  # High score for valid dataset
        assert result.summary['overall']['errors'] == 0
        assert result.summary['valid_entities'] == 2
        assert result.summary['valid_relationships'] == 1
    
    def test_validate_empty_dataset(self, validation_service):
        """Test validation of an empty dataset"""
        empty_dataset = {'entities': {}, 'relationships': []}
        result = validation_service.validate_dataset(empty_dataset)
        
        assert any(issue.code == 'EMPTY_DATASET' for issue in result.issues)
    
    def test_validate_dataset_missing_entities(self, validation_service):
        """Test validation with relationships referencing missing entities"""
        dataset = {
            'entities': {
                'entity:123': {
                    'id': 'entity:123',
                    'type': 'arkumu:Person'
                }
            },
            'relationships': [
                {
                    'source_entity': 'entity:123',
                    'target_entity': 'entity:999',  # Non-existent
                    'predicate': 'arkumu:knows'
                }
            ]
        }
        result = validation_service.validate_dataset(dataset)
        
        assert result.is_valid is False
        assert any(issue.code == 'MISSING_TARGET_ENTITY' for issue in result.issues)
    
    def test_validate_dataset_orphaned_entities(self, validation_service):
        """Test validation with orphaned entities"""
        dataset = {
            'entities': {
                'entity:1': {'id': 'entity:1', 'type': 'arkumu:Person'},
                'entity:2': {'id': 'entity:2', 'type': 'arkumu:Person'},
                'entity:3': {'id': 'entity:3', 'type': 'arkumu:Person'}  # Orphaned
            },
            'relationships': [
                {
                    'source_entity': 'entity:1',
                    'target_entity': 'entity:2',
                    'predicate': 'arkumu:knows'
                }
            ]
        }
        result = validation_service.validate_dataset(dataset)
        
        orphan_issues = [i for i in result.issues if i.code == 'ORPHANED_ENTITIES']
        assert len(orphan_issues) == 1
        assert orphan_issues[0].details['orphaned_count'] == 1
    
    def test_validate_dataset_referential_integrity(self, validation_service):
        """Test comprehensive referential integrity validation"""
        dataset = {
            'entities': {
                'entity:1': {'id': 'entity:1', 'type': 'arkumu:Person'}
            },
            'relationships': [
                {
                    'source_entity': 'entity:missing1',  # Non-existent
                    'target_entity': 'entity:1',
                    'predicate': 'arkumu:knows'
                },
                {
                    'source_entity': 'entity:1',
                    'target_entity': 'entity:missing2',  # Non-existent
                    'predicate': 'arkumu:knows'
                }
            ]
        }
        result = validation_service.validate_dataset(dataset)
        
        assert result.is_valid is False
        integrity_issues = [i for i in result.issues 
                           if i.category == ValidationCategory.REFERENTIAL_INTEGRITY]
        assert len(integrity_issues) == 2


class TestValidationScoring:
    """Test validation scoring functionality"""
    
    def test_calculate_validation_score_no_issues(self, validation_service):
        """Test score calculation with no issues"""
        issues = []
        score = validation_service._calculate_validation_score(issues)
        assert score == 1.0
    
    def test_calculate_validation_score_with_errors(self, validation_service):
        """Test score calculation with errors"""
        issues = [
            ValidationIssue(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.DATA_QUALITY,
                code="TEST_ERROR",
                message="Test error",
                details={}
            )
        ]
        score = validation_service._calculate_validation_score(issues)
        assert score == 0.5  # 1.0 - 0.5 (error penalty)
    
    def test_calculate_validation_score_mixed_issues(self, validation_service):
        """Test score calculation with mixed issue levels"""
        issues = [
            ValidationIssue(ValidationLevel.ERROR, ValidationCategory.DATA_QUALITY, 
                          "E1", "Error", {}),
            ValidationIssue(ValidationLevel.WARNING, ValidationCategory.DATA_QUALITY, 
                          "W1", "Warning", {}),
            ValidationIssue(ValidationLevel.WARNING, ValidationCategory.DATA_QUALITY, 
                          "W2", "Warning", {}),
            ValidationIssue(ValidationLevel.INFO, ValidationCategory.DATA_QUALITY, 
                          "I1", "Info", {})
        ]
        score = validation_service._calculate_validation_score(issues)
        # 1.0 - 0.5 - 0.2 - 0.2 - 0.05 = 0.05
        assert abs(score - 0.05) < 0.001  # Use tolerance for floating point comparison
    
    def test_calculate_validation_score_minimum_zero(self, validation_service):
        """Test that score never goes below 0"""
        issues = [
            ValidationIssue(ValidationLevel.ERROR, ValidationCategory.DATA_QUALITY, 
                          f"E{i}", "Error", {})
            for i in range(5)  # Many errors
        ]
        score = validation_service._calculate_validation_score(issues)
        assert score == 0.0


class TestCustomValidators:
    """Test custom validator functionality"""
    
    def test_add_custom_validator(self, validation_service):
        """Test adding a custom validator"""
        def custom_validator(data):
            issues = []
            if 'custom_field' not in data:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.BUSINESS_RULES,
                    code="MISSING_CUSTOM_FIELD",
                    message="Custom field is required",
                    details={}
                ))
            return ValidationResult(
                is_valid=len(issues) == 0,
                score=1.0 if len(issues) == 0 else 0.0,
                issues=issues,
                summary={},
                metadata={}
            )
        
        validation_service.add_custom_validator('custom_check', custom_validator)
        assert 'custom_check' in validation_service.custom_validators
    
    def test_run_custom_validator(self, validation_service):
        """Test running a custom validator"""
        def always_valid_validator(data):
            return ValidationResult(
                is_valid=True,
                score=1.0,
                issues=[],
                summary={},
                metadata={'validated': True}
            )
        
        validation_service.add_custom_validator('always_valid', always_valid_validator)
        result = validation_service.run_custom_validation({'test': 'data'}, 'always_valid')
        
        assert result.is_valid is True
        assert result.metadata['validated'] is True
    
    def test_run_nonexistent_custom_validator(self, validation_service):
        """Test running a non-existent custom validator"""
        with pytest.raises(ValueError, match="Custom validator 'nonexistent' not found"):
            validation_service.run_custom_validation({}, 'nonexistent')


class TestValidationSummary:
    """Test validation summary generation"""
    
    def test_generate_validation_summary(self, validation_service):
        """Test generation of validation summary"""
        issues = [
            ValidationIssue(ValidationLevel.ERROR, ValidationCategory.DATA_QUALITY, 
                          "E1", "Error", {}),
            ValidationIssue(ValidationLevel.ERROR, ValidationCategory.SCHEMA_COMPLIANCE, 
                          "E2", "Error", {}),
            ValidationIssue(ValidationLevel.WARNING, ValidationCategory.DATA_QUALITY, 
                          "W1", "Warning", {}),
            ValidationIssue(ValidationLevel.INFO, ValidationCategory.SEMANTIC_CONSISTENCY, 
                          "I1", "Info", {})
        ]
        
        summary = validation_service._generate_validation_summary(issues)
        
        assert summary['total_issues'] == 4
        assert summary['errors'] == 2
        assert summary['warnings'] == 1
        assert summary['info'] == 1
        assert summary['categories']['data_quality'] == 2
        assert summary['categories']['schema_compliance'] == 1
        assert summary['categories']['semantic_consistency'] == 1
    
    def test_generate_dataset_validation_summary(self, validation_service):
        """Test generation of dataset validation summary"""
        entity_validations = {
            'e1': ValidationResult(True, 1.0, [], {}, {}),
            'e2': ValidationResult(False, 0.5, [
                ValidationIssue(ValidationLevel.ERROR, ValidationCategory.DATA_QUALITY, 
                              "E1", "Error", {})
            ], {}, {})
        }
        
        relationship_validations = [
            ValidationResult(True, 1.0, [], {}, {}),
            ValidationResult(True, 0.8, [
                ValidationIssue(ValidationLevel.WARNING, ValidationCategory.SEMANTIC_CONSISTENCY, 
                              "W1", "Warning", {})
            ], {}, {})
        ]
        
        dataset_issues = [
            ValidationIssue(ValidationLevel.INFO, ValidationCategory.DATA_QUALITY, 
                          "I1", "Info", {})
        ]
        
        summary = validation_service._generate_dataset_validation_summary(
            entity_validations, relationship_validations, dataset_issues
        )
        
        assert summary['valid_entities'] == 1
        assert summary['total_entities'] == 2
        assert summary['valid_relationships'] == 2
        assert summary['total_relationships'] == 2
        assert summary['average_entity_score'] == 0.75
        assert summary['average_relationship_score'] == 0.9
        assert summary['overall']['total_issues'] == 3


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_validate_entity_with_none_properties(self, validation_service):
        """Test validation when properties is None"""
        entity = {
            'id': 'entity:123',
            'type': 'arkumu:Person',
            'properties': None
        }
        result = validation_service.validate_entity(entity)
        assert result.is_valid is True  # Should handle None gracefully
    
    def test_validate_relationship_with_none_metadata(self, validation_service):
        """Test validation when metadata is None"""
        relationship = {
            'source_entity': 'entity:123',
            'target_entity': 'entity:456',
            'predicate': 'arkumu:knows',
            'metadata': None
        }
        result = validation_service.validate_relationship(relationship)
        assert result.is_valid is True  # Should handle None gracefully
    
    def test_validate_dataset_with_none_values(self, validation_service):
        """Test validation when dataset has None values"""
        dataset = {
            'entities': None,
            'relationships': None
        }
        # Should handle gracefully, treating as empty
        result = validation_service.validate_dataset(dataset)
        assert isinstance(result, ValidationResult)
    
    @patch('arkumu.metadata.services.metadata_models_mapping.validation.datetime')
    def test_validation_timestamp(self, mock_datetime, validation_service):
        """Test that validation includes timestamp"""
        mock_now = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        entity = {'id': 'test', 'type': 'arkumu:Test'}
        result = validation_service.validate_entity(entity)
        
        assert result.metadata['validation_timestamp'] == mock_now.isoformat()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])