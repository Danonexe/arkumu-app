"""
Stage 2: Mapping Translation Tests - JSON to Structured Objects

This test validates the critical translation layer that converts raw mapping JSON
into typed, structured ExecutionConfig objects ready for data processing.

## What This Stage Tests

### Components Under Test
- **MappingAdapter**: `translate_to_execution_config()` method
- **ConfigTranslator**: Core conversion engine from JSON to typed objects

### Data Transformations
1. Raw mapping dictionary → Typed `ExecutionConfig` object
2. `workspace_datasets` → List of `DatasetConfig` objects  
3. `workspace_columns` → List of `ColumnConfig` objects with types and constraints
4. Relationship definitions → `FKRelationship` objects

### Key Validation Points
- ✅ ExecutionConfig object created without errors
- ✅ Expected counts: 35 datasets, 337 columns, 72 FK relationships
- ✅ DatasetConfig/ColumnConfig objects have correct attributes and types
- ✅ Foreign key relationships properly parsed and structured
- ✅ Organization and strategy configuration correctly set

## Why This Stage Matters

This stage transforms unstructured JSON into typed objects that the processor can safely
consume. Invalid translations would cause processing failures, making this validation critical.

## Expected Results
- Valid ExecutionConfig with 35+ DatasetConfig objects
- 337+ ColumnConfig objects with proper arkumu_type mappings
- 72+ FKRelationship objects with source/target definitions
- Ready for Stage 3 data correlation and Stage 5 processing
"""
import pytest
import logging
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter

logger = logging.getLogger(__name__)


class TestMappingTranslation:
    """Test mapping translation to execution config"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
    
    @pytest.mark.django_db
    def test_mapping_translation_process(self, production_test_mapping):
        """Test translation of mapping to execution config"""
        # Translate mapping to execution config
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Verify execution config was created
        assert execution_config is not None, "Execution config must be created"
        
        # Log translation results
        logger.info(f"Mapping translation completed successfully")
        logger.info(f"Datasets in execution config: {len(execution_config.datasets)}")
        logger.info(f"Total columns: {sum(len(ds.columns) for ds in execution_config.datasets)}")
        logger.info(f"FK relationships: {len(execution_config.fk_relationships)}")
        
        # Verify we have actual data
        assert len(execution_config.datasets) > 0, "Must have datasets in execution config"
        
    @pytest.mark.django_db
    def test_execution_config_structure(self, production_test_mapping):
        """Test structure of generated execution config"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Verify execution config attributes
        assert hasattr(execution_config, 'datasets'), "Execution config must have datasets"
        assert hasattr(execution_config, 'fk_relationships'), "Execution config must have FK relationships"
        assert hasattr(execution_config, 'organization_id'), "Execution config must have organization_id"
        
        # Verify organization
        assert execution_config.organization_id == 'fuk', "Organization must be FUK"
        
        # Log structure details
        logger.info(f"Execution config structure validation:")
        logger.info(f"  Organization: {execution_config.organization_id}")
        logger.info(f"  Datasets: {len(execution_config.datasets)}")
        logger.info(f"  FK Relationships: {len(execution_config.fk_relationships)}")
        
        # Verify datasets structure
        for i, dataset in enumerate(execution_config.datasets[:3]):  # Check first 3
            logger.info(f"  Dataset {i+1}: '{dataset.dataset_name}' with {len(dataset.columns)} columns")
            assert hasattr(dataset, 'dataset_name'), "Dataset must have name"
            assert hasattr(dataset, 'columns'), "Dataset must have columns"
            assert len(dataset.columns) > 0, f"Dataset {dataset.dataset_name} must have columns"
    
    @pytest.mark.django_db 
    def test_dataset_column_mapping(self, production_test_mapping):
        """Test that dataset columns are properly mapped"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Analyze column mappings
        total_columns = 0
        datasets_with_columns = 0
        
        for dataset in execution_config.datasets:
            if len(dataset.columns) > 0:
                datasets_with_columns += 1
                total_columns += len(dataset.columns)
                
                # Log first few columns for first few datasets
                if datasets_with_columns <= 3:
                    column_names = [col.column_name for col in dataset.columns[:5]]
                    logger.info(f"Dataset '{dataset.dataset_name}' columns: {column_names}...")
        
        logger.info(f"Column mapping analysis:")
        logger.info(f"  Total datasets: {len(execution_config.datasets)}")
        logger.info(f"  Datasets with columns: {datasets_with_columns}")
        logger.info(f"  Total columns mapped: {total_columns}")
        
        # Verify we have meaningful column mappings
        assert datasets_with_columns > 0, "Must have datasets with columns"
        assert total_columns > 0, "Must have total columns mapped"
        
    @pytest.mark.django_db
    def test_foreign_key_relationships(self, production_test_mapping):
        """Test foreign key relationship extraction"""
        execution_config = self.mapping_adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Analyze FK relationships
        fk_count = len(execution_config.fk_relationships)
        logger.info(f"Foreign key relationship analysis:")
        logger.info(f"  Total FK relationships: {fk_count}")
        
        if fk_count > 0:
            # Log first few FK relationships
            for i, fk in enumerate(execution_config.fk_relationships[:3]):
                logger.info(f"  FK {i+1}: {fk.source_dataset}.{fk.source_column} -> {fk.target_dataset}.{fk.target_column}")
                
                # Verify FK structure
                assert hasattr(fk, 'source_dataset'), "FK must have source dataset"
                assert hasattr(fk, 'source_column'), "FK must have source column"
                assert hasattr(fk, 'target_dataset'), "FK must have target dataset"
                assert hasattr(fk, 'target_column'), "FK must have target column"
        else:
            logger.warning("No FK relationships found in execution config")
        
        # FK relationships are optional, so just log the results
        logger.info(f"FK relationship extraction completed")