"""
Test Schema Service for Post-Import CRUD

Tests the schema service that provides access to complete schema
information for creating and validating entities after import.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

from django.core.cache import cache

from arkumu.importer.services.schema_service import SchemaService
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig, DatasetConfig, ColumnConfig, ColumnType
)
from arkumu.metadata.models.resource import Resource, ResourceType

logger = logging.getLogger(__name__)


@pytest.mark.django_db(transaction=True)
class TestSchemaService:
    """Test schema service for post-import CRUD operations"""
    
    @pytest.fixture
    def mock_mapping_adapter(self):
        """Mock the mapping adapter to return test config"""
        with patch('arkumu.importer.services.schema_service.MappingAdapter') as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            
            # Create test execution config
            author_columns = [
                ColumnConfig(
                    dataset_name="authors",
                    column_name="author_id",
                    column_type=ColumnType.ANCHOR,
                    arkumu_type="author_identifier"
                ),
                ColumnConfig(
                    dataset_name="authors",
                    column_name="name",
                    column_type=ColumnType.REGULAR,
                    arkumu_type="person_name"
                ),
                ColumnConfig(
                    dataset_name="authors",
                    column_name="email",
                    column_type=ColumnType.REGULAR,
                    arkumu_type="email_address"
                )
            ]
            
            book_columns = [
                ColumnConfig(
                    dataset_name="books",
                    column_name="book_id",
                    column_type=ColumnType.ANCHOR,
                    arkumu_type="book_identifier"
                ),
                ColumnConfig(
                    dataset_name="books",
                    column_name="title",
                    column_type=ColumnType.REGULAR,
                    arkumu_type="book_title"
                ),
                ColumnConfig(
                    dataset_name="books",
                    column_name="author_id",
                    column_type=ColumnType.FOREIGN_KEY,
                    arkumu_type="author_reference"
                )
            ]
            
            config = ExecutionConfig(
                mapping_id="test_service_mapping_456",
                mapping_name="Test Mapping",
                organization="TEST_ORG",
                datasets=[
                    DatasetConfig(dataset_name="authors", columns=author_columns),
                    DatasetConfig(dataset_name="books", columns=book_columns)
                ]
            )
            
            mock_adapter.translate_to_execution_config.return_value = config
            
            yield mock_adapter_class
    
    def test_schema_service_initialization(self, mock_mapping_adapter):
        """Test schema service initializes correctly"""
        
        service = SchemaService(
            mapping_id="test_service_mapping_456",
            institution="TEST_SERVICE",
            base_uri="http://test-service.arkumu.org/data"
        )
        
        assert service.mapping_id == "test_service_mapping_456"
        assert service.institution == "TEST_SERVICE"
        assert service.base_uri == "http://test-service.arkumu.org/data"
        assert service._schema_loaded is False
        
        logger.info("✅ Schema service initialization works")
    
    def test_schema_loading_from_cache(self, mock_mapping_adapter):
        """Test schema service loads from cache when available"""
        
        # Pre-populate cache with test blueprints
        cache_key = "complete_schema_blueprints_mapping_test_service_mapping_456"
        test_blueprints = {
            "authors": {
                'dataset_name': 'authors',
                'entity_type_resource': MagicMock(name='Person'),
                'property_resources': {
                    'author_id': MagicMock(uri='http://test/prop/author_id'),
                    'name': MagicMock(uri='http://test/prop/name')
                },
                'column_metadata': {
                    'author_id': {'is_anchor': True},
                    'name': {'is_required': True}
                },
                'anchor_columns': [{'column_name': 'author_id'}],
                'multi_value_schemas': {},
                'external_ontology_schemas': {},
                'fk_relationships': []
            }
        }
        cache.set(cache_key, test_blueprints, timeout=3600)
        
        # Create service
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        # Get schema - should load from cache
        schema = service.get_dataset_schema("authors")
        
        assert schema is not None
        assert service._schema_loaded is True
        # Verify mapping adapter was NOT called since we used cache
        assert not mock_mapping_adapter.called
        
        logger.info("✅ Schema service loads from cache successfully")
    
    def test_schema_creation_when_not_cached(self, mock_mapping_adapter):
        """Test schema service creates schema when not in cache"""
        
        # Clear cache
        cache.clear()
        
        # Create service
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        # Mock the processor creation
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            # Mock dataset blueprints
            mock_processor.dataset_blueprints = {
                "authors": {
                    'dataset_name': 'authors',
                    'entity_type_resource': MagicMock(name='Person'),
                    'property_resources': {},
                    'column_metadata': {},
                    'anchor_columns': [],
                    'multi_value_schemas': {},
                    'external_ontology_schemas': {},
                    'fk_relationships': []
                }
            }
            
            # Get schema - should create new
            schema = service.get_dataset_schema("authors")
            
            assert schema is not None
            assert service._schema_loaded is True
            # Verify mapping adapter WAS called
            assert mock_mapping_adapter.called
            # Verify processor was created
            assert mock_processor._create_complete_schema_blueprints.called
        
        logger.info("✅ Schema service creates schema when not cached")
    
    def test_list_datasets(self, mock_mapping_adapter):
        """Test listing all datasets in schema"""
        
        # Clear cache
        cache.clear()
        
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            mock_processor.dataset_blueprints = {
                "authors": {},
                "books": {},
                "publishers": {}
            }
            
            datasets = service.list_datasets()
            
            assert len(datasets) == 3
            assert "authors" in datasets
            assert "books" in datasets
            assert "publishers" in datasets
        
        logger.info("✅ List datasets returns all schema datasets")
    
    def test_get_dataset_properties(self, mock_mapping_adapter):
        """Test getting dataset properties with metadata"""
        
        cache.clear()
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            mock_processor.dataset_blueprints = {
                "authors": {
                    'column_metadata': {
                        'author_id': {
                            'column_type': 'anchor',
                            'is_anchor': True,
                            'arkumu_type': 'author_identifier'
                        },
                        'name': {
                            'column_type': 'regular',
                            'is_required': True,
                            'arkumu_type': 'person_name'
                        }
                    }
                }
            }
            
            mock_processor.get_schema_for_entity_creation.return_value = {
                'column_metadata': mock_processor.dataset_blueprints["authors"]['column_metadata']
            }
            
            properties = service.get_dataset_properties("authors")
            
            assert len(properties) == 2
            assert 'author_id' in properties
            assert properties['author_id']['is_anchor'] is True
            assert properties['name']['is_required'] is True
        
        logger.info("✅ Get dataset properties returns column metadata")
    
    def test_validate_entity_data(self, mock_mapping_adapter):
        """Test entity data validation against schema"""
        
        cache.clear()
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            # Setup schema
            schema = {
                'anchor_columns': [{'column_name': 'author_id'}],
                'column_metadata': {
                    'author_id': {'is_anchor': True},
                    'name': {'is_required': True},
                    'email': {'is_required': False}
                }
            }
            
            mock_processor.get_schema_for_entity_creation.return_value = schema
            mock_processor.dataset_blueprints = {"authors": {}}
            
            # Test valid data
            valid_data = {
                'author_id': 'A123',
                'name': 'John Doe',
                'email': 'john@example.com'
            }
            
            result = service.validate_entity_data("authors", valid_data)
            assert result['valid'] is True
            assert len(result['errors']) == 0
            
            # Test missing required field
            invalid_data = {
                'author_id': 'A123',
                'email': 'john@example.com'  # Missing required 'name'
            }
            
            result = service.validate_entity_data("authors", invalid_data)
            assert result['valid'] is False
            assert any('name' in error for error in result['errors'])
            
            # Test missing anchor column
            invalid_data2 = {
                'name': 'John Doe',
                'email': 'john@example.com'  # Missing anchor 'author_id'
            }
            
            result = service.validate_entity_data("authors", invalid_data2)
            assert result['valid'] is False
            assert any('author_id' in error for error in result['errors'])
        
        logger.info("✅ Entity validation works correctly")
    
    def test_create_entity(self, mock_mapping_adapter):
        """Test creating new entity through schema service"""
        
        cache.clear()
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            # Setup mocks
            mock_entity = MagicMock()
            mock_entity.uri = "http://test/authors/A123"
            mock_entity.id = 999
            
            mock_processor.create_entity_from_schema.return_value = mock_entity
            mock_processor.get_schema_for_entity_creation.return_value = {
                'anchor_columns': [{'column_name': 'author_id'}],
                'column_metadata': {
                    'author_id': {'is_anchor': True},
                    'name': {'is_required': True}
                }
            }
            mock_processor.dataset_blueprints = {"authors": {}}
            
            # Create entity
            entity_data = {
                'author_id': 'A123',
                'name': 'Jane Smith'
            }
            
            success, result = service.create_entity("authors", entity_data)
            
            assert success is True
            assert result['entity_uri'] == "http://test/authors/A123"
            assert result['entity_id'] == 999
            assert 'message' in result
            
            # Verify processor was called correctly
            mock_processor.create_entity_from_schema.assert_called_once_with("authors", entity_data)
        
        logger.info("✅ Entity creation through service works")
    
    def test_schema_visualization_data(self, mock_mapping_adapter):
        """Test getting schema visualization data"""
        
        cache.clear()
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            # Setup blueprints
            mock_processor.dataset_blueprints = {
                "authors": {
                    'entity_type_resource': MagicMock(name='Person'),
                    'property_resources': {'author_id': MagicMock(), 'name': MagicMock()},
                    'fk_relationships': [],
                    'anchor_columns': [{'column_name': 'author_id'}],
                    'multi_value_schemas': {},
                    'external_ontology_schemas': {}
                },
                "books": {
                    'entity_type_resource': MagicMock(name='Book'),
                    'property_resources': {'book_id': MagicMock(), 'title': MagicMock()},
                    'fk_relationships': [{
                        'source_dataset': 'books',
                        'target_dataset': 'authors',
                        'relationship_type': 'has_author',
                        'source_column': 'author_id',
                        'target_column': 'author_id'
                    }],
                    'anchor_columns': [{'column_name': 'book_id'}],
                    'multi_value_schemas': {},
                    'external_ontology_schemas': {}
                }
            }
            
            viz_data = service.get_schema_visualization_data()
            
            assert 'nodes' in viz_data
            assert 'edges' in viz_data
            assert 'metadata' in viz_data
            
            assert len(viz_data['nodes']) == 2
            assert len(viz_data['edges']) == 1
            
            # Check node structure
            author_node = next(n for n in viz_data['nodes'] if n['id'] == 'authors')
            assert author_node['type'] == 'dataset'
            assert author_node['entity_type'] == 'Person'
            assert 'author_id' in author_node['properties']
            
            # Check edge structure
            edge = viz_data['edges'][0]
            assert edge['source'] == 'books'
            assert edge['target'] == 'authors'
            assert edge['type'] == 'foreign_key'
        
        logger.info("✅ Schema visualization data generation works")
    
    def test_export_schema_definition(self, mock_mapping_adapter):
        """Test exporting complete schema definition"""
        
        cache.clear()
        service = SchemaService(mapping_id="test_service_mapping_456")
        
        with patch('arkumu.importer.services.schema_service.CompleteSchemaProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor
            
            # Setup minimal blueprint
            mock_processor.dataset_blueprints = {
                "authors": {
                    'entity_type_resource': MagicMock(name='Person'),
                    'property_resources': {
                        'author_id': MagicMock(uri='http://test/prop/author_id', name='author_identifier')
                    },
                    'column_metadata': {'author_id': {'is_anchor': True}},
                    'fk_relationships': [],
                    'anchor_columns': [{'column_name': 'author_id'}],
                    'multi_value_schemas': {},
                    'external_ontology_schemas': {}
                }
            }
            
            export = service.export_schema_definition()
            
            assert export['mapping_id'] == "test_service_mapping_456"
            assert 'datasets' in export
            assert 'authors' in export['datasets']
            assert export['datasets']['authors']['entity_type'] == 'Person'
            assert 'exported_at' in export
        
        logger.info("✅ Schema export generates complete definition")