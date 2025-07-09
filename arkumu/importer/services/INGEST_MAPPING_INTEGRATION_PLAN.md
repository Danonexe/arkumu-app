# Ingest UI Mapping Integration Implementation Plan

## Overview

This document outlines the implementation plan to integrate the powerful mapping and execution services from `@arkumu/importer/services/` into the ingest UI at `http://localhost:8000/importer/ingest/`. The goal is to leverage the full capabilities of the execution engine, mapping analysis, and phased processing for a more intelligent and robust import experience.

## Current State Analysis

### Existing Ingest Flow
1. **Organization Selection** → User selects organization from dropdown
2. **File Browser** → User browses and selects CSV files from S3 bucket
3. **Mapping Selection** → User optionally selects a pre-existing mapping
4. **Import Execution** → User clicks "Start Import" triggering `import_metadata.py` task

### Current Limitations
- No mapping analysis or validation before execution
- No file-to-dataset matching logic from mapping configuration
- No execution strategy selection based on mapping complexity
- No preview of what the mapping will do to the files
- Limited integration with the sophisticated execution services
- No phased processing visualization or control

### Existing Components to Leverage
- **Execution Engine**: `arkumu/importer/services/execution/execution_engine.py`
- **Mapping Adapter**: `arkumu/importer/services/mapping_consumer/mapping_adapter.py`
- **Config Translator**: `arkumu/importer/services/mapping_consumer/config_translator.py`
- **Validation Services**: `arkumu/importer/services/validation/validation.py`
- **Processing Strategies**: Multi-phase, entity-centric, streaming capabilities

## Implementation Plan

### Phase 1: Enhanced Mapping Integration

#### 1.1 Add Mapping Analysis View
**New HTMX Endpoint**: `/importer/ingest/mapping-analysis/`

```python
# arkumu/importer/views/ingest_views.py
@general_login_required
def mapping_analysis(request):
    """
    Analyze selected mapping and match it to selected files
    Returns detailed analysis of what the mapping will do
    """
    # Get selected mapping and files from session
    # Use MappingAdapter.translate_to_execution_config()
    # Analyze dataset requirements vs available files
    # Return execution strategy recommendations
```

**Key Features**:
- Analyze mapping complexity (phases, column types, relationships)
- Match mapping datasets to selected files
- Identify missing datasets or files
- Recommend execution strategy (entity-based vs mapping-based)
- Preview expected processing phases

#### 1.2 File-to-Dataset Matching Logic
**New Service**: `arkumu/importer/services/file_matching/`

```python
class FileDatasetMatcher:
    """
    Matches selected files to mapping datasets
    Handles various naming conventions and file structures
    """
    
    def match_files_to_datasets(self, selected_files, execution_config):
        """
        Returns mapping of dataset_name -> file_path
        Identifies unmatched files and missing datasets
        """
        
    def validate_file_structure(self, file_path, dataset_config):
        """
        Validates if file structure matches dataset expectations
        """
```

#### 1.3 Enhanced Execution Status Template
**Update**: `arkumu/importer/templates/importer/partials/execution_status.html`

**New Features**:
- Mapping complexity indicators
- File-to-dataset matching results
- Execution strategy selection
- Processing phase preview
- Validation status indicators

### Phase 2: Execution Enhancement

#### 2.1 Update import_metadata.py Task
**Enhanced Task**: `arkumu/importer/tasks/import_metadata.py`

```python
@db_task(retries=1, retry_delay=60)
def run_csv_import_workflow_with_mapping(
    # ... existing parameters ...
    mapping_id: Optional[str] = None,
    execution_strategy: str = "auto",  # auto, entity, mapping, streaming
    validation_mode: bool = True,
    file_dataset_mapping: Optional[Dict[str, str]] = None
):
    """
    Enhanced import task with full mapping integration
    """
    
    # 1. Load and validate mapping configuration
    if mapping_id:
        mapping_config = MappingAdapter().translate_to_execution_config(mapping_id)
        
        # 2. Validate files against mapping requirements
        validation_results = validate_mapping_files(file_dataset_mapping, mapping_config)
        
        # 3. Choose execution strategy
        if execution_strategy == "auto":
            execution_strategy = recommend_execution_strategy(mapping_config)
        
        # 4. Execute with appropriate processor
        if execution_strategy == "mapping":
            stats = MappingAwareProcessor().process_with_execution_config(
                execution_config=mapping_config,
                csv_sources=file_dataset_mapping,
                strategy=ProcessingStrategy.MULTI_PHASE
            )
        else:
            # Fall back to entity-based import
            stats = bridge_service.import_csv(...)
    
    # Enhanced progress tracking for phases
    # Better error handling and reporting
```

#### 2.2 Add Validation Step
**New Service**: `arkumu/importer/services/pre_execution_validation/`

```python
class PreExecutionValidator:
    """
    Validates mapping against selected files before execution
    Provides detailed validation reports
    """
    
    def validate_mapping_execution(self, mapping_config, file_paths):
        """
        Comprehensive validation of mapping against files
        """
        # File structure validation
        # Column mapping validation
        # Relationship validation
        # Resource requirements estimation
```

#### 2.3 Enhanced Progress Tracking
**Updates**: Cache-based progress tracking with phase information

```python
def update_cache_with_phase_info(status, message, progress, phase_info=None):
    """
    Enhanced cache updates with execution phase information
    """
    payload = {
        "status": status,
        "message": message, 
        "progress": progress,
        "current_phase": phase_info.get("current_phase") if phase_info else None,
        "total_phases": phase_info.get("total_phases") if phase_info else None,
        "phase_progress": phase_info.get("phase_progress") if phase_info else None
    }
```

### Phase 3: UI Improvements

#### 3.1 Execution Preview Panel
**New Template**: `arkumu/importer/templates/importer/partials/execution_preview.html`

**Features**:
- Show what datasets will be processed
- Display processing phases and order
- Estimate execution time and resources
- Show potential issues or warnings

#### 3.2 Strategy Recommendations
**Enhanced Logic**: Automatic strategy selection based on mapping complexity

```python
def recommend_execution_strategy(execution_config):
    """
    Analyze mapping and recommend optimal execution strategy
    """
    if has_complex_relationships(execution_config):
        return "mapping"  # Use multi-phase processing
    elif has_large_datasets(execution_config):
        return "streaming"  # Use chunked processing
    else:
        return "entity"  # Simple entity-based import
```

#### 3.3 Better Error Handling
**Enhanced Templates**: Better error display and recovery options

- Mapping validation errors with specific fixes
- File structure mismatch handling
- Execution phase failure recovery
- Clear error messages with actionable solutions

## Technical Implementation Details

### New Views to Add

1. **`mapping_analysis(request)`** - Analyze mapping and files
2. **`execution_strategy_selector(request)`** - Choose execution strategy
3. **`mapping_validation(request)`** - Validate mapping against files
4. **`execution_preview(request)`** - Preview what will happen
5. **`file_dataset_matching(request)`** - Match files to datasets

### New Templates to Create

1. **`execution_preview.html`** - Show execution plan
2. **`mapping_insights.html`** - Mapping complexity analysis
3. **`file_matching_results.html`** - File-to-dataset matching
4. **`strategy_selector.html`** - Execution strategy selection
5. **`validation_results.html`** - Mapping validation results

### Enhanced Session Management

```python
# Enhanced session structure
INGEST_SESSION_STRUCTURE = {
    'selected_files': [],
    'selected_mapping_id': None,
    'file_dataset_mapping': {},
    'execution_strategy': 'auto',
    'validation_results': {},
    'mapping_analysis': {},
    'execution_preview': {}
}
```

### Integration Points

1. **Mapping Selection** → **File Analysis** → **Execution Strategy** → **Import**
2. **MappingAdapter.translate_to_execution_config()** - Convert mapping to execution config
3. **MappingAwareProcessor** - For complex mappings with phases
4. **Validation Services** - Pre-execution validation
5. **Execution Engine** - Core processing with strategy selection

## Implementation Sequence

### Step 1: Core Integration (High Priority)
1. Add mapping analysis view and service
2. Create file-to-dataset matching logic
3. Update import_metadata.py task for execution config support
4. Enhance execution status template

### Step 2: UI Enhancement (Medium Priority)
1. Add execution strategy selection
2. Create execution preview panel
3. Implement validation results display
4. Add mapping insights visualization

### Step 3: Advanced Features (Low Priority)
1. Execution time estimation
2. Resource usage prediction
3. Advanced error recovery
4. Performance optimization recommendations

## Expected Benefits

1. **Intelligent Import Processing** - Automatic strategy selection based on mapping complexity
2. **Better Error Prevention** - Pre-execution validation catches issues early
3. **Improved User Experience** - Clear feedback on what will happen before import
4. **Enhanced Reliability** - Proper file-to-dataset matching reduces failures
5. **Full Service Integration** - Leverages all capabilities of the execution engine

## Testing Strategy

1. **Unit Tests** - Test mapping analysis and file matching logic
2. **Integration Tests** - Test end-to-end import workflow with mappings
3. **UI Tests** - Test HTMX interactions and template rendering
4. **Performance Tests** - Validate execution strategy recommendations
5. **Error Handling Tests** - Test validation and error recovery

## Rollout Plan

1. **Phase 1**: Deploy core integration features
2. **Phase 2**: Add UI enhancements and validation
3. **Phase 3**: Monitor performance and add advanced features
4. **Phase 4**: Optimize based on user feedback

This implementation will transform the ingest UI from a simple file upload interface into a sophisticated import orchestration system that fully leverages the powerful execution services architecture.