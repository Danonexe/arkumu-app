# Import Existing Mappings Feature - Implementation Plan

## Overview
Add functionality to import mapping definitions from JSON files stored in S3 metadata/ folder, making them available for use in the CSV import workflow.

## Architecture Components

### 1. Backend Services
**Location**: `arkumu/metadata/services/mapping/`

#### A. `mapping_import_service.py`
- **Purpose**: Handle mapping file discovery and import logic
- **Key Methods**:
  - `list_available_mapping_files(organization_id, s3_bucket)` - List JSON files in metadata/ folder
  - `validate_mapping_file(file_content)` - Validate JSON structure and required fields
  - `import_mapping_from_json(json_data, organization_id, created_by)` - Create Mapping object
  - `batch_import_mappings(file_list, organization_id, created_by)` - Import multiple files

#### B. Integration with existing S3UploadService
- **Purpose**: Reuse existing S3 connection and authentication
- **Location**: `arkumu/importer/services/file_upload/s3_upload_service.py`
- **Extension**: Add method to list files with metadata/ prefix

### 2. API Endpoints
**Location**: `arkumu/importer/views/ingest_views.py` (since this is related to the ingest workflow)

#### A. `list_importable_mappings` endpoint
- **URL**: `/importer/mappings/list-importable/`
- **Method**: GET
- **Purpose**: Return HTML list of available JSON mapping files
- **Response**: HTMX-compatible HTML with checkboxes for file selection

#### B. `import_selected_mappings` endpoint
- **URL**: `/importer/mappings/import/`
- **Method**: POST
- **Purpose**: Process selected mapping files and create Mapping objects
- **Response**: Success/error status with imported mapping names

### 3. Frontend Components

#### A. UI Button Addition
**Location**: `arkumu/importer/templates/importer/partials/navbar_mapping_controls.html`
- Add "Import Mappings" button next to "Create new mapping"
- Use similar styling and icon pattern

#### B. Modal/Dropdown Interface
**Template**: New partial `import_mappings_modal.html`
- Display available JSON files with checkboxes
- Show file metadata (name, date, size)
- Import progress indicator
- Success/error feedback

#### C. HTMX Integration
- Modal trigger on button click
- Dynamic file list loading
- Real-time import progress
- Auto-refresh mapping dropdown after successful import

### 4. Data Flow

#### A. File Discovery Flow
```
User clicks "Import Mappings" 
→ HTMX calls list_importable_mappings endpoint
→ Service queries S3 for metadata/*.json files
→ Returns HTML list with file details
→ User sees modal with available files
```

#### B. Import Flow
```
User selects files and clicks Import
→ HTMX calls import_selected_mappings endpoint
→ Service downloads and validates each JSON file
→ Creates Mapping objects with draft status
→ Returns success response with imported mapping names
→ Modal shows success message
→ Mapping dropdown refreshes to show new mappings
```

### 5. URL Configuration
**Location**: `arkumu/importer/urls.py`
- Add routes for new endpoints
- Follow existing naming patterns (e.g., `importer:list_importable_mappings`)

### 6. Expected JSON File Format
```json
{
  "name": "Product Import Mapping",
  "description": "Maps product CSV to CIDOC entities", 
  "mapping_config": { /* existing mapping configuration */ },
  "source_datasets": ["products", "inventory"],
  "metadata": {
    "exported_at": "2025-07-12T10:30:00Z",
    "exported_by": "user@example.com",
    "version": "1.0"
  }
}
```

### 7. Error Handling & Validation
- **File Format Validation**: Ensure JSON is valid and contains required fields
- **Name Conflict Resolution**: Handle duplicate mapping names within organization
- **S3 Access Errors**: Graceful handling of connection/permission issues
- **Partial Import Failures**: Continue processing remaining files if some fail

### 8. Security Considerations
- **Organization Scoping**: Only import mappings for current user's organization
- **File Type Validation**: Restrict to .json files only
- **Size Limits**: Prevent import of excessively large files
- **Content Sanitization**: Validate mapping_config structure

### 9. Testing Strategy
- **Unit Tests**: Test import service methods individually
- **Integration Tests**: Test full import workflow with mock S3 files
- **UI Tests**: Test HTMX interactions and modal behavior
- **Error Scenarios**: Test various failure modes and edge cases

## Implementation Order
1. Create mapping import service with S3 integration
2. Add API endpoints to importer views
3. Create modal template and UI components
4. Update navbar controls template
5. Add URL routing
6. Implement error handling and validation
7. Add tests and documentation

## File Structure
```
arkumu/
├── metadata/
│   └── services/
│       └── mapping/
│           └── mapping_import_service.py     # NEW
├── importer/
│   ├── views/
│   │   └── ingest_views.py                  # MODIFY - add endpoints
│   ├── urls.py                              # MODIFY - add routes
│   └── templates/
│       └── importer/
│           ├── partials/
│           │   ├── navbar_mapping_controls.html  # MODIFY - add button
│           │   └── import_mappings_modal.html     # NEW
│           └── modals/
│               └── import_mappings_modal.html     # NEW (alternative location)
```