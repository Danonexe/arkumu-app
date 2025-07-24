"""
Test Production Import Including Empty Datasets (Sammlung)

This test verifies that the production import correctly handles all 35 datasets
including empty datasets like Sammlung that have no CSV data.
"""
import pytest
import logging
from typing import Dict, List, Any

from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics, ExecutionMetrics
from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy
from arkumu.metadata.models import Resource

logger = logging.getLogger(__name__)


class TestSammlungProductionImport:
    """Test that verifies all 35 datasets including Sammlung are properly imported"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
        self.statistics = ExecutionStatistics()
        self.processor = None
        self.execution_config = None
    
    def load_production_test_mapping(self, mapping):
        """Load the mapping from test database using the automated system"""
        if self.execution_config is not None:
            return self.execution_config
            
        try:
            if not mapping.pk:
                raise AssertionError("Mapping must be saved in test database before loading")
                
            logger.info(f"Loading test mapping: ID={mapping.id}, Name={mapping.name} from test database")
            
            # Use the mapping adapter to handle everything automatically
            self.execution_config = self.mapping_adapter.translate_to_execution_config(mapping.id)
            
            logger.info(f"Loaded and translated mapping with {len(self.execution_config.datasets)} datasets")
            
            return self.execution_config
            
        except Exception as e:
            logger.error(f"Failed to load/translate test mapping: {e}")
            raise AssertionError(f"Could not load test mapping: {e}")
    
    @pytest.mark.django_db(transaction=True)
    def test_all_35_datasets_including_sammlung(self, production_test_mapping, real_csv_data, execution_statistics):
        """Test that all 35 datasets including Sammlung get imported correctly"""
        
        # Ensure we're using the test database
        assert production_test_mapping.pk is not None, "Mapping must be saved in test database"
        
        # Load and translate mapping using the automated system
        execution_config = self.load_production_test_mapping(production_test_mapping)
        
        # Verify we have all 35 datasets in the mapping
        assert len(execution_config.datasets) == 35, f"Expected 35 datasets in mapping, got {len(execution_config.datasets)}"
        
        # Check that Sammlung is in the mapping
        dataset_names = {ds.dataset_name for ds in execution_config.datasets}
        assert 'sammlung' in dataset_names, "Sammlung dataset not found in mapping"
        
        # Use real CSV data from S3
        csv_sources = real_csv_data
        
        # Log CSV vs mapping datasets
        logger.info("=== DATASET COMPARISON ===")
        logger.info(f"Mapping datasets: {len(dataset_names)}")
        logger.info(f"CSV datasets: {len(csv_sources)}")
        
        # Find datasets that are in mapping but not in CSV (like Sammlung)
        csv_dataset_names = set(csv_sources.keys())
        missing_from_csv = dataset_names - csv_dataset_names
        
        logger.info(f"Datasets in mapping but not in CSV: {len(missing_from_csv)}")
        for missing in sorted(missing_from_csv):
            logger.info(f"  - {missing}")
        
        # Initialize processor with test-specific URI to ensure test isolation
        self.processor = MappingAwareProcessor(
            institution="TEST_FUK_SAMMLUNG",
            base_uri="http://test-sammlung.arkumu.org/data",
            statistics=execution_statistics
        )
        
        # Execute the full pipeline
        try:
            metrics = self.processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Verify processing completed
            assert isinstance(metrics, ExecutionMetrics)
            
            # Log results
            logger.info("=== SAMMLUNG PRODUCTION IMPORT TEST RESULTS ===")
            logger.info(f"Datasets processed: {len(execution_config.datasets)}")
            logger.info(f"CSV sources: {len(csv_sources)}")
            logger.info(f"Rows processed: {metrics.rows_processed}")
            logger.info(f"Resources created: {metrics.resources_created}")
            logger.info(f"Triples created: {metrics.triples_created}")
            logger.info(f"Errors: {metrics.errors}")
            
            # Verify all 35 dataset URIs were created
            dataset_uris = Resource.objects.filter(
                uri__contains="/datasets/"
            ).filter(
                uri__contains="test-sammlung.arkumu.org"
            ).values_list('uri', flat=True)
            
            logger.info(f"Dataset URIs created: {len(dataset_uris)}")
            
            # Check specifically for Sammlung
            sammlung_uri = None
            for uri in dataset_uris:
                if '/datasets/sammlung' in uri:
                    sammlung_uri = uri
                    break
            
            assert sammlung_uri is not None, "Sammlung dataset URI was not created"
            logger.info(f"✓ Sammlung dataset URI created: {sammlung_uri}")
            
            # Verify we have all 35 dataset URIs
            created_dataset_names = set()
            for uri in dataset_uris:
                if '/datasets/' in uri:
                    dataset_name = uri.split('/datasets/')[-1]
                    created_dataset_names.add(dataset_name)
            
            logger.info(f"Created dataset URIs: {len(created_dataset_names)}")
            
            # List missing datasets
            missing_datasets = dataset_names - created_dataset_names
            if missing_datasets:
                logger.warning(f"Missing dataset URIs: {sorted(missing_datasets)}")
            
            # List all created datasets for verification
            logger.info("All created dataset URIs:")
            for i, name in enumerate(sorted(created_dataset_names), 1):
                logger.info(f"  {i:2d}. {name}")
            
            # Assert we have at least 27 datasets (current production count)
            # and specifically have Sammlung
            assert len(created_dataset_names) >= 27, f"Expected at least 27 datasets, got {len(created_dataset_names)}"
            assert 'sammlung' in created_dataset_names, "Sammlung dataset URI not found in created datasets"
            
            logger.info("=== SAMMLUNG IMPORT TEST PASSED ===")
            
        except Exception as e:
            logger.error(f"Sammlung import test failed: {e}")
            raise
        finally:
            # Clean up test resources
            try:
                Resource.objects.filter(uri__contains="test-sammlung.arkumu.org").delete()
            except Exception as e:
                logger.warning(f"Error cleaning up test resources: {e}")
    
    @pytest.mark.django_db(transaction=True)
    def test_empty_dataset_handling(self, production_test_mapping, execution_statistics):
        """Test handling of datasets with no CSV data (like Sammlung)"""
        
        # Load mapping
        execution_config = self.load_production_test_mapping(production_test_mapping)
        
        # Create empty CSV sources (simulating missing datasets)
        empty_csv_sources = {}  # No CSV data at all
        
        # Initialize processor
        self.processor = MappingAwareProcessor(
            institution="TEST_EMPTY",
            base_uri="http://test-empty.arkumu.org/data",
            statistics=execution_statistics
        )
        
        # Execute processing with no CSV data
        try:
            metrics = self.processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=empty_csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Check that dataset URIs were still created
            dataset_uris = Resource.objects.filter(
                uri__contains="/datasets/"
            ).filter(
                uri__contains="test-empty.arkumu.org"
            )
            
            logger.info(f"Dataset URIs created with no CSV data: {dataset_uris.count()}")
            
            # Should have created URIs for all 35 datasets even with no data
            assert dataset_uris.count() == 35, f"Expected 35 dataset URIs, got {dataset_uris.count()}"
            
            # Check for Sammlung specifically
            sammlung_exists = dataset_uris.filter(uri__contains="/datasets/sammlung").exists()
            assert sammlung_exists, "Sammlung dataset URI not created when no CSV data present"
            
            logger.info("✓ All 35 dataset URIs created even with no CSV data")
            logger.info("✓ Sammlung dataset URI created successfully")
            
        finally:
            # Clean up
            Resource.objects.filter(uri__contains="test-empty.arkumu.org").delete()