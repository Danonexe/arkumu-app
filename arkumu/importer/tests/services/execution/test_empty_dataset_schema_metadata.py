"""
Test schema metadata creation for empty datasets.

This test module verifies that empty datasets create proper schema metadata triples
linking datasets to their entity types and properties from the mapping configuration.
This ensures empty datasets maintain their column structure relationships in the knowledge graph.
"""

import pytest
from unittest.mock import Mock, patch
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor, ProcessingContext
from arkumu.importer.services.mapping_consumer import ExecutionConfig, DatasetConfig, ColumnConfig, ProcessingStrategy
from arkumu.importer.services.mapping_consumer.config_translator import ColumnType
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType


@pytest.fixture
def processor():
    """Create a mapping-aware processor instance."""
    stats = ExecutionStatistics()
    processor = MappingAwareProcessor(
        institution="test_org",
        base_uri="http://test.arkumu.org/data",
        statistics=stats,
        channel_id="test_channel",
        session=Mock()
    )
    return processor


@pytest.fixture
def empty_dataset_config():
    """Create configuration for an empty dataset with multiple column types."""
    return DatasetConfig(
        dataset_name="empty_sammlung",
        columns=[
            ColumnConfig(
                column_name="objekt_id",
                dataset_name="empty_sammlung",
                arkumu_type="objekt_identifier",
                column_type=ColumnType.ANCHOR,
                is_anchor=True,
                datatype="string"
            ),
            ColumnConfig(
                column_name="titel",
                dataset_name="empty_sammlung",
                arkumu_type="objekt_titel",
                column_type=ColumnType.REGULAR,
                datatype="string"
            ),
            ColumnConfig(
                column_name="beschreibung",
                dataset_name="empty_sammlung",
                arkumu_type="objekt_beschreibung",
                column_type=ColumnType.REGULAR,
                datatype="string"
            ),
            ColumnConfig(
                column_name="schlagworte",
                dataset_name="empty_sammlung",
                arkumu_type="objekt_schlagwort",
                column_type=ColumnType.MULTI_VALUE,
                is_multi_value=True,
                multi_value_separator=",",
                datatype="string"
            )
        ]
    )


@pytest.fixture
def execution_config(empty_dataset_config):
    """Create execution config with empty dataset."""
    return ExecutionConfig(
        mapping_id="test_empty_schema_mapping",
        mapping_name="Test Empty Schema Mapping",
        organization="test_org",
        datasets=[empty_dataset_config],
        processing_strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
    )


@pytest.mark.django_db
class TestEmptyDatasetSchemaMetadata:
    """Test suite for empty dataset schema metadata creation."""
    
    def test_empty_dataset_creates_schema_metadata(self, processor, execution_config):
        """Test that empty datasets create proper schema metadata triples."""
        
        # Arrange: Empty CSV data
        csv_sources = {
            "empty_sammlung": []  # Empty dataset
        }
        
        # Act: Process the empty dataset
        with patch('arkumu.metadata.models.Resource.objects') as mock_resource_objects, \
             patch('arkumu.metadata.models.triples.Triple.objects') as mock_triple_objects:
            
            # Mock resource creation
            mock_dataset_resource = Mock(spec=Resource)
            mock_dataset_resource.id = 1
            mock_dataset_resource.uri = "http://test.arkumu.org/data/test-org/datasets/empty-sammlung"
            mock_dataset_resource._meta = Resource._meta
            mock_dataset_resource._state = Mock()
            mock_dataset_resource._state.db = 'default'
            
            mock_entity_type_resource = Mock(spec=Resource)
            mock_entity_type_resource.id = 2
            mock_entity_type_resource.uri = "http://test.arkumu.org/data/test_org/properties/entity-type-empty-sammlung"
            
            mock_resource_objects.get_or_create.return_value = (mock_dataset_resource, True)
            mock_resource_objects.bulk_create.return_value = []
            mock_resource_objects.filter.return_value.select_related.return_value = []
            
            # Mock triple creation
            mock_triple_objects.bulk_create.return_value = []
            
            # Process
            metrics = processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Assert: Verify processing completed
            assert metrics.rows_processed == 0  # No data rows
            
            # Verify resource creation calls for schema metadata
            # Should create: dataset, entity type, properties, schema properties
            create_calls = mock_resource_objects.get_or_create.call_args_list
            
            # Should have calls for creating resources
            assert len(create_calls) > 0
            
            # Verify at least one call was for schema metadata
            schema_uris = [call[1]['uri'] for call in create_calls if 'uri' in call[1]]
            
            # Should include defines-entity-type and defines-property predicates
            assert any('defines-entity-type' in uri for uri in schema_uris)
            assert any('defines-property' in uri for uri in schema_uris)
    
    def test_empty_dataset_creates_all_column_properties(self, processor, execution_config):
        """Test that all columns from mapping config get property resources."""
        
        # Arrange
        csv_sources = {"empty_sammlung": []}
        expected_columns = execution_config.datasets[0].columns
        
        # Act
        with patch('arkumu.metadata.models.Resource.objects') as mock_resource_objects, \
             patch('arkumu.metadata.models.triples.Triple.objects') as mock_triple_objects:
            
            mock_resource = Mock(spec=Resource)
            mock_resource.id = 1
            mock_resource._meta = Resource._meta
            mock_resource._state = Mock()
            mock_resource._state.db = 'default'
            
            mock_resource_objects.get_or_create.return_value = (mock_resource, True)
            mock_resource_objects.bulk_create.return_value = []
            mock_resource_objects.filter.return_value.select_related.return_value = []
            mock_triple_objects.bulk_create.return_value = []
            
            processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Assert: Check that properties were created for each column
            create_calls = mock_resource_objects.get_or_create.call_args_list
            created_uris = [call[1]['uri'] for call in create_calls if 'uri' in call[1]]
            
            # Verify each column arkumu_type appears in created URIs
            for column in expected_columns:
                expected_property_uri = f"http://test.arkumu.org/data/test_org/properties/{column.arkumu_type.replace('_', '-')}"
                # Check if this arkumu_type appears in any created URI
                assert any(column.arkumu_type.replace('_', '-') in uri for uri in created_uris), \
                    f"Property for column {column.arkumu_type} was not created"
    
    def test_empty_dataset_entity_type_creation(self, processor, execution_config):
        """Test that entity type is properly created and linked."""
        
        # Arrange
        csv_sources = {"empty_sammlung": []}
        
        # Act
        with patch('arkumu.metadata.models.Resource.objects') as mock_resource_objects, \
             patch('arkumu.metadata.models.triples.Triple.objects') as mock_triple_objects:
            
            mock_resource = Mock(spec=Resource)
            mock_resource.id = 1
            mock_resource._meta = Resource._meta
            mock_resource._state = Mock()
            mock_resource._state.db = 'default'
            
            mock_resource_objects.get_or_create.return_value = (mock_resource, True)
            mock_resource_objects.bulk_create.return_value = []
            mock_resource_objects.filter.return_value.select_related.return_value = []
            mock_triple_objects.bulk_create.return_value = []
            
            processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Assert: Verify entity type resource creation
            create_calls = mock_resource_objects.get_or_create.call_args_list
            
            # Should create entity type resource
            entity_type_calls = [
                call for call in create_calls 
                if 'defaults' in call[1] 
                and call[1].get('defaults', {}).get('resource_type') == ResourceType.CLASS
            ]
            
            assert len(entity_type_calls) > 0, "Entity type resource should be created"
            
            # Entity type URI should contain dataset name
            entity_type_uri = entity_type_calls[0][1]['uri']
            assert 'entity-type-empty-sammlung' in entity_type_uri or 'entity_type_empty_sammlung' in entity_type_uri
    
    def test_schema_metadata_prevents_orphaned_datasets(self, processor, execution_config):
        """Test that schema metadata prevents datasets from appearing disconnected."""
        
        # This test verifies the fix for the issue where empty datasets like sammlung
        # appeared to have no relationships because schema metadata wasn't created
        
        # Arrange
        csv_sources = {"empty_sammlung": []}
        
        # Act
        with patch('arkumu.metadata.models.Resource.objects') as mock_resource_objects, \
             patch('arkumu.metadata.models.triples.Triple.objects') as mock_triple_objects:
            
            mock_resource = Mock(spec=Resource)
            mock_resource.id = 1
            mock_resource._meta = Resource._meta
            mock_resource._state = Mock()
            mock_resource._state.db = 'default'
            
            mock_resource_objects.get_or_create.return_value = (mock_resource, True)
            mock_resource_objects.bulk_create.return_value = []
            mock_resource_objects.filter.return_value.select_related.return_value = []
            
            # Track relationship triple creation calls
            relationship_triples = []
            def mock_create_relationship_triple(*args):
                relationship_triples.append(args)
            
            # Mock the resource manager's create_relationship_triple method
            processor.resource_manager.create_relationship_triple = Mock(side_effect=mock_create_relationship_triple)
            
            mock_triple_objects.bulk_create.return_value = []
            
            processor.process_with_execution_config(
                execution_config=execution_config,
                csv_sources=csv_sources,
                strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            )
            
            # Assert: Verify that relationship triples were created
            assert len(relationship_triples) > 0, "Schema metadata relationships should be created"
            
            # Should have at least:
            # 1. Dataset -> defines-entity-type -> EntityType
            # 2. EntityType -> defines-property -> Property (for each column)
            expected_min_relationships = 1 + len(execution_config.datasets[0].columns)
            
            assert len(relationship_triples) >= expected_min_relationships, \
                f"Expected at least {expected_min_relationships} relationships, got {len(relationship_triples)}"