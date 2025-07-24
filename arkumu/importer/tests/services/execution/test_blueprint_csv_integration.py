"""
Test Blueprint + CSV Integration

Tests that the blueprint creation (from mapping) and CSV processing
work together correctly without foreign key conflicts.
"""
import pytest
import logging
from typing import Dict, Any

from arkumu.metadata.models import Resource, Mapping
from arkumu.users.models import Organization
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy

logger = logging.getLogger(__name__)


@pytest.mark.django_db(transaction=True)
class TestBlueprintCSVIntegration:
    """Test that blueprint creation and CSV processing work together"""
    
    def setup_method(self):
        """Setup test environment"""
        self.test_organization = None
        self.test_mapping = None
    
    def test_blueprint_creation_then_csv_processing(self):
        """Test that blueprint creation followed by CSV processing works without conflicts"""
        
        # Step 1: Create test mapping that will trigger blueprint creation
        self.test_organization, _ = Organization.objects.get_or_create(
            code="TEST_BLUEPRINT_ORG",
            defaults={"name": "Test Blueprint Organization"}
        )
        
        # Create a simple mapping configuration
        mapping_config = {
            "version": "1.1",
            "workspace_columns": {
                "TestDataset": {
                    "id": {
                        "arkumu_type": "entity_id",
                        "is_anchor": True,
                        "column_type": "anchor"
                    },
                    "name": {
                        "arkumu_type": "entity_name", 
                        "column_type": "regular"
                    }
                }
            },
            "workspace_datasets": ["TestDataset"],
            "fk_relationships": {},
            "relationship_contexts": {}
        }
        
        # Create mapping - this should trigger blueprint creation via signal
        self.test_mapping = Mapping.objects.create(
            name="Test Blueprint Mapping",
            organization_id=self.test_organization,
            mapping_config=mapping_config,
            validation_status="validated"  # This should trigger blueprint creation
        )
        
        logger.info(f"Created test mapping: {self.test_mapping.id}")
        
        # Step 2: Verify blueprint created dataset resources
        dataset_resources_before = Resource.objects.filter(
            uri__contains="testdataset",
            resource_type="IRI"
        )
        
        logger.info(f"Dataset resources after blueprint: {dataset_resources_before.count()}")
        for resource in dataset_resources_before:
            logger.info(f"  Blueprint resource: {resource.uri}")
        
        # Step 3: Simulate CSV processing with mapping adapter
        mapping_adapter = MappingAdapter()
        execution_config = mapping_adapter.translate_to_execution_config(self.test_mapping.id)
        
        # Step 4: Create CSV data
        csv_sources = {
            "TestDataset": {
                "headers": ["id", "name"],
                "rows": [
                    {"id": "1", "name": "Test Entity 1"},
                    {"id": "2", "name": "Test Entity 2"}
                ],
                "row_count": 2
            }
        }
        
        # Step 5: Process with MappingAwareProcessor
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_BLUEPRINT_INST",
            base_uri="http://test-blueprint.arkumu.org/data",
            statistics=statistics
        )
        
        try:
            # This should work without foreign key conflicts
            metrics = processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Step 6: Verify processing succeeded
            assert metrics.rows_processed == 2
            assert metrics.errors == 0
            
            # Step 7: Verify dataset resources exist (should be same as blueprint)
            dataset_resources_after = Resource.objects.filter(
                uri__contains="testdataset",
                resource_type="IRI"
            )
            
            logger.info(f"Dataset resources after processing: {dataset_resources_after.count()}")
            
            # Should have same resources as before (reused from blueprint)
            assert dataset_resources_after.count() >= dataset_resources_before.count()
            
            # Step 8: Verify entity resources were created
            entity_resources = Resource.objects.filter(
                uri__contains="test-blueprint.arkumu.org"
            ).filter(
                uri__contains="/entities/"
            )
            
            logger.info(f"Entity resources created: {entity_resources.count()}")
            assert entity_resources.count() >= 2  # Should have created 2 entities
            
            # Step 9: Verify triples were created
            triples = Triple.objects.filter(
                subject__uri__contains="test-blueprint.arkumu.org"
            )
            
            logger.info(f"Triples created: {triples.count()}")
            assert triples.count() > 0
            
            logger.info("✓ Blueprint + CSV integration test passed")
            
        except Exception as e:
            logger.error(f"Blueprint + CSV integration test failed: {e}")
            raise
    
    def test_empty_dataset_handling_with_blueprint(self):
        """Test that empty datasets work correctly with blueprint"""
        
        # Create test mapping with one dataset that will have no CSV data
        self.test_organization, _ = Organization.objects.get_or_create(
            code="TEST_EMPTY_ORG",
            defaults={"name": "Test Empty Organization"}
        )
        
        mapping_config = {
            "version": "1.1",
            "workspace_columns": {
                "EmptyDataset": {
                    "id": {
                        "arkumu_type": "entity_id",
                        "is_anchor": True,
                        "column_type": "anchor"
                    }
                },
                "FilledDataset": {
                    "id": {
                        "arkumu_type": "entity_id",
                        "is_anchor": True,
                        "column_type": "anchor"
                    },
                    "value": {
                        "arkumu_type": "entity_value",
                        "column_type": "regular"
                    }
                }
            },
            "workspace_datasets": ["EmptyDataset", "FilledDataset"],
            "fk_relationships": {},
            "relationship_contexts": {}
        }
        
        self.test_mapping = Mapping.objects.create(
            name="Test Empty Dataset Mapping",
            organization_id=self.test_organization,
            mapping_config=mapping_config,
            validation_status="validated"
        )
        
        # CSV data - EmptyDataset has no data, FilledDataset has data
        csv_sources = {
            "EmptyDataset": {
                "headers": ["id"],
                "rows": [],
                "row_count": 0
            },
            "FilledDataset": {
                "headers": ["id", "value"],
                "rows": [
                    {"id": "1", "value": "Test Value"}
                ],
                "row_count": 1
            }
        }
        
        # Process
        mapping_adapter = MappingAdapter()
        execution_config = mapping_adapter.translate_to_execution_config(self.test_mapping.id)
        
        statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_EMPTY_INST",
            base_uri="http://test-empty.arkumu.org/data",
            statistics=statistics
        )
        
        try:
            metrics = processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Should process the one row from FilledDataset
            assert metrics.rows_processed == 1
            assert metrics.errors == 0
            
            # Both datasets should have URIs (from blueprint)
            empty_dataset_resources = Resource.objects.filter(
                uri__contains="emptydataset",
                resource_type="IRI"
            )
            filled_dataset_resources = Resource.objects.filter(
                uri__contains="filleddataset", 
                resource_type="IRI"
            )
            
            assert empty_dataset_resources.count() >= 1, "Empty dataset should have URI from blueprint"
            assert filled_dataset_resources.count() >= 1, "Filled dataset should have URI"
            
            logger.info("✓ Empty dataset handling with blueprint test passed")
            
        except Exception as e:
            logger.error(f"Empty dataset handling test failed: {e}")
            raise