/**
 * Execution Preview Utilities
 * 
 * Utility functions for testing and debugging the execution preview functionality
 */

// Mock data for testing
const MOCK_ANALYSIS_DATA = {
    success: true,
    mapping_info: {
        id: "test_mapping_123",
        name: "Test Mapping",
        datasets: [
            { name: "users", columns: 15 },
            { name: "products", columns: 20 },
            { name: "orders", columns: 12 }
        ],
        total_columns: 47,
        fk_relationships: 3,
        external_ontologies: 1,
        version: "1.0.0"
    },
    file_analysis: {
        total_files: 3,
        files_by_dataset: {
            "users": [{ file_path: "metadata/users.csv", file_name: "users.csv" }],
            "products": [{ file_path: "metadata/products.csv", file_name: "products.csv" }],
            "orders": [{ file_path: "metadata/orders.csv", file_name: "orders.csv" }]
        },
        unique_datasets: ["users", "products", "orders"]
    },
    dataset_matching: {
        match_percentage: 100,
        matched_datasets: [
            { dataset_name: "users", files: ["users.csv"] },
            { dataset_name: "products", files: ["products.csv"] },
            { dataset_name: "orders", files: ["orders.csv"] }
        ],
        missing_datasets: [],
        extra_files: []
    },
    complexity_analysis: {
        complexity_level: "medium",
        complexity_factors: ["Multiple datasets", "Foreign key relationships"],
        dataset_count: 3
    },
    execution_strategy: {
        recommended_strategy: "parallel",
        strategy_reason: "Multiple independent datasets can be processed simultaneously",
        estimated_duration: "3-5 minutes",
        estimated_memory: "Medium",
        should_change_strategy: false
    },
    processing_phases: [
        {
            name: "Validation Phase",
            description: "Validate file formats and mapping compatibility",
            estimated_duration: "30 seconds",
            datasets: ["users", "products", "orders"]
        },
        {
            name: "Data Processing Phase",
            description: "Process data according to mapping rules",
            estimated_duration: "2-3 minutes",
            datasets: ["users", "products", "orders"]
        },
        {
            name: "Relationship Building Phase",
            description: "Establish foreign key relationships",
            estimated_duration: "1 minute",
            datasets: ["users", "products", "orders"]
        },
        {
            name: "Finalization Phase",
            description: "Index data and complete import",
            estimated_duration: "30 seconds",
            datasets: ["users", "products", "orders"]
        }
    ],
    recommendations: [
        { type: "info", message: "Consider processing during off-peak hours for better performance" },
        { type: "warning", message: "Large dataset detected - ensure adequate memory is available" }
    ],
    readiness_status: {
        status: "ready",
        status_message: "All checks passed - ready to execute",
        issues: [],
        warnings: ["Large dataset may require extended processing time"]
    }
};

// Mock data for failed analysis
const MOCK_FAILED_ANALYSIS = {
    success: false,
    error: "Mapping validation failed",
    dataset_matching: {
        match_percentage: 60,
        matched_datasets: [
            { dataset_name: "users", files: ["users.csv"] }
        ],
        missing_datasets: ["products", "orders"],
        extra_files: ["categories.csv"]
    },
    readiness_status: {
        status: "not_ready",
        status_message: "Missing required datasets",
        issues: ["Missing products.csv", "Missing orders.csv"],
        warnings: ["Extra file categories.csv will be ignored"]
    }
};

/**
 * Test the execution preview with mock data
 */
function testExecutionPreview() {
    console.log("Testing execution preview with mock data...");
    
    // Test successful analysis
    if (typeof updateExecutionPreview === 'function') {
        updateExecutionPreview(MOCK_ANALYSIS_DATA);
        console.log("✓ Successful analysis test completed");
    } else {
        console.error("✗ updateExecutionPreview function not found");
    }
    
    // Test failed analysis after 3 seconds
    setTimeout(() => {
        if (typeof updateExecutionPreview === 'function') {
            updateExecutionPreview(MOCK_FAILED_ANALYSIS);
            console.log("✓ Failed analysis test completed");
        }
    }, 3000);
}

/**
 * Test all interactive features
 */
function testInteractiveFeatures() {
    console.log("Testing interactive features...");
    
    // Test toggle functions
    const functions = [
        'toggleExecutionDetails',
        'refreshExecutionPreview',
        'toggleAutoRefresh',
        'exportExecutionPreview'
    ];
    
    functions.forEach(funcName => {
        if (typeof window[funcName] === 'function') {
            console.log(`✓ ${funcName} function is available`);
        } else {
            console.error(`✗ ${funcName} function not found`);
        }
    });
    
    // Test DOM elements
    const elements = [
        'dataset-preview-content',
        'timeline-preview-content',
        'strategy-preview-content',
        'issues-preview-content',
        'file-matching-preview-content',
        'execution-details-content'
    ];
    
    elements.forEach(elementId => {
        const element = document.getElementById(elementId);
        if (element) {
            console.log(`✓ Element ${elementId} found`);
        } else {
            console.error(`✗ Element ${elementId} not found`);
        }
    });
}

/**
 * Simulate file selection changes
 */
function simulateFileSelectionChange() {
    console.log("Simulating file selection change...");
    
    // Trigger custom event
    const event = new CustomEvent('fileSelectionChanged', {
        detail: { files: ['file1.csv', 'file2.csv', 'file3.csv'] }
    });
    
    document.body.dispatchEvent(event);
    console.log("✓ File selection change event triggered");
}

/**
 * Simulate mapping selection
 */
function simulateMappingSelection() {
    console.log("Simulating mapping selection...");
    
    // Trigger custom event
    const event = new CustomEvent('mappingSelected', {
        detail: { mapping_id: 'test_mapping_123' }
    });
    
    document.body.dispatchEvent(event);
    console.log("✓ Mapping selection event triggered");
}

/**
 * Performance test for the preview updates
 */
function performanceTest() {
    console.log("Running performance test...");
    
    if (typeof updateExecutionPreview !== 'function') {
        console.error("✗ updateExecutionPreview function not available");
        return;
    }
    
    const startTime = performance.now();
    
    // Run multiple updates
    for (let i = 0; i < 10; i++) {
        updateExecutionPreview(MOCK_ANALYSIS_DATA);
    }
    
    const endTime = performance.now();
    const duration = endTime - startTime;
    
    console.log(`✓ Performance test completed: ${duration.toFixed(2)}ms for 10 updates`);
    console.log(`✓ Average time per update: ${(duration / 10).toFixed(2)}ms`);
}

/**
 * Test error handling
 */
function testErrorHandling() {
    console.log("Testing error handling...");
    
    // Test with invalid data
    const invalidData = {
        success: true,
        // Missing required fields
    };
    
    try {
        if (typeof updateExecutionPreview === 'function') {
            updateExecutionPreview(invalidData);
            console.log("✓ Error handling test completed");
        }
    } catch (error) {
        console.log(`✓ Error properly caught: ${error.message}`);
    }
    
    // Test with null data
    try {
        if (typeof updateExecutionPreview === 'function') {
            updateExecutionPreview(null);
            console.log("✓ Null data test completed");
        }
    } catch (error) {
        console.log(`✓ Null data error properly caught: ${error.message}`);
    }
}

/**
 * Run all tests
 */
function runAllTests() {
    console.log("🧪 Running all execution preview tests...");
    
    testInteractiveFeatures();
    setTimeout(testExecutionPreview, 500);
    setTimeout(performanceTest, 1000);
    setTimeout(testErrorHandling, 1500);
    setTimeout(simulateFileSelectionChange, 2000);
    setTimeout(simulateMappingSelection, 2500);
    
    console.log("✅ All tests scheduled");
}

/**
 * Debug information
 */
function debugInfo() {
    console.log("🔍 Execution Preview Debug Information:");
    console.log("- User Agent:", navigator.userAgent);
    console.log("- Screen Resolution:", screen.width + "x" + screen.height);
    console.log("- Viewport Size:", window.innerWidth + "x" + window.innerHeight);
    console.log("- Available Functions:", Object.keys(window).filter(key => key.includes('execution') || key.includes('preview')));
    console.log("- DOM Elements:", document.querySelectorAll('[id*="preview"]').length, "preview elements found");
    console.log("- Event Listeners:", getEventListeners ? Object.keys(getEventListeners(document.body) || {}) : "getEventListeners not available");
}

// Export functions for use in browser console
window.executionPreviewUtils = {
    testExecutionPreview,
    testInteractiveFeatures,
    simulateFileSelectionChange,
    simulateMappingSelection,
    performanceTest,
    testErrorHandling,
    runAllTests,
    debugInfo,
    MOCK_ANALYSIS_DATA,
    MOCK_FAILED_ANALYSIS
};

// Auto-run debug info when loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', debugInfo);
} else {
    debugInfo();
}

console.log("🚀 Execution Preview Utilities loaded. Use executionPreviewUtils.runAllTests() to run all tests.");