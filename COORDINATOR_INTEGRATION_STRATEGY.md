# Coordinator Integration Strategy

## Overview

This document outlines the strategy for integrating the CSV mapping coordinator infrastructure with the new ingest coordinator to maximize code reuse while avoiding duplication of logic.

## Current Architecture Analysis

### Existing Components

1. **CSVMappingCoordinatorMixin** (`arkumu/metadata/views/csv_mapping/mixins/coordinator.py`)
   - Complex state manager for *building* data mappings
   - Handles datasets, columns, FK relationships, workspace management
   - Serializes/deserializes mapping configurations
   - 1,500+ lines of sophisticated mapping logic

2. **CSVMappingTemplateHelperMixin** (`arkumu/metadata/views/csv_mapping/mixins/template_helpers.py`)
   - Template rendering helpers for CSV mapping UI
   - Workspace rendering, dataset badges, column management
   - Tightly coupled to mapping workspace data structures

3. **IngestCoordinatorMixin** (`arkumu/importer/mixins/ingest_coordinator.py`)
   - Simple state manager for *using* pre-existing mappings
   - Handles organization selection, file selection, mapping selection
   - ~400 lines focused on execution workflow

4. **MappingCoordinator** (`arkumu/metadata/services/mapping/mapping_coordinator.py`)
   - Backend service that processes mapping configurations
   - Builds processing plans from GUI configurations
   - Well-decoupled, no changes needed

### Key Duplication Identified

**Organization Management**: Both `CSVMappingCoordinatorMixin` and `IngestCoordinatorMixin` have nearly identical code for:
- `get_current_organization()`
- `set_current_organization()`
- `clear_current_organization()`
- Organization context preparation

## Integration Strategy

### Phase 1: Create Base Coordinator Mixin

Create a new `BaseCoordinatorMixin` to centralize shared functionality:

```python
# arkumu/common/mixins/base_coordinator.py
class BaseCoordinatorMixin:
    """Base coordinator for shared session and organization management."""
    
    def get_current_organization(self, request):
        """Centralized organization retrieval logic."""
        
    def set_current_organization(self, request, organization_id):
        """Centralized organization setting logic."""
        
    def clear_current_organization(self, request):
        """Centralized organization clearing logic."""
        
    def get_organization_context(self, request):
        """Standardized organization context for templates."""
        
    def handle_organization_change(self, request, new_organization_id):
        """Base organization change handler - subclasses can extend."""
        
    def get_session_key(self, base_key, organization_id=None):
        """Standardized session key generation with prefixes."""
```

### Phase 2: Refactor Existing Coordinators

#### Update IngestCoordinatorMixin

```python
class IngestCoordinatorMixin(BaseCoordinatorMixin):
    """Inherits from base coordinator, removes duplicate logic."""
    
    # Remove duplicate organization methods
    # Keep file selection, mapping selection logic
    # Use standardized session keys via get_session_key()
```

#### Update CSVMappingCoordinatorMixin

```python
class CSVMappingCoordinatorMixin(CSVDataMixin, MappingWorkspaceMixin, BaseCoordinatorMixin):
    """Add base coordinator to inheritance chain."""
    
    # Remove duplicate organization methods
    # Keep all complex mapping logic
    # Use standardized session keys via get_session_key()
```

### Phase 3: Session Key Standardization

Implement consistent session key patterns:

```python
# Current inconsistent keys:
'selected_datasets_{organization_id}'      # CSV mapping
'workspace_columns_{organization_id}'      # CSV mapping  
'ingest_current_organization'              # Ingest
'ingest_selected_files'                    # Ingest

# Proposed standardized keys:
'csv_mapping_selected_datasets_{org_id}'
'csv_mapping_workspace_columns_{org_id}'
'csv_mapping_current_organization'
'ingest_current_organization'
'ingest_selected_files_{org_id}'
'ingest_selected_mapping_{org_id}'
```

### Phase 4: Integration Points

#### Template Helper Reuse Strategy

The `CSVMappingTemplateHelperMixin` is NOT directly reusable for ingest because:
- Ingest UI is simpler (file selection + mapping selection)
- CSV mapping UI is complex (workspace management + relationship building)

**Solution**: Create targeted helper methods in `IngestCoordinatorMixin` for ingest-specific templates.

#### MappingCoordinator Service Integration

The `MappingCoordinator` service can be used directly by ingest views:

```python
# In ingest execution view:
def execute_import(self, request):
    # Get selected mapping from IngestCoordinatorMixin
    selected_mapping = self.get_selected_mapping(request)
    
    # Load mapping configuration
    mapping = Mapping.objects.get(id=selected_mapping['id'])
    
    # Use MappingCoordinator to build processing plan
    coordinator = MappingCoordinator(organization_id)
    plan = coordinator.build_processing_plan(
        mapping.mapping_config['workspace_columns'],
        mapping.mapping_config['workspace_datasets']
    )
    
    # Execute import with plan
    importer.execute_with_plan(plan, selected_files)
```

## Benefits of This Approach

### Code Reuse Maximized
- Eliminates ~100 lines of duplicate organization management
- Centralizes session key generation
- Creates reusable base for future coordinators

### Minimal Refactoring Required
- No changes to core mapping logic
- No changes to MappingCoordinator service
- Preserves existing CSV mapping functionality
- Simple inheritance chain additions

### Architectural Improvements
- Clear separation of concerns
- Consistent session management patterns
- Standardized coordinator interface
- Future-proof extensibility

### DRY Principle Enforcement
- Single source of truth for organization management
- Consistent session key patterns
- Centralized state change handling

## Implementation Plan

### Step 1: Create BaseCoordinatorMixin
- Extract organization management from existing coordinators
- Implement standardized session key generation
- Add base organization change handling

### Step 2: Update IngestCoordinatorMixin
- Inherit from BaseCoordinatorMixin
- Remove duplicate organization code
- Update to use standardized session keys
- Test ingest workflow

### Step 3: Update CSVMappingCoordinatorMixin
- Add BaseCoordinatorMixin to inheritance
- Remove duplicate organization code
- Update to use standardized session keys
- Test CSV mapping workflow

### Step 4: Integration Testing
- Verify both systems work independently
- Test organization switching between interfaces
- Validate session isolation
- Performance testing

## Session Management Strategy

### Isolation by Prefix
```python
# CSV Mapping sessions:
csv_mapping_selected_datasets_{org_id}
csv_mapping_workspace_columns_{org_id}
csv_mapping_loaded_mapping_{org_id}

# Ingest sessions:
ingest_selected_files_{org_id}
ingest_selected_mapping_{org_id}
ingest_current_organization

# Shared sessions:
current_organization  # Base coordinator manages this
```

### Cross-Interface Communication
When loading a mapping in the ingest interface:
1. IngestCoordinatorMixin gets mapping from database
2. MappingCoordinator processes the mapping configuration
3. No need to duplicate CSV mapping session state

## Future Extensions

This architecture enables:
- Additional coordinator types (e.g., ExportCoordinatorMixin)
- Cross-interface state sharing when needed
- Consistent patterns for new workflows
- Centralized session debugging and monitoring

## Risk Mitigation

### Backward Compatibility
- Existing CSV mapping functionality preserved
- No breaking changes to current interfaces
- Gradual migration possible

### Testing Strategy
- Unit tests for BaseCoordinatorMixin
- Integration tests for each coordinator
- End-to-end workflow testing
- Session isolation validation

### Rollback Plan
- BaseCoordinatorMixin can be developed independently
- Coordinators can be updated one at a time
- Easy to revert individual coordinator changes
- No database schema changes required

## Conclusion

This integration strategy achieves maximum code reuse while maintaining clean separation of concerns. The approach eliminates duplication, improves maintainability, and creates a solid foundation for future coordinator development.

The key insight is that while the coordinators serve different purposes (building vs. using mappings), they share common infrastructure needs that can be centralized without compromising their specific functionality.