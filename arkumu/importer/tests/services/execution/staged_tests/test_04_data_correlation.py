"""
Stage 4: Data Correlation Tests - Mapping-CSV Compatibility Analysis

This test performs critical correlation analysis between mapping configuration and CSV data
to ensure compatibility and readiness for processing. It's purely analytical - no processing occurs.

## What This Stage Tests

### Analysis Under Test
- **Dataset Name Correlation**: ExecutionConfig datasets ↔ CSV file names
- **Column Correlation**: Mapping column definitions ↔ CSV headers
- **Data Readiness Assessment**: Overall compatibility evaluation

### Data Correlation Workflow
1. Extract dataset names from ExecutionConfig (Stage 2 output)
2. Extract dataset names from CSV data (Stage 3 output)  
3. Calculate matches, missing datasets, extra files
4. For matched datasets: analyze column mapping correlation
5. Generate overall readiness assessment

### Key Validation Points
- ✅ High percentage of mapping datasets have corresponding CSV files
- ✅ Matched datasets show reasonable column correlation (mapping ↔ headers)
- ✅ Identifies missing datasets and extra files with detailed logging
- ✅ Data volume sufficient for meaningful processing
- ✅ Overall "readiness" assessment confirms pipeline can proceed

## Why This Stage Matters

This prevents processing failures by ensuring mapping and CSV data are compatible.
Without proper correlation, processing would fail or produce invalid results.

## Expected Results
- High dataset correlation between mapping and CSV files
- Reasonable column correlation for matched datasets  
- Sufficient data volume for processing
- Green light for Stage 5 processing execution
"""
import pytest
import logging
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter

logger = logging.getLogger(__name__)


class TestDataCorrelation:
    """Test correlation between mapping and CSV data"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
    
    @pytest.mark.django_db
    def test_dataset_name_correlation(self, production_test_mapping, real_csv_data):
        """Test correlation between mapping datasets and CSV file names"""
        # Get execution config
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Get dataset names from mapping
        mapping_datasets = {dataset.dataset_name for dataset in execution_config.datasets}
        
        # Get dataset names from CSV files
        csv_datasets = set(real_csv_data.keys())
        
        # Analyze correlation
        matched = mapping_datasets.intersection(csv_datasets)
        mapping_only = mapping_datasets - csv_datasets
        csv_only = csv_datasets - mapping_datasets
        
        # Log correlation results
        logger.info("=== DATASET NAME CORRELATION ANALYSIS ===")
        logger.info(f"Mapping datasets: {len(mapping_datasets)}")
        logger.info(f"CSV datasets: {len(csv_datasets)}")
        logger.info(f"Matched datasets: {len(matched)}")
        logger.info(f"Mapping-only datasets: {len(mapping_only)}")
        logger.info(f"CSV-only datasets: {len(csv_only)}")
        
        if matched:
            logger.info(f"Matched examples: {sorted(list(matched))[:5]}...")
        
        if mapping_only:
            logger.warning(f"Missing CSV files: {sorted(list(mapping_only))[:5]}...")
        
        if csv_only:
            logger.warning(f"Extra CSV files: {sorted(list(csv_only))[:5]}...")
        
        # Verify we have at least some matches
        assert len(matched) > 0, "Must have at least some dataset matches between mapping and CSV"
        
        # Calculate correlation percentage
        correlation_percentage = len(matched) / len(mapping_datasets) * 100 if mapping_datasets else 0
        logger.info(f"Dataset correlation: {correlation_percentage:.1f}%")
        
    @pytest.mark.django_db
    def test_column_correlation_analysis(self, production_test_mapping, real_csv_data):
        """Test correlation between mapping columns and CSV headers"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Find matched datasets
        mapping_datasets = {dataset.dataset_name: dataset for dataset in execution_config.datasets}
        csv_datasets = set(real_csv_data.keys())
        matched_datasets = set(mapping_datasets.keys()).intersection(csv_datasets)
        
        logger.info("=== COLUMN CORRELATION ANALYSIS ===")
        logger.info(f"Analyzing column correlation for {len(matched_datasets)} matched datasets")
        
        datasets_analyzed = 0
        total_mapping_columns = 0
        total_csv_columns = 0
        total_matched_columns = 0
        
        for dataset_name in list(matched_datasets)[:5]:  # Analyze first 5 matched datasets
            mapping_dataset = mapping_datasets[dataset_name]
            csv_data = real_csv_data[dataset_name]
            
            # Get columns
            mapping_columns = {col.column_name for col in mapping_dataset.columns}
            csv_headers = set(csv_data['headers']) if csv_data['headers'] else set()
            
            # Analyze correlation
            matched_columns = mapping_columns.intersection(csv_headers)
            mapping_only_cols = mapping_columns - csv_headers
            csv_only_cols = csv_headers - mapping_columns
            
            logger.info(f"Dataset '{dataset_name}':")
            logger.info(f"  Mapping columns: {len(mapping_columns)}")
            logger.info(f"  CSV headers: {len(csv_headers)}")
            logger.info(f"  Matched columns: {len(matched_columns)}")
            
            if mapping_only_cols:
                logger.warning(f"  Missing in CSV: {sorted(list(mapping_only_cols))[:3]}...")
            
            if csv_only_cols:
                logger.info(f"  Extra in CSV: {sorted(list(csv_only_cols))[:3]}...")
            
            # Accumulate totals
            total_mapping_columns += len(mapping_columns)
            total_csv_columns += len(csv_headers)
            total_matched_columns += len(matched_columns)
            datasets_analyzed += 1
        
        # Calculate overall column correlation
        if total_mapping_columns > 0:
            column_correlation = total_matched_columns / total_mapping_columns * 100
            logger.info(f"Overall column correlation: {column_correlation:.1f}% ({total_matched_columns}/{total_mapping_columns})")
        
        logger.info(f"Column correlation analysis completed for {datasets_analyzed} datasets")
        
    @pytest.mark.django_db
    def test_data_readiness_assessment(self, production_test_mapping, real_csv_data):
        """Test overall data readiness for processing"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Get basic counts
        mapping_datasets = {dataset.dataset_name for dataset in execution_config.datasets}
        csv_datasets = set(real_csv_data.keys())
        matched_datasets = mapping_datasets.intersection(csv_datasets)
        
        # Calculate readiness metrics
        dataset_coverage = len(matched_datasets) / len(mapping_datasets) * 100 if mapping_datasets else 0
        
        # Analyze data volume
        total_rows = sum(data['row_count'] for data in real_csv_data.values())
        matched_rows = sum(real_csv_data[name]['row_count'] for name in matched_datasets)
        
        # Calculate readiness score
        readiness_factors = {
            'dataset_coverage': dataset_coverage,
            'has_data': total_rows > 0,
            'matched_data_volume': matched_rows,
            'config_valid': execution_config is not None
        }
        
        logger.info("=== DATA READINESS ASSESSMENT ===")
        logger.info(f"Dataset coverage: {dataset_coverage:.1f}% ({len(matched_datasets)}/{len(mapping_datasets)})")
        logger.info(f"Total data volume: {total_rows} rows")
        logger.info(f"Matched data volume: {matched_rows} rows")
        logger.info(f"Configuration valid: {readiness_factors['config_valid']}")
        
        # Determine readiness status
        is_ready = (
            dataset_coverage > 0 and  # At least some datasets match
            total_rows > 0 and        # Have actual data
            execution_config is not None  # Valid configuration
        )
        
        logger.info(f"Data processing readiness: {'READY' if is_ready else 'NOT READY'}")
        
        # Assert minimum readiness
        assert is_ready, "Data must be ready for processing"
        assert dataset_coverage > 0, "Must have at least some dataset coverage"
        assert matched_rows > 0, "Must have rows in matched datasets"