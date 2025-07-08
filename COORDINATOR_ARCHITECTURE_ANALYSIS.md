# Coordinator Architecture Analysis

**Status: BROKEN - Multiple Critical Issues**

## Overview

The coordinator architecture consists of three main mixins that are supposed to work together to manage application state across different interfaces. However, there are fundamental coordination issues causing data loss and inconsistent behavior.

## Current Architecture

### 1. BaseCoordinatorMixin (`arkumu/common/mixins/base_coordinator.py`)
**Purpose**: Shared functionality for all coordinators
**Session Prefix**: `base`
**Key Methods**:
- `get_current_organization(request)` - Shared org state
- `set_current_organization(request, org_id)` - Set shared org
- `get_current_mapping(request)` - Shared mapping state
- `set_current_mapping(request, mapping_id, name, org_id)` - Set shared mapping
- `clear_current_mapping(request)` - Clear shared mapping
- `handle_organization_change(request, new_org_id)` - Handle org changes

**Session Keys**:
- `current_organization` - Shared across all coordinators
- `current_mapping` - Shared across all coordinators

### 2. CSVMappingCoordinatorMixin (`arkumu/metadata/views/csv_mapping/mixins/coordinator.py`)
**Purpose**: CSV mapping editor state management
**Session Prefix**: `csv_mapping`
**Key Methods**:
- `get_selected_dataset_names(request, org_id)` - Dataset selection
- `get_workspace_columns(request, org_id)` - Workspace columns
- `serialize_current_mapping_state(request, org_id)` - Save mapping
- `deserialize_mapping_state(request, org_id, config)` - Load mapping
- `reset_all_coordinator_state(request, org_id)` - Clear all state

**Session Keys**:
- `csv_mapping_selected_datasets_{org_id}` - Selected datasets
- `csv_mapping_workspace_columns_{org_id}` - Workspace columns
- `csv_mapping_column_selection_{org_id}` - Column selections
- `csv_mapping_all_datasets_fk_{org_id}` - FK datasets cache

### 3. IngestCoordinatorMixin (`arkumu/importer/mixins/ingest_coordinator.py`)
**Purpose**: Ingest interface state management
**Session Prefix**: `ingest`
**Key Methods**:
- `get_selected_files(request, org_id)` - Selected files
- `set_selected_files(request, files, org_id)` - Set selected files
- `get_file_browser_context(request, org_id)` - File browser data
- `get_ingest_context(request)` - Complete ingest context

**Session Keys**:
- `ingest_selected_files_{org_id}` - Selected files

## Critical Issues

### 1. Session Key Management Chaos
**Problem**: Multiple overlapping session key systems
- Base coordinator uses shared keys (`current_organization`, `current_mapping`)
- CSV coordinator uses prefixed keys (`csv_mapping_*`)
- Ingest coordinator uses prefixed keys (`ingest_*`)
- OrganizationMixin uses different keys (`last_selected_organization`)

**Impact**: State gets lost because different views look for different keys

### 2. Mapping State Persistence Failure
**Problem**: Mapping state is not properly coordinated between views
- CSV mapping editor stores mapping in workspace columns
- Base coordinator stores mapping metadata in `current_mapping`
- When navigating between views, only metadata persists, not workspace state

**Impact**: User loads mapping, navigates to ingest, returns to CSV editor → mapping gone

### 3. Organization Change Handling Inconsistency
**Problem**: Different views handle organization changes differently
- CSV mapping editor requires URL parameter (`?organization=xyz`)
- Ingest page can use session fallback
- Storage dashboard uses different pattern
- Organization change triggers aggressive state clearing

**Impact**: Navigation between views incorrectly detected as organization changes

### 4. Duplicate Method Implementations
**Problem**: Multiple implementations of similar functionality
- `get_current_mapping()` in BaseCoordinatorMixin
- `is_mapping_loaded()` in CSVMappingCoordinatorMixin
- Different mapping clearing methods across coordinators

**Impact**: Inconsistent behavior and maintenance nightmare

### 5. State Restoration Logic Broken
**Problem**: CSV mapping editor restoration logic is flawed
- Uses wrong session key (`loaded_mapping_{org_id}` vs `current_mapping`)
- Calls non-existent methods (`get_full_coordinator_context()`)
- Doesn't properly restore workspace state after deserialization

**Impact**: Mapping loads in navbar but workspace remains empty

## Session Key Conflicts

### Current Session Keys (Duplicates and Conflicts)
```
# Organization State
current_organization          # BaseCoordinatorMixin
last_selected_organization    # OrganizationMixin
organization_id               # Various places

# Mapping State
current_mapping              # BaseCoordinatorMixin (shared)
loaded_mapping_{org_id}      # CSV views (legacy, conflicting)

# CSV Mapping State
csv_mapping_selected_datasets_{org_id}
csv_mapping_workspace_columns_{org_id}
csv_mapping_column_selection_{org_id}
csv_mapping_all_datasets_fk_{org_id}

# Ingest State
ingest_selected_files_{org_id}
```

## Method Inventory

### BaseCoordinatorMixin Methods
- ✅ `get_current_organization(request)`
- ✅ `set_current_organization(request, org_id)`
- ✅ `clear_current_organization(request)`
- ✅ `get_current_mapping(request)`
- ✅ `set_current_mapping(request, mapping_id, name, org_id)`
- ✅ `clear_current_mapping(request)`
- ✅ `handle_organization_change(request, new_org_id)`
- ✅ `get_organization_context(request)`
- ✅ `get_session_key(base_key, org_id)`
- ❌ `clear_organization_specific_state(request, org_id)` - No-op, needs subclass implementation

### CSVMappingCoordinatorMixin Methods
- ✅ `get_selected_dataset_names(request, org_id)`
- ✅ `get_workspace_columns(request, org_id)`
- ✅ `serialize_current_mapping_state(request, org_id)`
- ✅ `deserialize_mapping_state(request, org_id, config)`
- ✅ `reset_all_coordinator_state(request, org_id)`
- ❌ `get_full_coordinator_context(request, org_id)` - MISSING METHOD
- ✅ `is_mapping_loaded(request)` - Duplicates BaseCoordinatorMixin functionality
- ✅ `validate_workspace_consistency(request, org_id)`

### IngestCoordinatorMixin Methods
- ✅ `get_selected_files(request, org_id)`
- ✅ `set_selected_files(request, files, org_id)`
- ✅ `get_file_browser_context(request, org_id)`
- ✅ `get_ingest_context(request)`
- ✅ `reset_ingest_state(request)`

## Root Cause Analysis

### The Fundamental Problem
The coordinators are **not actually coordinating**. They're three separate state management systems that happen to inherit from the same base class but don't properly share state or coordinate with each other.

### Specific Issues
1. **Session Key Fragmentation**: Each coordinator uses its own session keys with different naming patterns
2. **State Isolation**: No mechanism to sync state between coordinators
3. **Mapping Persistence**: Only metadata persists, not actual workspace state
4. **Organization Context**: Different views use different organization detection methods
5. **Method Duplication**: Same functionality implemented multiple times

## Immediate Fixes Needed

### 1. Standardize Session Key Usage
- All coordinators should use the same session keys for shared state
- Remove duplicate session key systems
- Implement proper session key hierarchy

### 2. Fix Mapping State Persistence
- Store complete mapping state in shared session
- Implement proper deserialization in CSV mapping editor
- Ensure workspace state survives navigation

### 3. Unify Organization Detection
- All views should use the same organization detection logic
- Remove URL parameter requirement from CSV mapping editor
- Implement consistent session fallback

### 4. Remove Method Duplication
- Consolidate mapping methods in BaseCoordinatorMixin
- Remove duplicate implementations
- Ensure all coordinators use shared methods

### 5. Implement True Coordination
- Create mechanism for coordinators to sync state
- Implement proper state change notifications
- Ensure cross-view state consistency

## Recommended Architecture

### Phase 1: Emergency Fixes
1. Fix CSV mapping editor to use `current_mapping` session key
2. Implement proper workspace state restoration
3. Standardize organization detection across all views

### Phase 2: Architectural Cleanup
1. Consolidate all shared state in BaseCoordinatorMixin
2. Remove duplicate session keys and methods
3. Implement proper state synchronization

### Phase 3: True Coordination
1. Create coordinator event system for state changes
2. Implement cross-view state validation
3. Add comprehensive state debugging tools

## Current Status: BROKEN

The coordinator architecture is fundamentally broken and needs immediate attention. The current implementation causes:
- Data loss when navigating between views
- Inconsistent user experience
- Maintenance nightmare with duplicate code
- Session state conflicts

**Priority**: CRITICAL - Fix immediately to restore basic functionality