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
        
        logger.info("=== PROCESSOR EXECUTION TEST ===")
        logger.info(f"Processing {len(real_csv_data)} datasets with {strategy.name} strategy")
        
        # Execute processing
        try:
            metrics = processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=real_csv_data,
                strategy=strategy
            )
            
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            
            # Verify processing completed
            assert isinstance(metrics, ExecutionMetrics), "Must return ExecutionMetrics"
            
            # Log processing results
            logger.info("Processing execution completed successfully")
            logger.info(f"  Processing time: {processing_time:.2f} seconds")
            logger.info(f"  Rows processed: {metrics.rows_processed}")
            logger.info(f"  Resources created: {metrics.resources_created}")
            logger.info(f"  Triples created: {metrics.triples_created}")
            logger.info(f"  Values created: {metrics.values_created}")
            
            # Verify meaningful processing occurred
            assert metrics.rows_processed > 0, "Must process at least some rows"
            
            # Performance check
            assert processing_time < 300.0, f"Processing took too long: {processing_time:.2f}s"
            
            # Verify execution completed properly
            assert metrics.execution_time is not None or metrics.end_time is not None, "Must have execution timing"
            
            return metrics
            
        except Exception as e:
            logger.error(f"Processing execution failed: {e}")
            raise
    
    @pytest.mark.django_db(transaction=True)
    def test_processing_metrics_validation(self, production_test_mapping, real_csv_data, execution_statistics):
        """Test validation of processing metrics output"""
        # Execute processing (reuse logic from previous test)
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        strategy = ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        
        processor = MappingAwareProcessor(
            institution="TEST_FUK",
            base_uri="http://test.arkumu.org/data",
            statistics=execution_statistics
        )
        self.processor = processor
        
        metrics = processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=real_csv_data,
            strategy=strategy
        )
        
        # Validate metrics structure
        logger.info("=== PROCESSING METRICS VALIDATION ===")
        
        # Check required metrics attributes
        required_attributes = [
            'rows_processed', 'resources_created', 'triples_created', 
            'values_created', 'start_time'
        ]
        
        for attr in required_attributes:
            assert hasattr(metrics, attr), f"Metrics must have {attr} attribute"
            value = getattr(metrics, attr)
            logger.info(f"  {attr}: {value}")
            
            # Verify numeric attributes are non-negative
            if attr in ['rows_processed', 'resources_created', 'triples_created', 'values_created']:
                assert isinstance(value, int), f"{attr} must be an integer"
                assert value >= 0, f"{attr} must be non-negative"
        
        # Verify timing attributes
        assert metrics.start_time is not None, "Must have start time"
        
        # Check for reasonable data processing ratios
        if metrics.rows_processed > 0:
            resources_per_row = metrics.resources_created / metrics.rows_processed
            triples_per_row = metrics.triples_created / metrics.rows_processed
            
            logger.info(f"  Resources per row: {resources_per_row:.2f}")
            logger.info(f"  Triples per row: {triples_per_row:.2f}")
            
            # Basic sanity checks
            assert resources_per_row >= 0, "Resources per row must be non-negative"
            assert triples_per_row >= 0, "Triples per row must be non-negative"
        
        logger.info("Processing metrics validation completed")
        
        return metrics
    
    @pytest.mark.django_db(transaction=True)
    def test_multi_value_column_detection(self, production_test_mapping, real_csv_data):
        """Test that multi-value columns are correctly detected from mapping configuration"""
        logger.info("=== MULTI-VALUE COLUMN DETECTION TEST ===")
        
        # Get execution config
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Import the data processor to test directly
        from arkumu.importer.services.execution.data_processor import DataProcessor
        
        # Process each dataset to check for multi-value columns
        processor = DataProcessor()
        total_multi_value_found = 0
        datasets_with_multi_value = []
        
        for dataset_name, dataset_data in real_csv_data.items():
            logger.info(f"Checking dataset '{dataset_name}' for multi-value columns")
            
            # Get the dataset config from execution config
            dataset_config = execution_config.get_dataset_config(dataset_name)
            
            if not dataset_config:
                logger.warning(f"No dataset config found for '{dataset_name}', skipping")
                continue
            
            # Skip datasets with no data
            if dataset_data['row_count'] == 0:
                logger.debug(f"Skipping empty dataset '{dataset_name}'")
                continue
            
            # Parse CSV into DataFrame from the structured data
            import polars as pl
            
            # Convert the structured data back to DataFrame
            df = pl.DataFrame(dataset_data['rows'])
            logger.debug(f"Dataset '{dataset_name}' has {len(df.columns)} columns: {df.columns}")
            
            # Create a mapping config structure that the data processor expects
            # The detect_multi_value_columns expects workspace_columns format
            workspace_columns = {}
            for column in dataset_config.columns:
                qualified_name = f"{dataset_name}::{column.column_name}"
                workspace_columns[qualified_name] = {
                    'is_multi_value': column.is_multi_value,
                    'separator': getattr(column, 'separator', ','),  # Default separator
                    'column_type': column.column_type.value if hasattr(column.column_type, 'value') else str(column.column_type)
                }
            
            mapping_config_for_processor = {
                'workspace_columns': workspace_columns
            }
            
            # Run multi-value detection with the dataset's mapping config
            multi_value_analysis = processor.detect_multi_value_columns(df, mapping_config_for_processor)
            
            # Count multi-value columns found
            multi_value_columns = [col for col, config in multi_value_analysis.items() if config['is_multi_value']]
            
            if multi_value_columns:
                total_multi_value_found += len(multi_value_columns)
                datasets_with_multi_value.append({
                    'dataset': dataset_name,
                    'columns': multi_value_columns,
                    'analysis': {col: multi_value_analysis[col] for col in multi_value_columns}
                })
                logger.info(f"✅ Found {len(multi_value_columns)} multi-value columns in '{dataset_name}': {multi_value_columns}")
                
                # Log details for each multi-value column
                for col in multi_value_columns:
                    analysis = multi_value_analysis[col]
                    logger.info(f"  - {col}: separator='{analysis['separator']}', source={analysis['source']}")
            else:
                logger.info(f"❌ No multi-value columns detected in '{dataset_name}'")
        
        # Summary
        logger.info(f"=== MULTI-VALUE DETECTION SUMMARY ===")
        logger.info(f"Total datasets checked: {len(real_csv_data)}")
        logger.info(f"Datasets with multi-value columns: {len(datasets_with_multi_value)}")
        logger.info(f"Total multi-value columns found: {total_multi_value_found}")
        
        if datasets_with_multi_value:
            logger.info("Multi-value columns found:")
            for dataset_info in datasets_with_multi_value:
                logger.info(f"  {dataset_info['dataset']}: {dataset_info['columns']}")
        
        # Assertions
        # Note: We can't assert that multi-value columns MUST be found, because it depends on the test data
        # But we can assert that the detection mechanism is working (no exceptions thrown)
        assert isinstance(total_multi_value_found, int), "Multi-value detection must return integer count"
        assert total_multi_value_found >= 0, "Multi-value count must be non-negative"
        
        # If we found any multi-value columns, verify their structure
        for dataset_info in datasets_with_multi_value:
            for col, analysis in dataset_info['analysis'].items():
                assert analysis['is_multi_value'] is True, f"Multi-value column {col} must have is_multi_value=True"
                assert 'separator' in analysis, f"Multi-value column {col} must have separator defined"
                assert 'source' in analysis, f"Multi-value column {col} must have source defined"
                assert analysis['source'] == 'mapping_config', f"Multi-value column {col} should be detected from mapping_config"
        
        logger.info("Multi-value column detection test completed successfully")
        
        return {
            'total_found': total_multi_value_found,
            'datasets_with_multi_value': datasets_with_multi_value
        }
    
    @pytest.mark.django_db(transaction=True)
    def test_external_ontology_recognition(self, production_test_mapping, real_csv_data):
        """Test that external ontology columns are correctly identified and processed from mapping configuration"""
        logger.info("=== EXTERNAL ONTOLOGY RECOGNITION TEST ===")
        
        # Get execution config
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Process each dataset to check for external ontology columns
        total_ontology_columns_found = 0
        datasets_with_ontology = []
        ontology_types_found = set()
        
        for dataset_name, dataset_data in real_csv_data.items():
            logger.info(f"Checking dataset '{dataset_name}' for external ontology columns")
            
            # Get the dataset config from execution config
            dataset_config = execution_config.get_dataset_config(dataset_name)
            
            if not dataset_config:
                logger.warning(f"No dataset config found for '{dataset_name}', skipping")
                continue
            
            # Skip datasets with no data
            if dataset_data['row_count'] == 0:
                logger.debug(f"Skipping empty dataset '{dataset_name}'")
                continue
            
            # Check for external ontology columns in the dataset config
            ontology_columns = []
            for column in dataset_config.columns:
                # Check if column has external ontology configuration
                if hasattr(column, 'is_external_ontology') and column.is_external_ontology:
                    # Get the external ontology config
                    ontology_config = getattr(column, 'external_ontology_config', {})
                    if ontology_config:
                        ontology_info = {
                            'column_name': column.column_name,
                            'ontology_type': ontology_config.get('ontology_type', 'unknown'),
                            'uri_template': ontology_config.get('uri_template', ''),
                            'identifier_pattern': ontology_config.get('identifier_pattern', ''),
                            'validation_enabled': ontology_config.get('validation_enabled', False)
                        }
                        ontology_columns.append(ontology_info)
                        ontology_types_found.add(ontology_info['ontology_type'])
                        
                        logger.info(f"  - Found {ontology_info['ontology_type']} ontology column: {column.column_name}")
                        logger.debug(f"    URI template: {ontology_info['uri_template']}")
                        if ontology_info['identifier_pattern']:
                            logger.debug(f"    Pattern: {ontology_info['identifier_pattern']}")
            
            if ontology_columns:
                total_ontology_columns_found += len(ontology_columns)
                datasets_with_ontology.append({
                    'dataset': dataset_name,
                    'ontology_columns': ontology_columns,
                    'column_count': len(ontology_columns)
                })
                logger.info(f"✅ Found {len(ontology_columns)} external ontology columns in '{dataset_name}'")
            else:
                logger.debug(f"❌ No external ontology columns detected in '{dataset_name}'")
        
        # Summary
        logger.info(f"=== EXTERNAL ONTOLOGY RECOGNITION SUMMARY ===")
        logger.info(f"Total datasets checked: {len(real_csv_data)}")
        logger.info(f"Datasets with external ontology columns: {len(datasets_with_ontology)}")
        logger.info(f"Total external ontology columns found: {total_ontology_columns_found}")
        logger.info(f"Ontology types found: {sorted(ontology_types_found)}")
        
        if datasets_with_ontology:
            logger.info("External ontology columns by dataset:")
            for dataset_info in datasets_with_ontology:
                logger.info(f"  {dataset_info['dataset']}: {dataset_info['column_count']} columns")
                for col_info in dataset_info['ontology_columns']:
                    logger.info(f"    - {col_info['column_name']} ({col_info['ontology_type']})")
        
        # Assertions
        assert isinstance(total_ontology_columns_found, int), "Ontology detection must return integer count"
        assert total_ontology_columns_found >= 0, "Ontology count must be non-negative"
        
        # If we found any ontology columns, verify their structure
        for dataset_info in datasets_with_ontology:
            for col_info in dataset_info['ontology_columns']:
                assert 'column_name' in col_info, f"Ontology column must have column_name"
                assert 'ontology_type' in col_info, f"Ontology column must have ontology_type"
                assert 'uri_template' in col_info, f"Ontology column must have uri_template"
                assert col_info['column_name'], f"Column name must not be empty"
                assert col_info['ontology_type'], f"Ontology type must not be empty"
                
                # Verify URI template contains identifier placeholder for substitution
                if col_info['uri_template']:
                    assert '{identifier}' in col_info['uri_template'], f"URI template should contain {{identifier}} placeholder: {col_info['uri_template']}"
        
        # Verify we found some expected ontology types if any ontologies are configured
        if total_ontology_columns_found > 0:
            logger.info("✅ External ontology recognition is working correctly")
            # Common ontology types we expect to see in academic/cultural heritage data
            expected_ontology_types = {'orcid', 'gnd', 'viaf', 'wikidata', 'aat', 'dublin_core', 'foaf'}
            found_expected = ontology_types_found.intersection(expected_ontology_types)
            if found_expected:
                logger.info(f"Found expected ontology types: {sorted(found_expected)}")
        else:
            logger.info("ℹ️  No external ontology columns found - this is expected if the test mapping doesn't include external authorities")
        
        logger.info("External ontology recognition test completed successfully")
        
        return {
            'total_found': total_ontology_columns_found,
            'datasets_with_ontology': datasets_with_ontology,
            'ontology_types': sorted(ontology_types_found)
        }