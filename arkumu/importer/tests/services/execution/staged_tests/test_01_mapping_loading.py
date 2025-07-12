"""
Stage 1: Mapping Loading Tests - Database Storage and Configuration Loading

This test validates the fundamental mapping storage and loading layer of the pipeline.
It focuses on ensuring that mapping configurations from S3 are correctly stored in the
database and can be reliably loaded for processing.

## What This Stage Tests

### Components Under Test
- **BucketService**: Loading mapping JSON from S3 (`fuk/metadata/fuk_mapping.json`)
- **Mapping Model**: Database storage of mapping configurations
- **MappingAdapter**: Loading mapping configurations from database

### Data Flow Validation
1. S3 mapping JSON → Database storage as Mapping object
2. Database retrieval → Raw mapping configuration dictionary
3. Metadata extraction → workspace_datasets and workspace_columns

### Key Validation Points
- ✅ Mapping object successfully created in test database
- ✅ mapping_config attribute contains expected dictionary from JSON
- ✅ MappingAdapter can load configuration and extract workspace components
- ✅ Database persistence maintains JSON structure integrity

## Why This Stage Matters

This is the foundation stage that validates the mapping storage layer works correctly
before any translation or processing occurs. Without reliable mapping storage and loading,
subsequent stages cannot function.

## Expected Results
- Mapping stored in test database with correct metadata
- Configuration loadable via MappingAdapter
- workspace_datasets and workspace_columns extractable
- Foundation ready for Stage 2 translation
"""
import pytest
import logging
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter

logger = logging.getLogger(__name__)


class TestMappingLoading:
    """Test mapping loading from database"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
    
    @pytest.mark.django_db
    def test_mapping_database_storage(self, production_test_mapping):
        """Test that mapping is correctly stored in test database"""
        # Verify mapping exists in database
        assert production_test_mapping.pk is not None, "Mapping must be saved in test database"
        assert production_test_mapping.name is not None, "Mapping must have a name"
        assert production_test_mapping.organization_id == 'fuk', "Mapping must belong to FUK organization"
        
        # Verify mapping config is stored
        assert production_test_mapping.mapping_config is not None, "Mapping config must be stored"
        assert isinstance(production_test_mapping.mapping_config, dict), "Mapping config must be a dictionary"
        
        # Log mapping details
        logger.info(f"Mapping loaded successfully: ID={production_test_mapping.id}, Name={production_test_mapping.name}")
        logger.info(f"Organization: {production_test_mapping.organization_id}")
        logger.info(f"Source datasets: {len(production_test_mapping.source_datasets)}")
        
    @pytest.mark.django_db 
    def test_mapping_config_loading(self, production_test_mapping):
        """Test loading mapping configuration from database"""
        # Load mapping config using adapter
        mapping_config = self.mapping_adapter.load_mapping_config(production_test_mapping.id)
        
        # Verify config structure
        assert mapping_config is not None, "Mapping config must be loaded"
        assert isinstance(mapping_config, dict), "Mapping config must be a dictionary"
        
        # Verify required fields exist
        required_fields = ['workspace_datasets', 'workspace_columns']
        for field in required_fields:
            assert field in mapping_config, f"Mapping config must contain '{field}'"
        
        # Log config details
        workspace_datasets = mapping_config.get('workspace_datasets', [])
        workspace_columns = mapping_config.get('workspace_columns', {})
        
        logger.info(f"Mapping config loaded successfully")
        logger.info(f"Workspace datasets: {len(workspace_datasets)}")
        logger.info(f"Workspace columns: {len(workspace_columns)} datasets configured")
        
        # Verify we have actual data
        assert len(workspace_datasets) > 0, "Must have workspace datasets"
        assert len(workspace_columns) > 0, "Must have workspace columns configuration"
        
    @pytest.mark.django_db
    def test_mapping_metadata_extraction(self, production_test_mapping):
        """Test extraction of mapping metadata"""
        mapping_config = self.mapping_adapter.load_mapping_config(production_test_mapping.id)
        
        # Extract metadata
        metadata = mapping_config.get('metadata', {})
        workspace_datasets = mapping_config.get('workspace_datasets', [])
        workspace_columns = mapping_config.get('workspace_columns', {})
        
        # Log metadata details
        logger.info(f"Mapping metadata extraction:")
        logger.info(f"  Metadata keys: {list(metadata.keys()) if isinstance(metadata, dict) else 'Not a dict'}")
        logger.info(f"  Workspace datasets count: {len(workspace_datasets)}")
        logger.info(f"  Configured dataset columns: {list(workspace_columns.keys())}")
        
        # Basic validation
        assert isinstance(workspace_datasets, list), "Workspace datasets must be a list"
        assert isinstance(workspace_columns, dict), "Workspace columns must be a dict"
        
        # Verify dataset/column alignment
        for dataset_name in workspace_datasets[:5]:  # Check first 5
            if dataset_name in workspace_columns:
                columns = workspace_columns[dataset_name]
                logger.info(f"  Dataset '{dataset_name}': {len(columns)} columns configured")
                assert isinstance(columns, dict), f"Columns for {dataset_name} must be a dict"