"""
Test specifically for the Sammlung dataset which has 0 rows in production.
This validates that empty datasets from real production data create their URI resources.
"""
import pytest
import logging
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy
from arkumu.metadata.models import Resource

logger = logging.getLogger(__name__)


@pytest.mark.django_db(transaction=True)
def test_sammlung_empty_dataset_creates_uri(production_test_mapping, real_csv_data, execution_statistics):
    """Test that the Sammlung dataset (which has 0 rows) creates its URI resource"""
    logger.info("=== TESTING SAMMLUNG EMPTY DATASET URI CREATION ===")
    
    # Check that Sammlung dataset exists and is empty
    assert 'Sammlung' in real_csv_data, "Sammlung dataset should be in real CSV data"
    
    sammlung_data = real_csv_data['Sammlung']
    sammlung_row_count = len(sammlung_data.get('rows', []))
    
    logger.info(f"Sammlung dataset row count: {sammlung_row_count}")
    assert sammlung_row_count == 0, f"Sammlung should have 0 rows, but has {sammlung_row_count}"
    
    logger.info("✅ Confirmed: Sammlung dataset has 0 rows - perfect test case for empty dataset fix")
    
    # Load mapping
    from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
    mapping_adapter = MappingAdapter()
    execution_config = mapping_adapter.translate_to_execution_config(production_test_mapping.id)
    
    # Check if Sammlung is in the mapping configuration
    sammlung_config = None
    for dataset_config in execution_config.datasets:
        if dataset_config.dataset_name.lower() == 'sammlung':
            sammlung_config = dataset_config
            break
    
    assert sammlung_config is not None, "Sammlung dataset should be in the mapping configuration"
    logger.info(f"✅ Sammlung dataset found in mapping with {len(sammlung_config.columns)} columns")
    
    # Create CSV data with just Sammlung (empty) to test the fix
    test_csv_data = {
        'Sammlung': sammlung_data
    }
    
    # Initialize processor
    processor = MappingAwareProcessor(
        institution="TEST_SAMMLUNG_FIX",
        base_uri="http://test-sammlung-fix.arkumu.org/data",
        statistics=execution_statistics
    )
    
    # Process with streaming entity-centric strategy
    logger.info("Processing Sammlung dataset with MappingAwareProcessor...")
    metrics = processor.process_with_execution_config(
        execution_config=execution_config,
        csv_sources=test_csv_data,
        strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
    )
    
    logger.info(f"Processing completed: {metrics.rows_processed} rows processed")
    assert metrics.rows_processed == 0, "Should process 0 rows for empty Sammlung dataset"
    
    # Check if Sammlung dataset URI resource was created
    sammlung_resources = Resource.objects.filter(
        uri__contains="test-sammlung-fix.arkumu.org"
    ).filter(
        uri__contains="/datasets/sammlung"
    )
    
    logger.info(f"Looking for Sammlung dataset URI resources...")
    logger.info(f"Found {sammlung_resources.count()} Sammlung dataset resources")
    
    if sammlung_resources.exists():
        sammlung_resource = sammlung_resources.first()
        logger.info(f"✅ SUCCESS: Sammlung dataset URI resource created!")
        logger.info(f"   URI: {sammlung_resource.uri}")
        logger.info(f"   Name: {sammlung_resource.name}")
        logger.info(f"   Type: {sammlung_resource.resource_type}")
        
        # Verify resource properties
        assert sammlung_resource.name.lower() == "sammlung"
        assert sammlung_resource.resource_type == "IRI"
        
        logger.info("✅ FIX IS WORKING: Empty datasets create URI resources!")
        
    else:
        # Debug: Show all dataset resources created
        all_dataset_resources = Resource.objects.filter(
            uri__contains="test-sammlung-fix.arkumu.org"
        ).filter(
            uri__contains="/datasets/"
        )
        logger.error(f"❌ FAILURE: Sammlung dataset URI resource NOT created")
        logger.error(f"All dataset resources created: {[r.uri for r in all_dataset_resources]}")
        
        # This should fail the test
        assert False, "Sammlung dataset URI resource was not created - fix is not working!"
    
    logger.info("=== SAMMLUNG EMPTY DATASET URI CREATION TEST PASSED ===")


@pytest.mark.django_db(transaction=True) 
def test_sammlung_with_other_empty_datasets(production_test_mapping, real_csv_data, execution_statistics):
    """Test Sammlung together with other empty datasets from production data"""
    logger.info("=== TESTING SAMMLUNG WITH OTHER EMPTY DATASETS ===")
    
    # Find all empty datasets in the real CSV data
    empty_datasets = {}
    populated_datasets = {}
    
    for dataset_name, data in real_csv_data.items():
        row_count = len(data.get('rows', []))
        if row_count == 0:
            empty_datasets[dataset_name] = data
        else:
            populated_datasets[dataset_name] = data
    
    logger.info(f"Found {len(empty_datasets)} empty datasets in production data")
    logger.info(f"Empty datasets: {list(empty_datasets.keys())}")
    logger.info(f"Found {len(populated_datasets)} populated datasets")
    
    # Ensure Sammlung is among the empty ones
    assert 'Sammlung' in empty_datasets, "Sammlung should be empty"
    
    # Process only the empty datasets
    from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
    mapping_adapter = MappingAdapter()
    execution_config = mapping_adapter.translate_to_execution_config(production_test_mapping.id)
    
    # Initialize processor
    processor = MappingAwareProcessor(
        institution="TEST_EMPTY_DATASETS",
        base_uri="http://test-empty-datasets.arkumu.org/data",
        statistics=execution_statistics
    )
    
    # Process with just the empty datasets
    logger.info(f"Processing {len(empty_datasets)} empty datasets...")
    metrics = processor.process_with_execution_config(
        execution_config=execution_config,
        csv_sources=empty_datasets,
        strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
    )
    
    logger.info(f"Processing completed: {metrics.rows_processed} rows processed")
    assert metrics.rows_processed == 0, "Should process 0 rows for all empty datasets"
    
    # Check that URI resources were created for ALL empty datasets
    uri_base = "test-empty-datasets.arkumu.org"
    
    for dataset_name in empty_datasets.keys():
        dataset_resources = Resource.objects.filter(
            uri__contains=uri_base
        ).filter(
            uri__contains=f"/datasets/{dataset_name.lower()}"
        )
        
        logger.info(f"Dataset '{dataset_name}': URI resource exists = {dataset_resources.exists()}")
        assert dataset_resources.exists(), \
            f"Empty dataset '{dataset_name}' should have created a URI resource"
    
    logger.info(f"✅ SUCCESS: All {len(empty_datasets)} empty datasets created URI resources!")
    logger.info("✅ FIX IS WORKING FOR MULTIPLE EMPTY DATASETS!")
    
    logger.info("=== EMPTY DATASETS TEST PASSED ===")