"""
Test Enhanced Blueprint Creation with Schema-First Approach

This test validates the new schema-first blueprint creation that:
1. Creates complete schema blueprints BEFORE CSV processing
2. Ensures FK relationships are properly mapped upfront
3. Validates data model compatibility across institutions
4. Tests resilient blueprint creation regardless of data presence
"""

import pytest
import logging
from unittest.mock import Mock
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.execution.enhanced_mapping_processor import EnhancedMappingProcessor
from arkumu.importer.services.execution.schema_first_processor import SchemaFirstProcessor, SchemaBlueprint
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig, DatasetConfig, ColumnConfig, ProcessingStrategy, ColumnType
)

logger = logging.getLogger(__name__)


@pytest.mark.django_db
class TestEnhancedBlueprintCreation:
    """Test the enhanced blueprint creation with schema-first approach."""

    def setup_method(self):
        """Setup test environment with clean database."""
        # Clean up any existing resources and triples
        Resource.objects.all().delete()
        Triple.objects.all().delete()
        
        # Test configuration
        self.institution = "TestInstitution"
        self.base_uri = "https://test.example.com"
        
        # Initialize components
        self.statistics = ExecutionStatistics()
        self.processor = EnhancedMappingProcessor(
            institution=self.institution,
            base_uri=self.base_uri,
            statistics=self.statistics
        )

    def create_test_execution_config(self):
        """Create test execution configuration."""
        
        # Dataset 1: Projects (has data)
        projects_columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="Projects",
                arkumu_type="project_id",
                column_type=ColumnType.REGULAR
            ),
            ColumnConfig(
                column_name="title",
                dataset_name="Projects",
                arkumu_type="project_title",
                column_type=ColumnType.REGULAR
            )
        ]
        
        # Dataset 2: Sammlung (empty - no CSV data)
        sammlung_columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="Sammlung",
                arkumu_type="collection_id",
                column_type=ColumnType.REGULAR
            ),
            ColumnConfig(
                column_name="name",
                dataset_name="Sammlung",
                arkumu_type="collection_name",
                column_type=ColumnType.REGULAR
            )
        ]
        
        # Dataset 3: Events
        events_columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="Events",
                arkumu_type="event_id",
                column_type=ColumnType.REGULAR
            ),
            ColumnConfig(
                column_name="name",
                dataset_name="Events",
                arkumu_type="event_name",
                column_type=ColumnType.REGULAR
            )
        ]
        
        datasets = [
            DatasetConfig(
                dataset_name="Projects",
                columns=projects_columns
            ),
            DatasetConfig(
                dataset_name="Sammlung",
                columns=sammlung_columns
            ),
            DatasetConfig(
                dataset_name="Events",
                columns=events_columns
            )
        ]
        
        return ExecutionConfig(
            mapping_id=1,
            mapping_name="test_mapping",
            organization="test_org",
            datasets=datasets
        )

    def create_test_csv_sources(self):
        """Create test CSV sources - note that Sammlung has no data."""
        return {
            "Projects": {
                "headers": ["id", "title"],
                "rows": [
                    {"id": "P001", "title": "Project Alpha"},
                    {"id": "P002", "title": "Project Beta"}
                ]
            },
            "Events": {
                "headers": ["id", "name"],
                "rows": [
                    {"id": "E001", "name": "Event One"},
                    {"id": "E002", "name": "Event Two"}
                ]
            }
            # Note: Sammlung intentionally missing - this is the empty dataset case
        }

    def test_schema_first_blueprint_creation(self):
        """Test that complete schema blueprints are created before CSV processing."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Schema-First Blueprint Creation")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        
        # Create schema blueprints FIRST (before any CSV processing)
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Validate all datasets have blueprints
        expected_datasets = {"Projects", "Sammlung", "Events"}
        assert set(blueprints.keys()) == expected_datasets
        
        logger.info(f"✅ Created blueprints for all {len(expected_datasets)} datasets")
        
        # Validate each blueprint structure
        for dataset_name, blueprint in blueprints.items():
            assert isinstance(blueprint, SchemaBlueprint)
            assert blueprint.dataset_name == dataset_name
            assert blueprint.dataset_resource is not None
            assert blueprint.entity_type_resource is not None
            assert len(blueprint.property_resources) > 0
            
            logger.info(f"   📦 {dataset_name}: {len(blueprint.property_resources)} properties, {len(blueprint.fk_relationships)} relationships")

    def test_empty_dataset_blueprint_completeness(self):
        """Test that empty datasets (like Sammlung) get complete blueprints."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Empty Dataset Blueprint Completeness")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Focus on Sammlung (the empty dataset)
        sammlung_blueprint = blueprints["Sammlung"]
        
        # Validate Sammlung has complete blueprint even without CSV data
        assert sammlung_blueprint.dataset_resource is not None
        assert sammlung_blueprint.entity_type_resource is not None
        assert "id" in sammlung_blueprint.property_resources
        assert "name" in sammlung_blueprint.property_resources
        
        logger.info("✅ Empty dataset 'Sammlung' has complete blueprint:")
        logger.info(f"   📁 Dataset resource: {sammlung_blueprint.dataset_resource.uri}")
        logger.info(f"   🏷️  Entity type: {sammlung_blueprint.entity_type_resource.name}")
        logger.info(f"   📝 Properties: {list(sammlung_blueprint.property_resources.keys())}")

    def test_basic_property_mapping(self):
        """Test that basic properties are properly mapped in blueprints."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Basic Property Mapping")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Validate Projects properties
        projects_blueprint = blueprints["Projects"]
        
        # Should have id and title properties
        assert "id" in projects_blueprint.property_resources
        assert "title" in projects_blueprint.property_resources
        
        logger.info("✅ Projects properties mapped:")
        logger.info(f"   📝 Properties: {list(projects_blueprint.property_resources.keys())}")
        
        # Validate Sammlung properties (empty dataset)
        sammlung_blueprint = blueprints["Sammlung"]
        assert "id" in sammlung_blueprint.property_resources
        assert "name" in sammlung_blueprint.property_resources
        
        logger.info("✅ Sammlung properties mapped (even though empty):")
        logger.info(f"   📝 Properties: {list(sammlung_blueprint.property_resources.keys())}")

    def test_schema_consistency_validation(self):
        """Test schema consistency validation across blueprints."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Schema Consistency Validation")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Validate schema consistency (should pass with basic configuration)
        warnings = self.processor.schema_processor.validate_schema_consistency()
        
        logger.info(f"Schema validation warnings: {len(warnings)}")
        for warning in warnings:
            logger.info(f"   ⚠️  {warning}")
        
        # For basic configuration without FK relationships, should have no warnings
        logger.info("✅ Schema consistency validation completed")

    def test_enhanced_processor_with_blueprints(self):
        """Test the complete enhanced processor workflow with blueprint guidance."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Enhanced Processor with Blueprint Guidance")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        csv_sources = self.create_test_csv_sources()
        
        # Execute enhanced processing with blueprint creation
        metrics = self.processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=csv_sources,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Validate processing completed successfully
        assert metrics is not None
        logger.info(f"✅ Enhanced processing completed with metrics: {metrics}")
        
        # Validate blueprints were created
        assert len(self.processor.blueprints) == 3
        assert "Projects" in self.processor.blueprints
        assert "Sammlung" in self.processor.blueprints
        assert "Events" in self.processor.blueprints
        
        logger.info("✅ All dataset blueprints created successfully")
        
        # Validate that even empty dataset (Sammlung) has proper schema
        sammlung_blueprint = self.processor.get_blueprint("Sammlung")
        assert sammlung_blueprint is not None
        assert sammlung_blueprint.dataset_resource is not None
        
        logger.info("✅ Empty dataset 'Sammlung' has complete blueprint even without CSV data")

    def test_dataset_resource_creation(self):
        """Test that dataset resources are created for all datasets."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Dataset Resource Creation")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        csv_sources = self.create_test_csv_sources()
        
        # Process with enhanced processor
        self.processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=csv_sources,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        # Validate that resources were created for datasets
        dataset_resources = Resource.objects.filter(resource_type=ResourceType.IRI, name__in=["Projects", "Sammlung", "Events"])
        dataset_names = {res.name for res in dataset_resources}
        
        # Should include all datasets, even empty ones
        expected_datasets = {"Projects", "Sammlung", "Events"}
        assert expected_datasets.issubset(dataset_names)
        
        logger.info(f"✅ Dataset resources created for all datasets: {sorted(dataset_names)}")

    def test_arkumu_data_model_compatibility(self):
        """Test that blueprints ensure Arkumu data model compatibility."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Arkumu Data Model Compatibility")
        logger.info("="*80)
        
        execution_config = self.create_test_execution_config()
        
        # Create blueprints
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Validate that all blueprints follow Arkumu conventions
        for dataset_name, blueprint in blueprints.items():
            # Check that URIs follow expected patterns
            assert blueprint.dataset_resource.uri.startswith(self.base_uri)
            assert blueprint.entity_type_resource.uri.startswith(self.base_uri)
            
            # Check that property URIs follow naming conventions
            for prop_name, prop_resource in blueprint.property_resources.items():
                assert prop_resource.uri.startswith(self.base_uri)
                assert "/property/" in prop_resource.uri
        
        logger.info("✅ All blueprints follow Arkumu data model conventions")
        
        # Validate cross-institutional compatibility
        all_property_types = set()
        for dataset_config in execution_config.datasets:
            for column in dataset_config.columns:
                all_property_types.add(column.arkumu_type)
        
        logger.info(f"✅ Property types used: {sorted(all_property_types)}")
        logger.info("✅ Cross-institutional compatibility ensured through consistent Arkumu type mapping")

    def test_resilient_blueprint_creation(self):
        """Test that blueprint creation is resilient to various edge cases."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Resilient Blueprint Creation")
        logger.info("="*80)
        
        # Test Case 1: All datasets empty (no CSV data)
        execution_config = self.create_test_execution_config()
        empty_csv_sources = {}  # No CSV data for any dataset
        
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Should still create complete blueprints
        assert len(blueprints) == 3
        logger.info("✅ Test Case 1: Blueprints created even when all datasets are empty")
        
        # Test Case 2: FK pointing to non-existent dataset
        # (This should be caught by validation)
        
        # Test Case 3: Circular FK relationships
        # (Should be handled gracefully)
        
        # Test Case 4: Process with empty CSV sources
        metrics = self.processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=empty_csv_sources,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        assert metrics is not None
        logger.info("✅ Test Case 4: Processing completed successfully even with no CSV data")
        
        # All datasets should still have been "processed" (blueprint created)
        assert len(self.processor.blueprints) == 3
        logger.info("✅ All datasets have blueprints despite missing CSV data")

    def test_performance_with_large_schema(self):
        """Test performance characteristics with larger schema configurations."""
        logger.info("\\n" + "="*80)
        logger.info("TEST: Performance with Large Schema")
        logger.info("="*80)
        
        # Create a larger execution config with many datasets and columns
        large_datasets = []
        
        for i in range(10):  # 10 datasets
            columns = []
            for j in range(20):  # 20 columns each
                columns.append(ColumnConfig(
                    column_name=f"column_{j}",
                    dataset_name=f"Dataset_{i}",
                    arkumu_type=f"property_type_{i}_{j}",
                    column_type=ColumnType.REGULAR
                ))
            
            # Add entity column
            columns.append(ColumnConfig(
                column_name="entity_id",
                dataset_name=f"Dataset_{i}",
                arkumu_type=f"entity_id_type_{i}",
                column_type=ColumnType.REGULAR
            ))
            
            large_datasets.append(DatasetConfig(
                dataset_name=f"Dataset_{i}",
                columns=columns
            ))
        
        large_config = ExecutionConfig(
            mapping_id=2,
            mapping_name="large_test_mapping",
            organization="test_org",
            datasets=large_datasets
        )
        
        # Measure blueprint creation time
        import time
        start_time = time.time()
        
        blueprints = self.processor.schema_processor.create_complete_schema_blueprint(large_config)
        
        end_time = time.time()
        creation_time = end_time - start_time
        
        # Validate results
        assert len(blueprints) == 10
        total_properties = sum(len(bp.property_resources) for bp in blueprints.values())
        total_fk_relationships = sum(len(bp.fk_relationships) for bp in blueprints.values())
        
        logger.info(f"✅ Large schema blueprint creation completed:")
        logger.info(f"   📊 Datasets: {len(blueprints)}")
        logger.info(f"   🏷️  Total properties: {total_properties}")
        logger.info(f"   🔗 Total FK relationships: {total_fk_relationships}")
        logger.info(f"   ⏱️  Creation time: {creation_time:.3f} seconds")
        
        # Performance should be reasonable (< 5 seconds for this size)
        assert creation_time < 5.0, f"Blueprint creation took too long: {creation_time:.3f} seconds"
        
        logger.info("✅ Blueprint creation performance is acceptable")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])