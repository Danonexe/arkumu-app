# ResourceManager Test Fixes Summary

## Issues Fixed

### 1. URI Format Mismatch
**Problem**: Tests expected underscores in URIs (e.g., "test_dataset") but the `slugify_uri_part` function converts underscores to hyphens (e.g., "test-dataset").

**Solution**: Updated all test assertions to expect hyphenated URIs instead of underscored ones.

**Files Modified**:
- `arkumu/importer/tests/services/execution/test_resource_manager.py`
  - Updated URI assertions in:
    - `test_generate_dataset_uri`
    - `test_generate_column_uri`
    - `test_generate_row_uri`
    - `test_generate_cell_uri`
    - `test_generate_entity_uri`
    - `test_generate_junction_uri`
    - `test_extract_row_id_from_uri`
    - `test_extract_column_name_from_uri`
    - `test_initialization`

### 2. Mock Resource Validation Errors
**Problem**: Mock objects weren't properly configured with the Django model spec, causing `ValueError: Cannot assign "<Mock id='...'>": "Triple.subject" must be a "Resource" instance.`

**Solution**: 
1. Updated the `test_resources` fixture to use `Mock(spec=Resource)` with proper `_meta` and `_state` attributes
2. Updated all test methods that create Mock resources to use the `create_mock_resource` helper function

**Files Modified**:
- `arkumu/importer/tests/services/execution/conftest.py`
  - Updated `test_resources` fixture to create properly spec'd Mock objects
  - Fixed URIs in the fixture to use hyphenated format

- `arkumu/importer/tests/services/execution/test_resource_manager.py`
  - Updated tests to use `create_mock_resource` helper:
    - `test_create_cell_resources_bulk`
    - `test_get_existing_resources_bulk`
    - `test_create_property_triple`
    - `test_create_relationship_triple`
    - `test_bulk_cell_creation_performance`
    - `test_bulk_triple_creation_performance`

## Result
All 41 tests in `test_resource_manager.py` are now passing successfully.