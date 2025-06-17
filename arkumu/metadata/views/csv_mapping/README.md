# CSV Mapping Views - Mixin-Based Architecture

## Overview
This package contains views for the CSV mapping editor using **mixin-based architecture** for clean separation of concerns and reusable functionality.

**Purpose:** Design import mappings for SmartBulkUpdaterPolars

## Mixin Architecture

### ✅ COMPLETED: Mixin Structure
**Location:** `mixins/` folder

**Files Created:**
- `mixins/__init__.py` - Package initialization with imports
- `mixins/base.py` - **OrganizationMixin** (organization discovery and management)
- `mixins/csv_data.py` - **CSVDataMixin** (CSV dataset loading and preview)
- `mixins/workspace.py` - **MappingWorkspaceMixin** (column workspace and session management)
- `mixins/import_strategy.py` - **ImportStrategyMixin** (import configuration and strategy management)

**Architecture Benefits:**
- ✅ **Separation of Concerns**: Each mixin handles specific functionality
- ✅ **Reusability**: Mixins can be combined in different views as needed
- ✅ **Maintainability**: Changes to specific functionality isolated to relevant mixin
- ✅ **Testability**: Each mixin can be tested independently
- ✅ **Extensibility**: New mixins can be added without affecting existing ones

## Step-by-Step Implementation Status

## ✅ Step 1: COMPLETE - Mixin Architecture
**Main Editor View + Mixin Infrastructure**

**Class-Based Views Created:**
- `CSVMappingEditorView` - Main editor using all 4 mixins
- `UpdateImportStrategyView` - Import strategy management (ready to use)
- Placeholder views for Steps 2-4 with proper mixin inheritance

**Function Wrapper:**
- `csv_mapping_editor_view()` - Maintains URL compatibility

**Functionality:**
- ✅ Organization discovery and validation
- ✅ CSV dataset discovery and filtering
- ✅ Session-based workspace management  
- ✅ Import strategy configuration
- ✅ Enhanced context with statistics and summaries

## ⏳ Step 2: PENDING
**Dataset Card Views (Using Mixins)**

**Views to Implement:**
- `CSVDatasetCardView` → Complete implementation using CSVDataMixin + MappingWorkspaceMixin
- `ToggleDatasetSelectionView` → Complete implementation using CSVDataMixin

**Templates to Update:**
- `partials/dataset_badges.html` - Update URL references to new views
- Create `partials/csv_dataset_card.html` - Dataset preview template

## ⏳ Step 3: PENDING  
**Column Workspace Management (Using Mixins)**

**Views to Implement:**
- `AddColumnToWorkspaceView` → Complete implementation using MappingWorkspaceMixin
- `RemoveColumnFromWorkspaceView` → Complete implementation using MappingWorkspaceMixin
- Additional column management views as needed

**Templates to Update:**
- `partials/selected_columns_workspace.html`
- `partials/column_badges.html`
- `partials/column_item.html`

## ⏳ Step 4: PENDING
**FK Relationship Configuration (Using Mixins)**

**Views to Implement:**
- `ConfigureFKRelationshipView` → Complete implementation using MappingWorkspaceMixin
- Additional FK configuration views as needed

**Templates to Update:**
- `partials/inline_fk_form.html`

## Mixin Details

### OrganizationMixin
```python
# Key Methods:
get_organization_id_from_request(request)
get_available_organizations(use_cache=True)
validate_organization_exists(organization_id)
get_organization_context(request)
```

### CSVDataMixin
```python
# Key Methods:
get_csv_datasets_for_organization(organization_id)
get_dataset_preview(source, dataset_name, limit=50)
get_selected_datasets_with_details(request, organization_id, csv_datasets)
toggle_dataset_selection(request, organization_id, dataset_name)
```

### MappingWorkspaceMixin
```python
# Key Methods:
get_workspace_columns(request, organization_id)
add_column_to_workspace(request, organization_id, column_id, ...)
update_column_configuration(request, organization_id, column_id, **config)
set_anchor_column(request, organization_id, column_id)
get_workspace_statistics(request, organization_id)
```

### ImportStrategyMixin
```python
# Key Methods:
get_import_strategy(request, organization_id)
update_import_strategy(request, organization_id, strategy_updates)
validate_import_strategy(strategy)
generate_smartbulkupdater_config(request, organization_id, selected_columns)
```

## URL Mapping
```
/metadata/csv-mapping-editor/           -> CSVMappingEditorView (READY)
/metadata/update-import-strategy/       -> UpdateImportStrategyView (READY)
/metadata/csv-dataset-card/             -> CSVDatasetCardView [Step 2]
/metadata/toggle-csv-dataset/           -> ToggleDatasetSelectionView [Step 2]
/metadata/add-column-to-workspace/      -> AddColumnToWorkspaceView [Step 3]
/metadata/remove-column-from-workspace/ -> RemoveColumnFromWorkspaceView [Step 3]
/metadata/configure-fk-relationship/    -> ConfigureFKRelationshipView [Step 4]
```

## Testing Commands
```bash
# Test Step 1 (main editor with mixin architecture)
python manage.py runserver
# Visit: http://localhost:8000/metadata/csv-mapping-editor/?organization=rsh

# Test import strategy updates
# POST to: http://localhost:8000/metadata/update-import-strategy/
# Data: {'update_strategy': 'UPDATE_EXISTING', 'organization': 'rsh'}
```

## Next Steps
The mixin architecture is complete and ready for step-by-step implementation:
1. **Step 2:** Implement dataset card views using existing mixins
2. **Step 3:** Implement column workspace management using existing mixins  
3. **Step 4:** Implement FK relationship configuration using existing mixins

Each step will be much faster now since the core functionality is already implemented in the mixins! 