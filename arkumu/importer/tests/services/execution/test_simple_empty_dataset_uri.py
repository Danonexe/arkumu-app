"""
Simple test to verify empty datasets create URI resources during import.
This validates the fix for the issue where empty datasets were being skipped
without creating their dataset URI resources.
"""
import pytest
import logging
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig, DatasetConfig, ColumnConfig, ProcessingStrategy, ColumnType
)
from arkumu.metadata.models import Resource

logger = logging.getLogger(__name__)


@pytest.fixture
def simple_mapping_config():
    """Create a simple test mapping configuration"""
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="simple_test_mapping",
        organization="TEST_ORG",
        version="2.0",
        processing_strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC,
        datasets=[
            DatasetConfig(
                dataset_name="customers",
                columns=[
                    ColumnConfig(
                        column_name="customer_id",
                        dataset_name="customers",
                        column_type=ColumnType.ANCHOR,
                        datatype="entity",
                        arkumu_type="customer_id",
                        is_anchor=True
                    )
                ]
            ),
            DatasetConfig(
                dataset_name="orders",
                columns=[
                    ColumnConfig(
                        column_name="order_id",
                        dataset_name="orders",
                        column_type=ColumnType.ANCHOR,
                        datatype="entity",
                        arkumu_type="order_id",
                        is_anchor=True
                    )
                ]
            )
        ],
        fk_relationships=[]  # No FK relationships to avoid complexity
    )


@pytest.fixture
def simple_csv_data():
    """Create simple test CSV data with empty datasets"""
    return {
        # Empty dataset - should still create URI resource
        "customers": {
            "headers": ["customer_id"],
            "rows": []  # Empty!
        },
        # Dataset with data
        "orders": {
            "headers": ["order_id"],
            "rows": [
                {"order_id": "ORD001"},
                {"order_id": "ORD002"}
            ]
        }
    }


@pytest.mark.django_db(transaction=True)
def test_empty_dataset_creates_uri_resource(simple_mapping_config, simple_csv_data):
    """Test that empty datasets create their URI resources during streaming entity-centric processing"""
    logger.info("=== TESTING SIMPLE EMPTY DATASET URI CREATION ===")
    
    # Initialize processor with unique test URI
    statistics = ExecutionStatistics()
    processor = MappingAwareProcessor(
        institution="TEST_SIMPLE",
        base_uri="http://test-simple.arkumu.org/data",
        statistics=statistics
    )
    
    # Process with streaming entity-centric strategy
    metrics = processor.process_with_execution_config(
        execution_config=simple_mapping_config,
        csv_sources=simple_csv_data,
        strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
    )
    
    # Verify processing completed
    assert metrics.rows_processed == 2, "Should process 2 rows from orders dataset"
    
    # Check that URI resources were created for BOTH datasets
    logger.info("Checking dataset URI resources...")
    
    # Debug: Check all dataset resources that were created
    all_dataset_resources = Resource.objects.filter(uri__contains="/datasets/")
    logger.info(f"All dataset resources found: {[r.uri for r in all_dataset_resources]}")
    
    # Check customers dataset (empty) - use correct URI format
    customers_uri = "http://test-simple.arkumu.org/data/test-simple/datasets/customers"
    customers_resource = Resource.objects.filter(uri=customers_uri)
    
    logger.info(f"Customers dataset (empty): URI resource exists = {customers_resource.exists()}")
    
    assert customers_resource.exists(), \
        f"Empty dataset URI resource not created for customers (expected: {customers_uri})"
    
    # Check orders dataset (has data)
    orders_uri = "http://test-simple.arkumu.org/data/test-simple/datasets/orders"
    orders_resource = Resource.objects.filter(uri=orders_uri)
    
    logger.info(f"Orders dataset (data): URI resource exists = {orders_resource.exists()}")
    assert orders_resource.exists(), \
        f"Dataset URI resource not created for orders (expected: {orders_uri})"
    
    # Verify resource properties
    customers_res = customers_resource.first()
    assert customers_res.name == "customers"
    assert customers_res.resource_type == "IRI"
    
    orders_res = orders_resource.first()
    assert orders_res.name == "orders" 
    assert orders_res.resource_type == "IRI"
    
    # Verify statistics
    logger.info(f"Processing metrics: rows_processed={metrics.rows_processed}, resources_created={metrics.resources_created}")
    assert metrics.rows_processed == 2, "Should process 2 rows from orders dataset"
    assert metrics.resources_created == 4, "Should create 4 resources (2 datasets + 2 entities)"
    
    logger.info("=== SIMPLE EMPTY DATASET URI CREATION TEST PASSED ===")


@pytest.mark.django_db(transaction=True) 
def test_all_empty_datasets_create_uri_resources(simple_mapping_config):
    """Test that completely empty import still creates dataset URI resources"""
    logger.info("=== TESTING ALL EMPTY DATASETS URI CREATION ===")
    
    # CSV data with all empty datasets
    all_empty_csv = {
        "customers": {"headers": ["customer_id"], "rows": []},
        "orders": {"headers": ["order_id"], "rows": []}
    }
    
    # Initialize processor
    statistics = ExecutionStatistics()
    processor = MappingAwareProcessor(
        institution="TEST_ALL_EMPTY",
        base_uri="http://test-all-empty.arkumu.org/data", 
        statistics=statistics
    )
    
    # Process
    metrics = processor.process_with_execution_config(
        execution_config=simple_mapping_config,
        csv_sources=all_empty_csv,
        strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
    )
    
    # Should process 0 rows but still create dataset resources
    assert metrics.rows_processed == 0, "Should process 0 rows (all empty)"
    assert metrics.datasets_skipped == 2, "Should skip both empty datasets"
    
    # But both dataset URI resources should exist
    customers_uri = "http://test-all-empty.arkumu.org/data/datasets/customers"
    orders_uri = "http://test-all-empty.arkumu.org/data/datasets/orders"
    
    assert Resource.objects.filter(uri=customers_uri).exists(), "Customers dataset URI should exist"
    assert Resource.objects.filter(uri=orders_uri).exists(), "Orders dataset URI should exist"
    
    logger.info("=== ALL EMPTY DATASETS URI CREATION TEST PASSED ===")