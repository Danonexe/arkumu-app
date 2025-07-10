# Centralized Mapping Validation Architecture

## Executive Summary

After analyzing the current validation system across `arkumu/importer/services/pre_execution_validation/`, `arkumu/common/mixins/base_coordinator.py`, `arkumu/importer/mixins/ingest_coordinator.py`, and `arkumu/metadata/views/csv_mapping/mixins/coordinator.py`, we've identified significant architectural issues that need to be addressed:

1. **Duplication of validation logic** across multiple components
2. **No single source of truth** for validation rules
3. **Blurred separation of concerns** between state management and validation

This document proposes a centralized validation architecture that solves these issues.

## Current Architecture Analysis

### 1. BaseCoordinatorMixin
- **Purpose**: Foundation for session and state management
- **Validation**: None - provides infrastructure only
- **Location**: `arkumu/common/mixins/base_coordinator.py`

### 2. IngestCoordinatorMixin
- **Purpose**: Manages ingest process state (file selection, mapping choice)
- **Validation**: 
  - `validate_selected_files()` - checks file existence and format
  - `validate_import_configuration()` - validates import config completeness
- **Location**: `arkumu/importer/mixins/ingest_coordinator.py`

### 3. CSVMappingCoordinatorMixin
- **Purpose**: Manages mapping creation state (workspace columns, types, relationships)
- **Validation**:
  - `validate_mapping_structure()` - validates mapping internal consistency
  - `validate_workspace_column_uniqueness()` - ensures no duplicate columns
- **Location**: `arkumu/metadata/views/csv_mapping/mixins/coordinator.py`

### 4. PreExecutionValidator
- **Purpose**: Performs comprehensive pre-flight validation before import
- **Validation**: Duplicates logic from coordinators, plus additional checks
- **Location**: `arkumu/importer/services/pre_execution_validation/`

## Problems with Current Architecture

### 1. Code Duplication
```python
# Example: File validation exists in multiple places
# IngestCoordinatorMixin._validate_single_file()
# PreExecutionValidator.validate_file_structure()
# Both check file existence, format, size, etc.
```

### 2. Inconsistent Validation Rules
- Different components may apply different rules
- Updates must be made in multiple places
- Risk of validation drift over time

### 3. Poor Separation of Concerns
- Coordinators mix state management with validation
- No clear boundary between UI state and business rules

## Proposed Solution: Centralized Validation Service

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     UI Components                             │
│  (CSVMappingView, IngestView, PreExecutionPreview, etc.)     │
└─────────────┬───────────────────────────────┬─────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────────┐ ┌──────────────────────────────┐
│   Coordinator Mixins        │ │   PreExecutionValidator      │
│   (State Management)        │ │   (Orchestration)            │
└─────────────┬───────────────┘ └──────────────┬───────────────┘
              │                                 │
              └──────────────┬──────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │    MappingValidator          │
              │  (Centralized Validation)    │
              └──────────────────────────────┘
```

### Implementation Plan

#### 1. Create New Validation Service

**Location**: `arkumu/importer/services/mapping_validation/`

```python
# arkumu/importer/services/mapping_validation/validator.py

class MappingValidator:
    """
    Centralized validation service for all mapping-related validation.
    This is a stateless service that can be used by any component.
    """
    
    @staticmethod
    def validate_column_mappings(workspace_columns, file_columns):
        """Validate column mappings between workspace and files."""
        pass
    
    @staticmethod
    def validate_relationships(workspace_columns, fk_relationships):
        """Validate foreign key relationships."""
        pass
    
    @staticmethod
    def validate_file_structure(file_path, organization_code):
        """Validate file structure, encoding, readability."""
        pass
    
    @staticmethod
    def validate_data_types(workspace_columns, sample_data):
        """Validate data types match expectations."""
        pass
    
    @staticmethod
    def validate_mapping_completeness(mapping_config):
        """Validate mapping has all required components."""
        pass
```

#### 2. Refactor Existing Components

##### CSVMappingCoordinatorMixin
```python
def validate_mapping_structure(self, request, organization_id, file_columns=None):
    """
    Validate mapping structure - now delegates to MappingValidator.
    """
    from arkumu.importer.services.mapping_validation import MappingValidator
    
    # Get state from session
    workspace_columns = self.get_workspace_columns(request, organization_id)
    
    # Delegate to centralized validator
    return MappingValidator.validate_column_mappings(workspace_columns, file_columns)
```

##### IngestCoordinatorMixin
```python
def validate_selected_files(self, request, organization_id=None):
    """
    Validate selected files - now uses MappingValidator.
    """
    from arkumu.importer.services.mapping_validation import MappingValidator
    
    selected_files = self.get_selected_files(request, organization_id)
    validation_results = []
    
    for file_path in selected_files:
        issues = MappingValidator.validate_file_structure(file_path, organization.code)
        validation_results.extend(issues)
    
    return self._aggregate_validation_results(validation_results)
```

##### PreExecutionValidator
```python
def validate(self):
    """
    Orchestrate comprehensive validation using MappingValidator.
    """
    from arkumu.importer.services.mapping_validation import MappingValidator
    
    issues = []
    
    # Validate files
    for file_path in self.file_paths:
        issues.extend(MappingValidator.validate_file_structure(
            file_path, self.organization_code
        ))
    
    # Validate column mappings
    if self.mapping_config:
        mapping_result = MappingValidator.validate_column_mappings(
            self.mapping_config.get('workspace_columns', {}),
            self._extract_file_columns()
        )
        issues.extend(mapping_result.get('issues', []))
    
    # Validate relationships
    if self.mapping_config and 'fk_relationships' in self.mapping_config:
        issues.extend(MappingValidator.validate_relationships(
            self.mapping_config.get('workspace_columns', {}),
            self.mapping_config.get('fk_relationships', {})
        ))
    
    return PreExecutionValidationResult(issues=issues)
```

## Benefits of This Architecture

### 1. Single Source of Truth
- All validation rules in one place
- Easy to update and maintain
- Consistent validation across the application

### 2. Clear Separation of Concerns
- **Coordinators**: State management and UI orchestration
- **MappingValidator**: Business validation rules
- **PreExecutionValidator**: Validation orchestration

### 3. Reusability
- Any component can use MappingValidator
- No need to duplicate validation logic
- Easy to add new validation rules

### 4. Testability
- Stateless validator is easy to unit test
- Can test validation logic independently of UI state
- Clear test boundaries

### 5. Extensibility
- Easy to add new validation methods
- Can be extended without modifying existing code
- Supports plugin-style validation extensions

## Migration Strategy

### Phase 1: Create MappingValidator
1. Create the new service structure
2. Move validation logic from CSVMappingCoordinatorMixin.validate_mapping_structure
3. Add comprehensive unit tests

### Phase 2: Refactor Coordinators
1. Update CSVMappingCoordinatorMixin to use MappingValidator
2. Update IngestCoordinatorMixin to use MappingValidator
3. Ensure backward compatibility

### Phase 3: Refactor PreExecutionValidator
1. Remove duplicated validation logic
2. Update to use MappingValidator
3. Simplify to focus on orchestration

### Phase 4: Cleanup
1. Remove the pre_execution_validation directory (it's confusing)
2. Update all imports and documentation
3. Run comprehensive integration tests

## Example Usage

```python
# In any component that needs validation
from arkumu.importer.services.mapping_validation import MappingValidator

# Validate column mappings
result = MappingValidator.validate_column_mappings(
    workspace_columns={'col1': {...}, 'col2': {...}},
    file_columns=['col1', 'col2', 'col3']
)

# Check validation results
if result['missing_required_columns']:
    # Handle missing columns
    pass

# Validate file structure
issues = MappingValidator.validate_file_structure(
    's3://bucket/file.csv',
    'org-code'
)

# Check for errors
errors = [i for i in issues if i.severity == 'ERROR']
if errors:
    # Handle validation errors
    pass
```

## Conclusion

The current validation architecture has served its purpose but has become fragmented and difficult to maintain. By centralizing validation logic into a dedicated service, we can:

1. Eliminate code duplication
2. Ensure consistent validation rules
3. Improve maintainability
4. Enable better testing
5. Support future extensibility

The proposed MappingValidator service provides a clean, reusable solution that maintains clear separation of concerns while being easy to integrate with existing components.