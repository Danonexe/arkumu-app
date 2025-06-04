"""
Validation Service

Handles data quality checks, semantic validation, and integrity verification.
Provides comprehensive validation for entities, relationships, and transformations.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(Enum):
    DATA_QUALITY = "data_quality"
    SEMANTIC_CONSISTENCY = "semantic_consistency"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    SCHEMA_COMPLIANCE = "schema_compliance"
    BUSINESS_RULES = "business_rules"


@dataclass
class ValidationIssue:
    """A single validation issue"""
    level: ValidationLevel
    category: ValidationCategory
    code: str
    message: str
    details: Dict[str, Any]
    location: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of a validation check"""
    is_valid: bool
    score: float  # 0.0 to 1.0
    issues: List[ValidationIssue]
    summary: Dict[str, Any]
    metadata: Dict[str, Any]


class ValidationService:
    """Service for comprehensive validation of semantic data"""
    
    def __init__(self):
        self.validation_rules = self._initialize_validation_rules()
        self.custom_validators = {}
    
    def _initialize_validation_rules(self) -> Dict[str, Any]:
        """Initialize built-in validation rules"""
        return {
            'entity_rules': {
                'required_fields': ['id', 'type'],
                'id_patterns': {
                    'valid': r'^[a-zA-Z0-9_\-:]+$',
                    'invalid_chars': r'[^\w\-:]'
                },
                'type_patterns': {
                    'arkumu_types': r'^arkumu:[a-zA-Z][a-zA-Z0-9_]*$',
                    'standard_types': r'^(rdf|rdfs|owl|foaf|dc|skos):[a-zA-Z][a-zA-Z0-9_]*$'
                }
            },
            'relationship_rules': {
                'required_fields': ['source_entity', 'target_entity', 'predicate'],
                'predicate_patterns': {
                    'arkumu_predicates': r'^arkumu:[a-zA-Z][a-zA-Z0-9_]*$',
                    'standard_predicates': r'^(rdf|rdfs|owl|foaf|dc|skos):[a-zA-Z][a-zA-Z0-9_]*$'
                }
            },
            'data_quality_rules': {
                'completeness_threshold': 0.8,
                'uniqueness_threshold': 0.95,
                'consistency_threshold': 0.9
            }
        }
    
    def validate_entity(self, entity_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single entity
        
        Args:
            entity_data: Entity data dictionary
            
        Returns:
            ValidationResult with validation details
        """
        issues = []
        
        # Required fields validation
        issues.extend(self._validate_required_fields(
            entity_data, 
            self.validation_rules['entity_rules']['required_fields'],
            'entity'
        ))
        
        # ID validation
        if 'id' in entity_data:
            issues.extend(self._validate_entity_id(entity_data['id']))
        
        # Type validation
        if 'type' in entity_data:
            issues.extend(self._validate_entity_type(entity_data['type']))
        
        # Property validation
        if 'properties' in entity_data and entity_data['properties'] is not None:
            issues.extend(self._validate_entity_properties(entity_data['properties']))
        
        # Data consistency validation
        issues.extend(self._validate_entity_consistency(entity_data))
        
        # Calculate validation score
        score = self._calculate_validation_score(issues)
        
        return ValidationResult(
            is_valid=not any(issue.level == ValidationLevel.ERROR for issue in issues),
            score=score,
            issues=issues,
            summary=self._generate_validation_summary(issues),
            metadata={
                'entity_id': entity_data.get('id', 'unknown'),
                'entity_type': entity_data.get('type', 'unknown'),
                'validation_timestamp': datetime.now().isoformat()
            }
        )
    
    def validate_relationship(self, relationship_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single relationship
        
        Args:
            relationship_data: Relationship data dictionary
            
        Returns:
            ValidationResult with validation details
        """
        issues = []
        
        # Required fields validation
        issues.extend(self._validate_required_fields(
            relationship_data,
            self.validation_rules['relationship_rules']['required_fields'],
            'relationship'
        ))
        
        # Entity reference validation
        issues.extend(self._validate_relationship_entities(relationship_data))
        
        # Predicate validation
        if 'predicate' in relationship_data:
            issues.extend(self._validate_relationship_predicate(relationship_data['predicate']))
        
        # Relationship consistency validation
        issues.extend(self._validate_relationship_consistency(relationship_data))
        
        # Calculate validation score
        score = self._calculate_validation_score(issues)
        
        return ValidationResult(
            is_valid=not any(issue.level == ValidationLevel.ERROR for issue in issues),
            score=score,
            issues=issues,
            summary=self._generate_validation_summary(issues),
            metadata={
                'relationship_id': relationship_data.get('id', 'unknown'),
                'source_entity': relationship_data.get('source_entity', 'unknown'),
                'target_entity': relationship_data.get('target_entity', 'unknown'),
                'predicate': relationship_data.get('predicate', 'unknown'),
                'validation_timestamp': datetime.now().isoformat()
            }
        )
    
    def validate_dataset(self, dataset_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate an entire dataset (collection of entities and relationships)
        
        Args:
            dataset_data: Dataset containing entities and relationships
            
        Returns:
            ValidationResult with dataset-level validation
        """
        issues = []
        entities = dataset_data.get('entities', {}) or {}
        relationships = dataset_data.get('relationships', []) or []
        
        # Validate individual entities
        entity_validations = {}
        for entity_id, entity_data in entities.items():
            entity_result = self.validate_entity(entity_data)
            entity_validations[entity_id] = entity_result
            issues.extend(entity_result.issues)
        
        # Validate individual relationships
        relationship_validations = []
        for relationship_data in relationships:
            relationship_result = self.validate_relationship(relationship_data)
            relationship_validations.append(relationship_result)
            issues.extend(relationship_result.issues)
        
        # Dataset-level validations
        issues.extend(self._validate_referential_integrity(entities, relationships))
        issues.extend(self._validate_dataset_consistency(dataset_data))
        issues.extend(self._validate_dataset_completeness(dataset_data))
        
        # Calculate overall score
        score = self._calculate_validation_score(issues)
        
        return ValidationResult(
            is_valid=not any(issue.level == ValidationLevel.ERROR for issue in issues),
            score=score,
            issues=issues,
            summary=self._generate_dataset_validation_summary(
                entity_validations, relationship_validations, issues
            ),
            metadata={
                'dataset_entities_count': len(entities),
                'dataset_relationships_count': len(relationships),
                'validation_timestamp': datetime.now().isoformat()
            }
        )
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str], 
                                data_type: str) -> List[ValidationIssue]:
        """Validate that required fields are present"""
        issues = []
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA_COMPLIANCE,
                    code=f"MISSING_REQUIRED_FIELD",
                    message=f"Required field '{field}' is missing or empty in {data_type}",
                    details={'field': field, 'data_type': data_type},
                    suggestion=f"Ensure that the {data_type} has a valid '{field}' value"
                ))
        
        return issues
    
    def _validate_entity_id(self, entity_id: str) -> List[ValidationIssue]:
        """Validate entity ID format"""
        issues = []
        
        # Check for valid characters
        valid_pattern = self.validation_rules['entity_rules']['id_patterns']['valid']
        if not re.match(valid_pattern, entity_id):
            issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA_COMPLIANCE,
                code="INVALID_ENTITY_ID",
                message=f"Entity ID '{entity_id}' contains invalid characters",
                details={'entity_id': entity_id, 'valid_pattern': valid_pattern},
                suggestion="Entity IDs should only contain letters, numbers, underscores, hyphens, and colons"
            ))
        
        # Check for proper URI format (if applicable)
        if ':' in entity_id:
            parts = entity_id.split(':', 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.SCHEMA_COMPLIANCE,
                    code="MALFORMED_URI",
                    message=f"Entity ID '{entity_id}' appears to be a malformed URI",
                    details={'entity_id': entity_id},
                    suggestion="URIs should follow the format 'namespace:localname'"
                ))
        
        return issues
    
    def _validate_entity_type(self, entity_type: str) -> List[ValidationIssue]:
        """Validate entity type format"""
        issues = []
        
        # Check for recognized namespace patterns
        arkumu_pattern = self.validation_rules['entity_rules']['type_patterns']['arkumu_types']
        standard_pattern = self.validation_rules['entity_rules']['type_patterns']['standard_types']
        
        if not (re.match(arkumu_pattern, entity_type) or re.match(standard_pattern, entity_type)):
            issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                category=ValidationCategory.SEMANTIC_CONSISTENCY,
                code="UNRECOGNIZED_TYPE_NAMESPACE",
                message=f"Entity type '{entity_type}' uses an unrecognized namespace",
                details={'entity_type': entity_type},
                suggestion="Consider using arkumu: namespace for custom types or standard namespaces for known types"
            ))
        
        return issues
    
    def _validate_entity_properties(self, properties: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate entity properties"""
        issues = []
        
        for prop_name, prop_value in properties.items():
            # Check property name format
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_:]*$', prop_name):
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.SCHEMA_COMPLIANCE,
                    code="INVALID_PROPERTY_NAME",
                    message=f"Property name '{prop_name}' uses invalid format",
                    details={'property_name': prop_name},
                    suggestion="Property names should start with a letter and contain only letters, numbers, underscores, and colons"
                ))
            
            # Check for empty values
            if prop_value is None or prop_value == '':
                issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.DATA_QUALITY,
                    code="EMPTY_PROPERTY_VALUE",
                    message=f"Property '{prop_name}' has an empty value",
                    details={'property_name': prop_name},
                    suggestion="Consider removing empty properties or providing default values"
                ))
        
        return issues
    
    def _validate_entity_consistency(self, entity_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate entity internal consistency"""
        issues = []
        
        # Check for conflicting information
        if 'source_value' in entity_data and 'properties' in entity_data:
            name_properties = ['name', 'title', 'label']
            for prop in name_properties:
                if prop in entity_data['properties']:
                    if entity_data['source_value'] != entity_data['properties'][prop]:
                        issues.append(ValidationIssue(
                            level=ValidationLevel.INFO,
                            category=ValidationCategory.DATA_QUALITY,
                            code="INCONSISTENT_NAME_VALUES",
                            message=f"Source value and {prop} property differ",
                            details={
                                'source_value': entity_data['source_value'],
                                'property_value': entity_data['properties'][prop]
                            },
                            suggestion="Ensure name consistency across different fields"
                        ))
                    break
        
        return issues
    
    def _validate_relationship_entities(self, relationship_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate relationship entity references"""
        issues = []
        
        source_entity = relationship_data.get('source_entity')
        target_entity = relationship_data.get('target_entity')
        
        # Check for self-references
        if source_entity and target_entity and source_entity == target_entity:
            issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                category=ValidationCategory.SEMANTIC_CONSISTENCY,
                code="SELF_REFERENCE",
                message="Relationship references the same entity as source and target",
                details={'entity': source_entity},
                suggestion="Verify that self-references are intentional and semantically valid"
            ))
        
        return issues
    
    def _validate_relationship_predicate(self, predicate: str) -> List[ValidationIssue]:
        """Validate relationship predicate"""
        issues = []
        
        # Check for recognized namespace patterns
        arkumu_pattern = self.validation_rules['relationship_rules']['predicate_patterns']['arkumu_predicates']
        standard_pattern = self.validation_rules['relationship_rules']['predicate_patterns']['standard_predicates']
        
        if not (re.match(arkumu_pattern, predicate) or re.match(standard_pattern, predicate)):
            issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                category=ValidationCategory.SEMANTIC_CONSISTENCY,
                code="UNRECOGNIZED_PREDICATE_NAMESPACE",
                message=f"Predicate '{predicate}' uses an unrecognized namespace",
                details={'predicate': predicate},
                suggestion="Consider using arkumu: namespace for custom predicates or standard namespaces"
            ))
        
        return issues
    
    def _validate_relationship_consistency(self, relationship_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate relationship internal consistency"""
        issues = []
        
        # Check for metadata consistency
        if 'metadata' in relationship_data:
            metadata = relationship_data['metadata']
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    if value is None or value == '':
                        issues.append(ValidationIssue(
                            level=ValidationLevel.INFO,
                            category=ValidationCategory.DATA_QUALITY,
                            code="EMPTY_METADATA_VALUE",
                            message=f"Relationship metadata '{key}' has an empty value",
                            details={'metadata_key': key},
                            suggestion="Consider removing empty metadata or providing default values"
                        ))
        
        return issues
    
    def _validate_referential_integrity(self, entities: Dict[str, Any], 
                                      relationships: List[Dict[str, Any]]) -> List[ValidationIssue]:
        """Validate referential integrity between entities and relationships"""
        issues = []
        
        entity_ids = set(entities.keys())
        
        for relationship in relationships:
            source_entity = relationship.get('source_entity')
            target_entity = relationship.get('target_entity')
            
            # Check if referenced entities exist
            if source_entity and source_entity not in entity_ids:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.REFERENTIAL_INTEGRITY,
                    code="MISSING_SOURCE_ENTITY",
                    message=f"Relationship references non-existent source entity '{source_entity}'",
                    details={'source_entity': source_entity, 'relationship_id': relationship.get('id')},
                    suggestion="Ensure all referenced entities exist in the dataset"
                ))
            
            if target_entity and target_entity not in entity_ids:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.REFERENTIAL_INTEGRITY,
                    code="MISSING_TARGET_ENTITY",
                    message=f"Relationship references non-existent target entity '{target_entity}'",
                    details={'target_entity': target_entity, 'relationship_id': relationship.get('id')},
                    suggestion="Ensure all referenced entities exist in the dataset"
                ))
        
        return issues
    
    def _validate_dataset_consistency(self, dataset_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate dataset-level consistency"""
        issues = []
        
        entities = dataset_data.get('entities', {}) or {}
        
        # Check for duplicate entity IDs (should not happen, but good to verify)
        entity_ids = list(entities.keys())
        if len(entity_ids) != len(set(entity_ids)):
            issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.DATA_QUALITY,
                code="DUPLICATE_ENTITY_IDS",
                message="Dataset contains duplicate entity IDs",
                details={'total_entities': len(entity_ids), 'unique_entities': len(set(entity_ids))},
                suggestion="Ensure all entity IDs are unique within the dataset"
            ))
        
        return issues
    
    def _validate_dataset_completeness(self, dataset_data: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate dataset completeness"""
        issues = []
        
        entities = dataset_data.get('entities', {}) or {}
        relationships = dataset_data.get('relationships', []) or []
        
        # Check if dataset is empty
        if not entities and not relationships:
            issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                category=ValidationCategory.DATA_QUALITY,
                code="EMPTY_DATASET",
                message="Dataset contains no entities or relationships",
                details={},
                suggestion="Verify that the dataset was processed correctly"
            ))
        
        # Check for orphaned entities (entities with no relationships)
        if entities and relationships:
            referenced_entities = set()
            for rel in relationships:
                if 'source_entity' in rel:
                    referenced_entities.add(rel['source_entity'])
                if 'target_entity' in rel:
                    referenced_entities.add(rel['target_entity'])
            
            orphaned_entities = set(entities.keys()) - referenced_entities
            if orphaned_entities:
                issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    category=ValidationCategory.DATA_QUALITY,
                    code="ORPHANED_ENTITIES",
                    message=f"Dataset contains {len(orphaned_entities)} entities with no relationships",
                    details={'orphaned_count': len(orphaned_entities)},
                    suggestion="Consider if isolated entities are expected or if relationships are missing"
                ))
        
        return issues
    
    def _calculate_validation_score(self, issues: List[ValidationIssue]) -> float:
        """Calculate a validation score (0.0 to 1.0) based on issues"""
        if not issues:
            return 1.0
        
        # Weight different issue levels
        weights = {
            ValidationLevel.ERROR: -0.5,
            ValidationLevel.WARNING: -0.2,
            ValidationLevel.INFO: -0.05
        }
        
        total_penalty = sum(weights[issue.level] for issue in issues)
        score = max(0.0, 1.0 + total_penalty)
        
        return score
    
    def _generate_validation_summary(self, issues: List[ValidationIssue]) -> Dict[str, Any]:
        """Generate a summary of validation issues"""
        summary = {
            'total_issues': len(issues),
            'errors': len([i for i in issues if i.level == ValidationLevel.ERROR]),
            'warnings': len([i for i in issues if i.level == ValidationLevel.WARNING]),
            'info': len([i for i in issues if i.level == ValidationLevel.INFO]),
            'categories': {}
        }
        
        # Count by category
        for issue in issues:
            category = issue.category.value
            if category not in summary['categories']:
                summary['categories'][category] = 0
            summary['categories'][category] += 1
        
        return summary
    
    def _generate_dataset_validation_summary(self, entity_validations: Dict[str, ValidationResult],
                                           relationship_validations: List[ValidationResult],
                                           dataset_issues: List[ValidationIssue]) -> Dict[str, Any]:
        """Generate a comprehensive dataset validation summary"""
        
        entity_summary = self._generate_validation_summary([
            issue for result in entity_validations.values() for issue in result.issues
        ])
        
        relationship_summary = self._generate_validation_summary([
            issue for result in relationship_validations for issue in result.issues
        ])
        
        dataset_summary = self._generate_validation_summary(dataset_issues)
        
        return {
            'overall': self._generate_validation_summary(
                [issue for result in entity_validations.values() for issue in result.issues] +
                [issue for result in relationship_validations for issue in result.issues] +
                dataset_issues
            ),
            'entities': entity_summary,
            'relationships': relationship_summary,
            'dataset': dataset_summary,
            'valid_entities': len([r for r in entity_validations.values() if r.is_valid]),
            'total_entities': len(entity_validations),
            'valid_relationships': len([r for r in relationship_validations if r.is_valid]),
            'total_relationships': len(relationship_validations),
            'average_entity_score': sum(r.score for r in entity_validations.values()) / len(entity_validations) if entity_validations else 0,
            'average_relationship_score': sum(r.score for r in relationship_validations) / len(relationship_validations) if relationship_validations else 0
        }
    
    def add_custom_validator(self, name: str, validator_function: callable):
        """Add a custom validation function"""
        self.custom_validators[name] = validator_function
    
    def run_custom_validation(self, data: Any, validator_name: str) -> ValidationResult:
        """Run a custom validation function"""
        if validator_name not in self.custom_validators:
            raise ValueError(f"Custom validator '{validator_name}' not found")
        
        validator = self.custom_validators[validator_name]
        return validator(data) 