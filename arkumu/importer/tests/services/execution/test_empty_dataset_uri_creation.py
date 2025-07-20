"""
Test that empty datasets properly create their URI resources during import.

This test validates the fix for the issue where empty datasets were being skipped
without creating their dataset URI resources, breaking the blueprint structure.
"""
import pytest
import logging
from typing import Dict, Any
from io import StringIO

from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig, DatasetConfig, ColumnConfig, ProcessingStrategy, ColumnType, FKRelationship
)
from arkumu.metadata.models import Resource
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)


@pytest.fixture
def test_mapping_config():
    """Create a test mapping configuration with multiple datasets"""
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="test_mapping",
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
                    ),
                    ColumnConfig(
                        column_name="customer_name",
                        dataset_name="customers",
                        column_type=ColumnType.REGULAR,
                        datatype="text",
                        arkumu_type="customer_name"
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
                    ),
                    ColumnConfig(
                        column_name="customer_id",
                        dataset_name="orders",
                        column_type=ColumnType.FOREIGN_KEY,
                        datatype="entity",
                        arkumu_type="customer_id"
                    ),
                    ColumnConfig(
                        column_name="order_amount",
                        dataset_name="orders",
                        column_type=ColumnType.REGULAR,
                        datatype="decimal",
                        arkumu_type="order_amount"
                    )
                ]
            ),
            DatasetConfig(
                dataset_name="products",
                columns=[
                    ColumnConfig(
                        column_name="product_id",
                        dataset_name="products",
                        column_type=ColumnType.ANCHOR,
                        datatype="entity",
                        arkumu_type="product_id",
                        is_anchor=True
                    ),
                    ColumnConfig(
                        column_name="product_name",
                        dataset_name="products",
                        column_type=ColumnType.REGULAR,
                        datatype="text",
                        arkumu_type="product_name"
                    )
                ]
            )
        ],
        fk_relationships=[
            FKRelationship(
                source_column="customer_id",
                source_dataset="orders", 
                target_column="customer_id",
                target_dataset="customers",
                relationship_type="isPartOf"
            )
        ]
    )


@pytest.fixture
def test_csv_data():
    """Create test CSV data with some empty datasets"""
    return {
        # Empty dataset - should still create URI resource
        "customers": {
            "headers": ["customer_id", "customer_name"],
            "rows": []  # Empty!
        },
        # Dataset with data
        "orders": {
            "headers": ["order_id", "customer_id", "order_amount"],
            "rows": [
                {"order_id": "ORD001", "customer_id": "CUST001", "order_amount": "100.50"},
                {"order_id": "ORD002", "customer_id": "CUST002", "order_amount": "250.75"}
            ]
        },
        # Another empty dataset
        "products": {
            "headers": ["product_id", "product_name"],
            "rows": []  # Empty!
        }
    }


@pytest.fixture
def missing_dataset_csv_data():
    """Create test CSV data with completely missing datasets"""
    return {
        # Only orders dataset has data, others are missing entirely
        "orders": {
            "headers": ["order_id", "customer_id", "order_amount"],
            "rows": [
                {"order_id": "ORD001", "customer_id": "CUST001", "order_amount": "100.50"},
                {"order_id": "ORD002", "customer_id": "CUST002", "order_amount": "250.75"}
            ]
        }
        # Note: customers and products datasets are completely missing from CSV data
    }


class TestEmptyDatasetUriCreation:
    """Test that empty datasets properly create their URI resources"""
    
    @pytest.mark.django_db(transaction=True)
    def test_empty_datasets_create_uri_resources(self, test_mapping_config, test_csv_data):
        """Test that empty datasets still create their dataset URI resources"""
        logger.info("=== TESTING EMPTY DATASET URI CREATION ===")
        
        # Initialize processor
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_EMPTY_DS",
            base_uri="http://test-empty.arkumu.org/data",
            statistics=statistics
        )
        
        # Process with streaming entity-centric strategy
        metrics = processor.process_with_execution_config(
            execution_config=test_mapping_config,
            csv_sources=test_csv_data,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Verify processing completed
        assert metrics.rows_processed == 2, "Should process 2 rows from orders dataset"
        
        # Check that URI resources were created for ALL datasets
        logger.info("Checking dataset URI resources...")
        
        for dataset_name in ["customers", "orders", "products"]:
            dataset_uri = f"http://test-empty.arkumu.org/data/datasets/{dataset_name.lower()}"
            
            # Check if dataset resource exists
            dataset_resources = Resource.objects.filter(uri=dataset_uri)
            
            logger.info(f"Dataset '{dataset_name}': URI resource exists = {dataset_resources.exists()}")
            
            # Assert that the dataset URI resource was created
            assert dataset_resources.exists(), \
                f"Dataset URI resource not created for {dataset_name} (expected: {dataset_uri})"
            
            # Verify resource properties
            dataset_resource = dataset_resources.first()
            assert dataset_resource.name == dataset_name.lower()
            assert dataset_resource.resource_type == Resource.ResourceType.IRI
        
        # Verify statistics show correct counts
        assert metrics.datasets_processed == 1, "Should process only 1 dataset with data (orders)"
        assert metrics.datasets_skipped == 2, "Should skip 2 empty datasets (customers, products)"
        
        logger.info("=== EMPTY DATASET URI CREATION TEST PASSED ===")
    
    @pytest.mark.django_db(transaction=True)
    def test_missing_datasets_create_uri_resources(self, test_mapping_config, missing_dataset_csv_data):
        """Test that completely missing datasets still create their dataset URI resources"""
        logger.info("=== TESTING MISSING DATASET URI CREATION ===")
        
        # Initialize processor
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_MISSING_DS",
            base_uri="http://test-missing.arkumu.org/data",
            statistics=statistics
        )
        
        # Process with streaming entity-centric strategy
        metrics = processor.process_with_execution_config(
            execution_config=test_mapping_config,
            csv_sources=missing_dataset_csv_data,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Verify processing completed
        assert metrics.rows_processed == 2, "Should process 2 rows from orders dataset"
        
        # Check that URI resources were created for ALL datasets
        logger.info("Checking dataset URI resources for missing datasets...")
        
        for dataset_name in ["customers", "orders", "products"]:
            dataset_uri = f"http://test-missing.arkumu.org/data/datasets/{dataset_name.lower()}"
            
            # Check if dataset resource exists
            dataset_resources = Resource.objects.filter(uri=dataset_uri)
            
            is_in_csv = dataset_name in missing_dataset_csv_data
            logger.info(f"Dataset '{dataset_name}': in CSV = {is_in_csv}, URI resource exists = {dataset_resources.exists()}")
            
            # Assert that the dataset URI resource was created
            assert dataset_resources.exists(), \
                f"Dataset URI resource not created for {dataset_name} (expected: {dataset_uri})"
            
            # Verify resource properties
            dataset_resource = dataset_resources.first()
            assert dataset_resource.name == dataset_name.lower()
            assert dataset_resource.resource_type == Resource.ResourceType.IRI
        
        # Verify statistics show correct counts
        assert metrics.datasets_processed == 1, "Should process only 1 dataset (orders)"
        assert metrics.datasets_skipped == 2, "Should skip 2 missing datasets (customers, products)"
        
        logger.info("=== MISSING DATASET URI CREATION TEST PASSED ===")
    
    @pytest.mark.django_db(transaction=True)
    def test_mixed_empty_and_populated_datasets(self, test_mapping_config, test_csv_data):
        """Test processing with a mix of empty and populated datasets"""
        logger.info("=== TESTING MIXED EMPTY AND POPULATED DATASETS ===")
        
        # Initialize processor
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_MIXED_DS",
            base_uri="http://test-mixed.arkumu.org/data",
            statistics=statistics
        )
        
        # Process
        metrics = processor.process_with_execution_config(
            execution_config=test_mapping_config,
            csv_sources=test_csv_data,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Check entity creation for populated dataset
        order_entities = Resource.objects.filter(
            uri__contains="/entities/orders/"
        ).filter(
            uri__contains="test-mixed"
        )
        assert order_entities.count() == 2, "Should create 2 order entities"
        
        # Check NO entities created for empty datasets
        customer_entities = Resource.objects.filter(
            uri__contains="/entities/customers/"
        ).filter(
            uri__contains="test-mixed"
        )
        assert customer_entities.count() == 0, "Should not create entities for empty customers dataset"
        
        product_entities = Resource.objects.filter(
            uri__contains="/entities/products/"
        ).filter(
            uri__contains="test-mixed"
        )
        assert product_entities.count() == 0, "Should not create entities for empty products dataset"
        
        # But ALL datasets should have URI resources
        for dataset_name in ["customers", "orders", "products"]:
            dataset_uri = f"http://test-mixed.arkumu.org/data/datasets/{dataset_name.lower()}"
            assert Resource.objects.filter(uri=dataset_uri).exists(), \
                f"Dataset URI resource should exist for {dataset_name}"
        
        logger.info("=== MIXED DATASET TEST PASSED ===")
    
    @pytest.mark.django_db(transaction=True)
    def test_dataset_entity_linking_with_empty_datasets(self, test_mapping_config, test_csv_data):
        """Test that entity linking works correctly when some datasets are empty"""
        logger.info("=== TESTING ENTITY LINKING WITH EMPTY DATASETS ===")
        
        # Initialize processor
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_LINKING_EMPTY",
            base_uri="http://test-linking-empty.arkumu.org/data",
            statistics=statistics
        )
        
        # Process
        metrics = processor.process_with_execution_config(
            execution_config=test_mapping_config,
            csv_sources=test_csv_data,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Get isPartOf property
        is_part_of_uri = "http://purl.org/dc/terms/isPartOf"
        is_part_of_prop = Resource.objects.filter(uri=is_part_of_uri).first()
        assert is_part_of_prop is not None, "isPartOf property should exist"
        
        # Check that orders entities are linked to orders dataset
        orders_dataset = Resource.objects.get(
            uri="http://test-linking-empty.arkumu.org/data/datasets/orders"
        )
        
        order_entities = Resource.objects.filter(
            uri__contains="/entities/orders/"
        ).filter(
            uri__contains="test-linking-empty"
        )
        
        # Check linking triples
        linking_triples = Triple.objects.filter(
            subject__in=order_entities,
            predicate=is_part_of_prop,
            object=orders_dataset
        )
        
        assert linking_triples.count() == 2, "All order entities should be linked to orders dataset"
        
        # Verify empty datasets have no entity links (but dataset URI still exists)
        for empty_dataset in ["customers", "products"]:
            dataset_resource = Resource.objects.get(
                uri=f"http://test-linking-empty.arkumu.org/data/datasets/{empty_dataset}"
            )
            
            # Should have no entities linked to it
            empty_links = Triple.objects.filter(
                predicate=is_part_of_prop,
                object=dataset_resource
            )
            assert empty_links.count() == 0, f"Empty dataset {empty_dataset} should have no linked entities"
        
        logger.info("=== ENTITY LINKING WITH EMPTY DATASETS TEST PASSED ===")