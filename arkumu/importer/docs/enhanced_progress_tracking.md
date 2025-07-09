# Enhanced Progress Tracking System

## Overview

The enhanced progress tracking system provides comprehensive phase-based progress monitoring for import operations with mapping-aware complexity estimation. This system improves user experience by providing detailed, accurate progress information during complex import workflows.

## Key Features

### 1. Phase-Based Progress Tracking

The system tracks progress through multiple phases of import operations:

#### Single File Import Phases:
- **initialization**: Preparing import task
- **file_download**: Downloading file from S3
- **mapping_validation**: Validating mapping configuration
- **file_validation**: Validating file structure
- **strategy_selection**: Selecting execution strategy
- **data_import**: Importing data
- **finalization**: Finalizing import

#### Directory Import Phases:
- **initialization**: Initializing directory import
- **discovery**: Discovering CSV files
- **download**: Downloading files
- **processing**: Processing CSV files
- **finalization**: Finalizing directory import

#### Structured Error Handling Phases:
- **file_download**: Downloading and preparing file
- **mapping_validation**: Validating mapping configuration
- **data_import**: Importing data with error tracking
- **finalization**: Finalizing and reporting results

### 2. Mapping-Aware Progress Estimation

The system analyzes mapping complexity to provide more accurate progress estimates:

#### Complexity Metrics:
- **Dataset Count**: Number of datasets in mapping
- **Column Count**: Total number of columns across all datasets
- **Relationship Count**: Number of relationships between datasets
- **Foreign Key Count**: Number of foreign key relationships
- **Transformation Count**: Number of data transformations
- **Validation Rule Count**: Number of validation rules

#### Complexity-Based Adjustments:
- **Mapping Validation**: Scales with dataset count and validation rules
- **File Validation**: Scales with column count and relationships
- **Data Import**: Most complex phase, scales with all metrics
- **Finalization**: Scales with output complexity

### 3. Enhanced Cache Structure

The enhanced cache payload includes:

```python
{
    "status": "processing",
    "message": "Processing message",
    "progress": 45,  # Overall progress percentage
    "timestamp": "2025-01-XX...",
    "phase_info": {
        "current_phase": "data_import",
        "current_phase_index": 5,
        "total_phases": 7,
        "phase_progress": 60,  # Progress within current phase
        "phase_description": "Importing data",
        "execution_strategy": "mapping_driven"
    },
    "details": {
        "complexity_score": 15.5,
        "estimated_duration": 45.2,
        "complexity_factor": 1.8
    }
}
```

### 4. Frontend Integration

#### Task Status Poller Template Updates:
- Displays current phase information
- Shows phase progress alongside overall progress
- Provides execution strategy context
- Enhanced tooltips with phase descriptions

#### Directory Import Status Updates:
- Overall progress bar
- Phase-specific progress bar
- File processing counts
- Phase descriptions and strategy information

## Implementation Details

### Core Functions

#### `update_cache_with_phase_info()`
Enhanced cache update function that supports phase information:

```python
def update_cache_with_phase_info(status: str, message: str, progress: int, 
                               phase_info: Optional[Dict] = None, 
                               details: Optional[Dict] = None, 
                               error_type: Optional[str] = None):
```

#### `get_phase_info()`
Generates comprehensive phase information with complexity estimation:

```python
def get_phase_info(phase_name: str, phase_progress: int = 0) -> Dict:
```

### Progress Estimator

The `MappingProgressEstimator` class provides:

#### Key Methods:
- `analyze_mapping_complexity()`: Analyzes mapping configuration
- `estimate_phase_durations()`: Estimates duration for each phase
- `calculate_progress_weights()`: Calculates progress weights
- `get_enhanced_progress_info()`: Provides comprehensive progress info

#### Base Duration Estimates:
```python
BASE_DURATIONS = {
    ExecutionStrategy.MAPPING_DRIVEN: {
        "initialization": 2.0,
        "file_download": 5.0,
        "mapping_validation": 8.0,
        "file_validation": 15.0,
        "strategy_selection": 1.0,
        "data_import": 30.0,
        "finalization": 3.0
    },
    # ... other strategies
}
```

### Execution Strategies

The system supports multiple execution strategies:

- **MAPPING_DRIVEN**: Uses mapping configuration for complex imports
- **ENTITY_CENTRIC**: Entity-focused imports with table services
- **STANDARD**: Basic import workflow
- **DIRECTORY**: Directory-based imports
- **STRUCTURED**: Structured error handling workflow

## Usage Examples

### Basic Usage

```python
# Initialize phase tracking
phase_info = get_phase_info("data_import", 45)
update_cache_with_phase_info("processing", "Importing data...", 60, phase_info)
```

### Enhanced Usage with Complexity Estimation

```python
# Get enhanced progress information
enhanced_info = progress_estimator.get_enhanced_progress_info(
    current_phase="data_import",
    phase_progress=45,
    strategy=ExecutionStrategy.MAPPING_DRIVEN,
    mapping_config=execution_config.dict()
)

# Use enhanced progress
phase_info = get_phase_info("data_import", 45)
phase_info.update(enhanced_info)
```

### Template Usage

```html
<!-- Phase information display -->
{% if task_info.phase_info %}
    <div class="text-xs text-base-content/70 mt-1">
        Phase {{ task_info.phase_info.current_phase_index|add:1 }}/{{ task_info.phase_info.total_phases }}: 
        {{ task_info.phase_info.phase_description }}
    </div>
{% endif %}

<!-- Phase progress bar -->
{% if task_info.phase_info.phase_progress %}
    <progress class="progress progress-secondary w-full" 
              value="{{ task_info.phase_info.phase_progress }}" 
              max="100"></progress>
{% endif %}
```

## Backward Compatibility

The enhanced system maintains full backward compatibility:

- Legacy `update_cache()` function still works
- Existing templates continue to function
- New features are additive and optional
- No breaking changes to existing APIs

## Error Handling Integration

The system integrates with the structured error handling pipeline:

- Phase-specific error context
- Error tracking with phase information
- Enhanced error reporting with progress state
- Structured error persistence with phase details

## Performance Considerations

### Optimizations:
- Lazy loading of complexity analysis
- Cached progress calculations
- Minimal overhead for basic operations
- Efficient phase tracking algorithms

### Scalability:
- Handles large mapping configurations
- Efficient for directory imports with many files
- Optimized progress weight calculations
- Minimal memory footprint

## Testing

### Unit Tests:
- Phase tracking accuracy
- Progress estimation correctness
- Complexity analysis validation
- Cache payload structure

### Integration Tests:
- End-to-end import workflows
- Template rendering with phase info
- Error handling with phases
- Backward compatibility verification

## Future Enhancements

### Planned Features:
- Real-time progress streaming
- Historical progress analysis
- Adaptive complexity learning
- User-specific progress preferences

### Potential Improvements:
- Machine learning-based estimates
- File size-based adjustments
- Network speed considerations
- User feedback integration

## Configuration

### Environment Variables:
- `ARKUMU_PROGRESS_ESTIMATION_ENABLED`: Enable/disable complexity estimation
- `ARKUMU_PROGRESS_CACHE_TIMEOUT`: Cache timeout for progress data
- `ARKUMU_PROGRESS_LOGGING_LEVEL`: Logging level for progress tracking

### Settings:
```python
# In settings.py
ARKUMU_PROGRESS_SETTINGS = {
    'ENABLE_COMPLEXITY_ESTIMATION': True,
    'CACHE_TIMEOUT': 3600,
    'LOG_PHASE_TRANSITIONS': True,
    'ENHANCED_TEMPLATES': True
}
```

## Troubleshooting

### Common Issues:
- **Phase not updating**: Check cache key validity
- **Progress estimation errors**: Verify mapping config format
- **Template not showing phases**: Ensure phase_info is in context
- **Backward compatibility issues**: Verify legacy function calls

### Debug Information:
- Enable debug logging for progress tracking
- Check cache contents for phase information
- Verify mapping complexity analysis
- Monitor progress weight calculations

## Conclusion

The enhanced progress tracking system provides a comprehensive, mapping-aware solution for import progress monitoring. It maintains backward compatibility while offering significant improvements in user experience and progress accuracy.