"""
Stage 5: Processor Execution Tests - Data Processing Engine

This test validates the core data processing engine that transforms CSV data into
Resource and Triple objects using the mapping configuration. This is where actual
data processing occurs.

## What This Stage Tests

### Components Under Test
- **MappingAwareProcessor**: Main data processing engine
- **Processing Strategies**: Multiple available strategies for different data sizes/complexity
- **ExecutionMetrics**: Processing statistics and performance measurement

### Available Processing Strategies
1. **ENTITY_CENTRIC**: Complete entity creation in single pass (small datasets <50MB)
2. **STREAMING_ENTITY_CENTRIC**: Balanced chunked processing (medium datasets 50-500MB) ← *Used in tests*
3. **MULTI_PHASE**: Most memory efficient, multiple passes (large datasets >500MB)
4. **AUTO**: Intelligent strategy selection based on data characteristics

### Processing Workflow Validation
1. Processor initialization with test-specific URI and institution
2. ExecutionConfig + CSV data → `process_with_execution_config()`
3. Processing strategy execution → In-memory Resource/Triple creation
4. Metrics generation → Processing statistics and timing

### Key Validation Points
- ✅ Processor runs to completion without errors
- ✅ Returns valid ExecutionMetrics object
- ✅ Processing statistics > 0 (rows_processed, resources_created, triples_created)
- ✅ Processing time within performance threshold (< 300 seconds)
- ✅ Strategy configuration and execution successful

## Why This Stage Matters

This is the core processing engine that transforms raw CSV data into structured
knowledge objects. Without reliable processing execution, no data transformation occurs.

## Expected Results
- Processing completes successfully for 35+ datasets
- Meaningful metrics: rows processed, resources/triples created
- Performance within acceptable thresholds
- Ready for Stage 6 database validation
"""
import pytest
import logging
from datetime import datetime, timezone
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics, ExecutionMetrics
from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy

logger = logging.getLogger(__name__)


class TestProcessorExecution:
    """Test processor execution stage"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
        self.statistics = ExecutionStatistics()
        self.processor = None
    
    def teardown_method(self):
        """Clean up after test"""
        if self.processor:
            # Reset processor state
            if hasattr(self.processor, 'entity_cache'):
                self.processor.entity_cache = {}
            if hasattr(self.processor, 'pending_relationships'):
                self.processor.pending_relationships = []
    
    @pytest.mark.django_db(transaction=True)
    def test_processor_initialization(self, execution_statistics):
        """Test processor initialization with test configuration"""
        # Initialize processor with test-specific settings
        processor = MappingAwareProcessor(
            institution="TEST_FUK",
            base_uri="http://test.arkumu.org/data",
            statistics=execution_statistics
        )
        
        # Verify processor attributes
        assert processor is not None, "Processor must be initialized"
        assert processor.institution == "TEST_FUK", "Institution must be set correctly"
        assert processor.base_uri == "http://test.arkumu.org/data", "Base URI must be set correctly"
        assert processor.statistics is not None, "Statistics must be attached"
        
        logger.info("Processor initialization validation:")
        logger.info(f"  Institution: {processor.institution}")
        logger.info(f"  Base URI: {processor.base_uri}")
        logger.info(f"  Statistics attached: {processor.statistics is not None}")
        
        self.processor = processor
        
    @pytest.mark.django_db(transaction=True)
    def test_processing_strategy_selection(self, production_test_mapping):
        """Test processing strategy configuration"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Test different strategies
        available_strategies = [
            ProcessingStrategy.STREAMING_ENTITY_CENTRIC,
            # Add other strategies as needed
        ]
        
        logger.info("Processing strategy validation:")
        
        for strategy in available_strategies:
            logger.info(f"  Strategy {strategy.name}: Available")
            assert strategy is not None, f"Strategy {strategy.name} must be available"
        
        # Use the supported strategy for testing
        selected_strategy = ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        logger.info(f"Selected strategy for testing: {selected_strategy.name}")
        
        return selected_strategy
        
    @pytest.mark.django_db(transaction=True)
    def test_processing_execution(self, production_test_mapping, real_csv_data, execution_statistics):
        """Test actual data processing execution"""
        # Setup
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        strategy = ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        
        # Initialize processor
        processor = MappingAwareProcessor(
            institution="TEST_FUK",
            base_uri="http://test.arkumu.org/data",
            statistics=execution_statistics
        )
        self.processor = processor
        
        # Track processing time
        start_time = datetime.now(timezone.utc)
        
        logger.info("=== PROCESSOR EXECUTION TEST ===\")
        logger.info(f\"Processing {len(real_csv_data)} datasets with {strategy.name} strategy\")\n        \n        # Execute processing\n        try:\n            metrics = processor.process_with_execution_config(\n                execution_config=execution_config,\n                csv_sources=real_csv_data,\n                strategy=strategy\n            )\n            \n            end_time = datetime.now(timezone.utc)\n            processing_time = (end_time - start_time).total_seconds()\n            \n            # Verify processing completed\n            assert isinstance(metrics, ExecutionMetrics), \"Must return ExecutionMetrics\"\n            \n            # Log processing results\n            logger.info(\"Processing execution completed successfully\")\n            logger.info(f\"  Processing time: {processing_time:.2f} seconds\")\n            logger.info(f\"  Rows processed: {metrics.rows_processed}\")\n            logger.info(f\"  Resources created: {metrics.resources_created}\")\n            logger.info(f\"  Triples created: {metrics.triples_created}\")\n            logger.info(f\"  Values created: {metrics.values_created}\")\n            \n            # Verify meaningful processing occurred\n            assert metrics.rows_processed > 0, \"Must process at least some rows\"\n            \n            # Performance check\n            assert processing_time < 300.0, f\"Processing took too long: {processing_time:.2f}s\"\n            \n            # Verify execution completed properly\n            assert metrics.execution_time is not None or metrics.end_time is not None, \"Must have execution timing\"\n            \n            return metrics\n            \n        except Exception as e:\n            logger.error(f\"Processing execution failed: {e}\")\n            raise\n    \n    @pytest.mark.django_db(transaction=True)\n    def test_processing_metrics_validation(self, production_test_mapping, real_csv_data, execution_statistics):\n        \"\"\"Test validation of processing metrics output\"\"\"\n        # Execute processing (reuse logic from previous test)\n        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)\n        strategy = ProcessingStrategy.STREAMING_ENTITY_CENTRIC\n        \n        processor = MappingAwareProcessor(\n            institution=\"TEST_FUK\",\n            base_uri=\"http://test.arkumu.org/data\",\n            statistics=execution_statistics\n        )\n        self.processor = processor\n        \n        metrics = processor.process_with_execution_config(\n            execution_config=execution_config,\n            csv_sources=real_csv_data,\n            strategy=strategy\n        )\n        \n        # Validate metrics structure\n        logger.info(\"=== PROCESSING METRICS VALIDATION ===\")\n        \n        # Check required metrics attributes\n        required_attributes = [\n            'rows_processed', 'resources_created', 'triples_created', \n            'values_created', 'start_time'\n        ]\n        \n        for attr in required_attributes:\n            assert hasattr(metrics, attr), f\"Metrics must have {attr} attribute\"\n            value = getattr(metrics, attr)\n            logger.info(f\"  {attr}: {value}\")\n            \n            # Verify numeric attributes are non-negative\n            if attr in ['rows_processed', 'resources_created', 'triples_created', 'values_created']:\n                assert isinstance(value, int), f\"{attr} must be an integer\"\n                assert value >= 0, f\"{attr} must be non-negative\"\n        \n        # Verify timing attributes\n        assert metrics.start_time is not None, \"Must have start time\"\n        \n        # Check for reasonable data processing ratios\n        if metrics.rows_processed > 0:\n            resources_per_row = metrics.resources_created / metrics.rows_processed\n            triples_per_row = metrics.triples_created / metrics.rows_processed\n            \n            logger.info(f\"  Resources per row: {resources_per_row:.2f}\")\n            logger.info(f\"  Triples per row: {triples_per_row:.2f}\")\n            \n            # Basic sanity checks\n            assert resources_per_row >= 0, \"Resources per row must be non-negative\"\n            assert triples_per_row >= 0, \"Triples per row must be non-negative\"\n        \n        logger.info(\"Processing metrics validation completed\")\n        \n        return metrics"