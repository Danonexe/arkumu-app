"""
Test Schema-First Blueprint Creation

Tests that schema blueprints are created for ALL datasets in mapping
BEFORE any CSV processing begins, including empty datasets like Sammlung.
"""

import pytest
import logging
from unittest.mock import patch

from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)


@pytest.mark.django_db(transaction=True)
class TestSchemaFirstBlueprints:
    """Test that schema blueprints are created before CSV processing"""
    
    def test_blueprints_created_before_csv_processing(self, production_test_mapping):
        """Test that ALL dataset blueprints are created before any CSV processing"""
        
        # Load the mapping configuration
        from arkumu.importer.services.mapping_consumer import MappingAdapter
        adapter = MappingAdapter()
        execution_config = adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Get all dataset names from mapping
        all_mapping_datasets = {dataset.dataset_name for dataset in execution_config.datasets}
        logger.info(f"=== SCHEMA-FIRST BLUEPRINT TEST ===")
        logger.info(f"Total datasets in mapping: {len(all_mapping_datasets)}")
        logger.info(f"Datasets: {sorted(list(all_mapping_datasets))[:10]}...")
        
        # Create processor with test URI base
        execution_statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_SCHEMA_FIRST",
            base_uri="http://test-schema.arkumu.org/data",
            statistics=execution_statistics
        )
        
        # Mock CSV sources to be empty - this simulates having ONLY the mapping without CSV files
        empty_csv_sources = {}
        
        # Create a mock that tracks when CSV processing would start
        csv_processing_started = False
        original_process_streaming = processor._process_streaming_entity_centric
        
        def mock_streaming_process(context):
            nonlocal csv_processing_started
            csv_processing_started = True
            # Check blueprints exist BEFORE CSV processing
            logger.info(f"🔍 CSV processing starting - checking blueprints exist first...")
            assert len(processor.dataset_blueprints) > 0, "No blueprints created before CSV processing!"
            
            # Verify ALL mapping datasets have blueprints
            missing_blueprints = all_mapping_datasets - set(processor.dataset_blueprints.keys())
            assert len(missing_blueprints) == 0, f"Missing blueprints: {missing_blueprints}"
            
            logger.info(f"✅ All {len(processor.dataset_blueprints)} blueprints created BEFORE CSV processing")
            
            # Return minimal metrics without actual processing
            from arkumu.importer.services.execution.statistics import ExecutionMetrics
            return ExecutionMetrics(
                total_entities_processed=0,
                total_triples_created=0,
                processing_time_seconds=0.1
            )
        
        processor._process_streaming_entity_centric = mock_streaming_process
        
# This should trigger schema blueprint creation FIRST
        metrics = processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=empty_csv_sources,
            strategy=None  # Will use default streaming strategy
        )
        
        # Verify CSV processing was reached (meaning blueprints were created first)
        assert csv_processing_started, "CSV processing phase was never reached"
        
        # Verify ALL datasets from mapping have blueprints
        assert len(processor.dataset_blueprints) == len(all_mapping_datasets)
        logger.info(f"✅ Created blueprints for {len(processor.dataset_blueprints)} datasets")
        
        # Verify specific blueprint structure
        for dataset_name in all_mapping_datasets:
            blueprint = processor.dataset_blueprints[dataset_name]
            assert 'dataset_resource' in blueprint
            assert 'entity_type_resource' in blueprint
            assert 'property_resources' in blueprint
            assert 'fk_relationships' in blueprint
            
            logger.info(f"   📦 {dataset_name}: {len(blueprint['property_resources'])} properties")
        
        # Verify dataset URIs were created (even for empty datasets)
        created_dataset_uris = Resource.objects.filter(
            uri__contains="/datasets/"
        ).filter(
            uri__contains="test-schema.arkumu.org"
        ).values_list('uri', flat=True)
        
        logger.info(f"✅ Created {len(created_dataset_uris)} dataset URI resources")
        
        # Extract dataset names from URIs and verify all mapping datasets have URIs
        created_dataset_names = set()
        for uri in created_dataset_uris:
            if '/datasets/' in uri:
                dataset_name = uri.split('/datasets/')[-1]
                created_dataset_names.add(dataset_name)
        
        missing_dataset_uris = all_mapping_datasets - created_dataset_names
        logger.info(f"✅ Dataset URIs: {len(created_dataset_names)}/{len(all_mapping_datasets)}")
        
        if missing_dataset_uris:
            logger.warning(f"⚠️  Missing dataset URIs: {sorted(missing_dataset_uris)}")
        
        # Check if Sammlung specifically got a blueprint and URI
        if 'Sammlung' in all_mapping_datasets:
            assert 'Sammlung' in processor.dataset_blueprints, "Sammlung blueprint missing"
            assert 'Sammlung' in created_dataset_names, "Sammlung dataset URI missing"
            logger.info("✅ Sammlung (empty dataset) blueprint and URI created successfully")
        
        logger.info("=== SCHEMA-FIRST BLUEPRINT TEST PASSED ===")
        logger.info("✅ Schema-first approach working correctly")
        logger.info("✅ ALL datasets get blueprints BEFORE CSV processing")
        logger.info("✅ Empty datasets included in schema creation")


    def test_empty_dataset_specific_blueprint_creation(self, production_test_mapping):
        """Focused test on empty dataset blueprint creation (like Sammlung)"""
        
        from arkumu.importer.services.mapping_consumer import MappingAdapter
        adapter = MappingAdapter()
        execution_config = adapter.translate_to_execution_config(production_test_mapping.id)
        
        # Find datasets that typically don't have CSV files
        all_datasets = [d.dataset_name for d in execution_config.datasets]
        logger.info(f"🔍 Looking for empty datasets in: {sorted(all_datasets)[:10]}...")
        
        # Create processor
        execution_statistics = ExecutionStatistics()
        processor = MappingAwareProcessor(
            institution="TEST_EMPTY_DATASETS",
            base_uri="http://test-empty.arkumu.org/data",
            statistics=execution_statistics
        )
        
# Call only the schema blueprint creation phase
        processor._create_complete_schema_blueprints(execution_config)
        
        # Verify blueprints were created for ALL datasets
        assert len(processor.dataset_blueprints) == len(all_datasets)
        logger.info(f"✅ Blueprints created for {len(processor.dataset_blueprints)} datasets")
        
        # Check each blueprint structure
        for dataset_name in all_datasets:
            assert dataset_name in processor.dataset_blueprints
            blueprint = processor.dataset_blueprints[dataset_name]
            
            # Verify blueprint has all required components
            assert blueprint['dataset_resource'] is not None
            assert blueprint['entity_type_resource'] is not None
            assert isinstance(blueprint['property_resources'], dict)
            assert isinstance(blueprint['fk_relationships'], list)
            
            logger.info(f"   📦 {dataset_name}: {len(blueprint['property_resources'])} properties")
        
        # Special check for Sammlung if it exists
        if 'Sammlung' in all_datasets:
            sammlung_blueprint = processor.dataset_blueprints['Sammlung']
            logger.info(f"✅ Sammlung blueprint: {len(sammlung_blueprint['property_resources'])} properties")
            logger.info(f"   📁 Dataset URI: {sammlung_blueprint['dataset_resource'].uri}")
            logger.info(f"   🏷️  Entity type: {sammlung_blueprint['entity_type_resource'].name}")
        
        logger.info("✅ Empty dataset blueprint creation verified")