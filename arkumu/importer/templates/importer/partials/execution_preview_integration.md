# Execution Preview Panel Integration

## Overview
The execution preview panel provides users with a comprehensive view of what will happen during import execution before they start the process. It integrates seamlessly with the existing mapping analysis service and supports both mapping-based and non-mapping workflows.

## Files Created

### 1. `/arkumu/importer/templates/importer/partials/execution_preview.html`
- **Purpose**: Advanced execution preview for mapping-based workflows
- **Features**:
  - Dataset processing overview with file matching
  - Processing timeline with phases
  - Execution strategy recommendations
  - Resource usage estimates
  - Issues and warnings display
  - Detailed execution plan (expandable)
  - Interactive features (refresh, export, auto-refresh)
  - Print-friendly styling

### 2. `/arkumu/importer/templates/importer/partials/execution_preview_simple.html`
- **Purpose**: Simple execution preview for non-mapping workflows
- **Features**:
  - Basic file processing summary
  - Simple processing phases
  - Resource estimates
  - Print functionality

### 3. `/arkumu/importer/templates/importer/partials/execution_status.html` (Modified)
- **Changes**: Added conditional execution preview integration
- **Logic**: Shows advanced preview for mapping workflows, simple preview otherwise

## Integration Points

### 1. Data Source Integration
- **Service**: `analyze_mapping` view in `ingest_views.py`
- **Data Flow**: 
  - User clicks "Analyze Mapping" button
  - `analyze_mapping` endpoint returns comprehensive analysis data
  - JavaScript function `updateExecutionPreview()` processes the response
  - Preview panels are populated with analysis results

### 2. HTMX Integration
- **Triggers**: 
  - `mappingSelected` - when mapping is selected
  - `fileSelectionChanged` - when files are selected/deselected
- **Auto-refresh**: Automatically updates preview when selections change
- **Progressive Enhancement**: Works with or without JavaScript

### 3. Template Integration
- **Conditional Rendering**: 
  ```django
  {% if selected_mapping %}
      {% include 'importer/partials/execution_preview.html' %}
  {% else %}
      {% include 'importer/partials/execution_preview_simple.html' %}
  {% endif %}
  ```

## Data Structure Expected

### From `analyze_mapping` Response:
```json
{
  "success": true,
  "mapping_info": {
    "id": "mapping_id",
    "name": "mapping_name",
    "datasets": [...],
    "total_columns": 50,
    "fk_relationships": 5,
    "external_ontologies": 2
  },
  "file_analysis": {
    "total_files": 10,
    "files_by_dataset": {...},
    "unique_datasets": [...]
  },
  "dataset_matching": {
    "match_percentage": 85,
    "matched_datasets": [...],
    "missing_datasets": [...],
    "extra_files": [...]
  },
  "complexity_analysis": {
    "complexity_level": "medium",
    "complexity_factors": [...]
  },
  "execution_strategy": {
    "recommended_strategy": "parallel",
    "strategy_reason": "...",
    "estimated_duration": "5-10 minutes",
    "estimated_memory": "Medium"
  },
  "processing_phases": [...],
  "recommendations": [...],
  "readiness_status": {
    "status": "ready",
    "status_message": "Ready to execute",
    "issues": [],
    "warnings": []
  }
}
```

## Key Features

### 1. Dataset Processing Overview
- Shows which datasets will be processed
- Displays file matching status
- Highlights missing or extra files

### 2. Processing Timeline
- Visual timeline of processing phases
- Estimated duration for each phase
- Strategy-based phase organization

### 3. Execution Strategy Display
- Recommended processing strategy
- Complexity assessment
- Resource usage estimates

### 4. Issues and Warnings
- Real-time validation feedback
- Color-coded alerts (error, warning, success)
- Actionable recommendations

### 5. File Matching Summary
- Match percentage visualization
- Detailed file-to-dataset mapping
- Missing dataset warnings

### 6. Interactive Features
- Expandable detailed execution plan
- Auto-refresh toggle
- Export functionality
- Print-friendly styling

## Usage

### For Mapping-based Workflows:
1. User selects files and mapping
2. User clicks "Analyze Mapping" (or auto-triggered)
3. Advanced preview appears with comprehensive analysis
4. User can review all aspects before execution

### For Non-mapping Workflows:
1. User selects files (no mapping required)
2. Simple preview appears immediately
3. Basic processing information is displayed
4. User can proceed with execution

## CSS Classes and Styling

### Key CSS Classes:
- `.execution-preview-container`: Main container with animations
- `.progress-bar-animation`: Animated progress bars
- Print-specific styles for professional output

### DaisyUI/Tailwind Integration:
- Uses existing component patterns (cards, badges, alerts)
- Follows established color schemes
- Responsive design for mobile/desktop

## JavaScript Functions

### Core Functions:
- `updateExecutionPreview(analysisData)`: Updates all preview sections
- `toggleExecutionDetails()`: Expands/collapses detailed plan
- `refreshExecutionPreview()`: Manually triggers analysis
- `exportExecutionPreview()`: Exports preview data as JSON
- `toggleAutoRefresh(enabled)`: Controls auto-refresh behavior

### Event Listeners:
- Listens for mapping analysis completion
- Responds to file selection changes
- Handles HTMX events for seamless updates

## Testing

### Manual Testing Checklist:
1. **File Selection**: Verify preview updates when files are selected
2. **Mapping Selection**: Confirm advanced preview appears with mapping
3. **Analysis Trigger**: Test "Analyze Mapping" button functionality
4. **Auto-refresh**: Verify preview updates automatically
5. **Export Feature**: Test JSON export functionality
6. **Print Styling**: Verify print-friendly output
7. **Responsive Design**: Test on mobile/tablet/desktop
8. **Error Handling**: Test with invalid mappings or missing files

### Browser Compatibility:
- Modern browsers with ES6+ support
- Progressive enhancement for older browsers
- Graceful degradation without JavaScript

## Future Enhancements

### Potential Improvements:
1. **Real-time Progress**: Show live progress during analysis
2. **Comparison Mode**: Compare different execution strategies
3. **Historical Data**: Show previous execution statistics
4. **Performance Metrics**: Display detailed performance predictions
5. **Resource Monitoring**: Real-time resource usage tracking
6. **Batch Operations**: Support for multiple mapping comparisons

### Integration Opportunities:
1. **Task Queue Integration**: Show queue position and estimated wait time
2. **Resource Monitoring**: Display current system load
3. **Notification System**: Alert users when analysis completes
4. **Dashboard Integration**: Summary cards for main dashboard
5. **API Endpoints**: RESTful endpoints for external integrations

## Security Considerations

### Current Security:
- Uses Django's built-in CSRF protection
- Respects user permissions and organization access
- No sensitive data exposure in client-side code

### Recommendations:
- Sanitize all user inputs in JavaScript
- Validate file paths and mapping IDs server-side
- Implement rate limiting for analysis requests
- Log all execution preview requests for auditing

## Performance Considerations

### Optimization Strategies:
- Client-side caching of analysis results
- Debounced auto-refresh to prevent excessive requests
- Lazy loading of detailed execution plans
- Progressive disclosure to reduce initial load

### Monitoring:
- Track analysis request frequency
- Monitor JavaScript execution time
- Measure template rendering performance
- Monitor memory usage during preview updates