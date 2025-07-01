"""
Tests for ConfigTranslator
"""

import pytest
from unittest.mock import patch
from arkumu.importer.services.mapping_consumer.config_translator import (
    ConfigTranslator,
    ExecutionConfig,
    ColumnConfig,
    ColumnType,
    ProcessingStrategy,
    FKRelationship,
    RelationshipContext
)


@pytest.fixture
def config_translator():
    """ConfigTranslator instance for testing."""
    return ConfigTranslator()


@pytest.fixture
def sample_mapping_config():
    """Sample mapping configuration from GUI."""
    return {
        '_metadata': {
            'mapping_id': 123,
            'mapping_name': 'Test Mapping',
            'organization': 'Test Org'
        },
        'version': '1.1',
        'selected_datasets': ['people', 'departments'],
        'workspace_columns': {
            'people': {
                'name': {
                    'arkumu_type': 'person_name',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'confidence': 0.95
                },
                'age': {
                    'arkumu_type': 'person_age',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#int',
                    'is_anchor': False
                },
                'tags': {
                    'arkumu_type': 'person_tags',
                    'is_multi_value': True,
                    'multi_value_separator': ',',
                    'confidence': 0.8
                },
                'department_id': {
                    'arkumu_type': 'works_in',
                    'is_foreign_key': True
                }
            },
            'departments': {
                'name': {
                    'arkumu_type': 'department_name',
                    'is_anchor': True
                },
                'budget': {
                    'arkumu_type': 'department_budget',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#decimal'
                }
            },
            'excluded_dataset': {
                'col1': {
                    'arkumu_type': 'test_type'
                }
            }
        },
        'fk_relationships': {
            'people_to_departments': {
                'source_column': 'department_id',
                'source_dataset': 'people',
                'target_column': 'name',
                'target_dataset': 'departments',
                'relationship_type': 'works_in',
                'direction': 'outgoing',
                'confidence': 0.9
            }
        },
        'relationship_contexts': {
            'person_project_context': {
                'context_id': 'person_project_context',
                'primary_fk': 'person_id',
                'secondary_fk': 'project_id',
                'context_columns': ['role', 'start_date'],
                'context_type': 'employment',
                'dataset_name': 'assignments'
            }
        },
        'external_ontologies': {
            'orcid_mapping': {
                'column_name': 'orcid_id',
                'dataset_name': 'people',
                'ontology_type': 'orcid',
                'uri_template': 'https://orcid.org/{identifier}',
                'validation_enabled': True
            }
        },
        'import_strategy': {
            'processing_strategy': 'entity_centric',
            'chunk_size': 1000,
            'parallel_processing': False
        }
    }


@pytest.fixture
def minimal_mapping_config():
    """Minimal mapping configuration."""
    return {
        'selected_datasets': ['people'],
        'workspace_columns': {
            'people': {
                'name': {
                    'arkumu_type': 'person_name'
                }
            }
        }
    }


class TestConfigTranslator:
    """Test ConfigTranslator functionality."""
    
    def test_initialization(self, config_translator):
        """Test ConfigTranslator initializes correctly."""
        assert config_translator is not None
    
    @patch('arkumu.importer.services.mapping_consumer.config_translator.logger')
    def test_translate_mapping_config_complete(self, mock_logger, config_translator, sample_mapping_config):
        """Test complete mapping configuration translation."""
        result = config_translator.translate_mapping_config(sample_mapping_config)
        
        # Check metadata
        assert result.mapping_id == 123
        assert result.mapping_name == 'Test Mapping'
        assert result.organization == 'Test Org'
        assert result.version == '1.1'
        
        # Check column configurations (people: name, age, tags, department_id + departments: name, budget = 6)
        assert len(result.column_configurations) == 6
        
        # Check people.name column
        people_name = result.column_configurations.get('people.name')
        assert people_name is not None
        assert people_name.column_name == 'name'
        assert people_name.dataset_name == 'people'
        assert people_name.arkumu_type == 'person_name'
        assert people_name.is_anchor is True
        assert people_name.column_type == ColumnType.ANCHOR
        assert people_name.confidence == 0.95
        
        # Check people.tags (multi-value)
        people_tags = result.column_configurations.get('people.tags')
        assert people_tags is not None
        assert people_tags.is_multi_value is True
        assert people_tags.multi_value_separator == ','
        assert people_tags.column_type == ColumnType.MULTI_VALUE
        
        # Check FK relationships
        assert len(result.fk_relationships) == 1
        fk_rel = result.fk_relationships[0]
        assert fk_rel.source_column == 'department_id'
        assert fk_rel.source_dataset == 'people'
        assert fk_rel.target_column == 'name'
        assert fk_rel.target_dataset == 'departments'
        assert fk_rel.relationship_type == 'works_in'
        assert fk_rel.confidence == 0.9
        
        # Check relationship contexts
        assert len(result.relationship_contexts) == 1
        rel_context = result.relationship_contexts[0]
        assert rel_context.context_id == 'person_project_context'
        assert rel_context.primary_fk == 'person_id'
        assert rel_context.secondary_fk == 'project_id'
        assert rel_context.context_columns == ['role', 'start_date']
        assert rel_context.dataset_name == 'assignments'
        
        # Check external ontologies
        assert len(result.external_ontologies) == 1
        ext_ont = result.external_ontologies[0]
        assert ext_ont.column_name == 'orcid_id'
        assert ext_ont.dataset_name == 'people'
        assert ext_ont.ontology_type == 'orcid'
        assert ext_ont.uri_template == 'https://orcid.org/{identifier}'
        
        # Check datasets were built
        assert len(result.datasets) == 2
        
        # Check log message
        mock_logger.info.assert_called_once()
    
    def test_translate_mapping_config_minimal(self, config_translator, minimal_mapping_config):
        """Test minimal mapping configuration translation."""
        result = config_translator.translate_mapping_config(minimal_mapping_config)
        
        # Check defaults
        assert result.mapping_id == 0
        assert result.mapping_name == 'Unknown'
        assert result.organization == 'Unknown'
        assert result.version == '1.1'
        
        # Check column configuration
        assert len(result.column_configurations) == 1
        people_name = result.column_configurations.get('people.name')
        assert people_name is not None
        assert people_name.column_type == ColumnType.REGULAR
        assert people_name.datatype == 'http://www.w3.org/2001/XMLSchema#string'
        
        # Check empty collections
        assert len(result.fk_relationships) == 0
        assert len(result.relationship_contexts) == 0
        assert len(result.external_ontologies) == 0
    
    @patch('arkumu.importer.services.mapping_consumer.config_translator.logger')
    def test_translate_workspace_columns_skips_unselected_datasets(self, mock_logger, config_translator):
        """Test that unselected datasets are skipped."""
        mapping_config = {
            'selected_datasets': ['people'],  # Only people selected
            'workspace_columns': {
                'people': {
                    'name': {'arkumu_type': 'person_name'}
                },
                'departments': {  # Not selected
                    'name': {'arkumu_type': 'dept_name'}
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        # Should only have people columns
        assert len(result.column_configurations) == 1
        assert 'people.name' in result.column_configurations
        assert 'departments.name' not in result.column_configurations
        
        # Check debug log was called (may be multiple debug calls)
        mock_logger.debug.assert_called()
    
    def test_column_type_determination(self, config_translator):
        """Test column type determination logic."""
        mapping_config = {
            'selected_datasets': ['test'],
            'workspace_columns': {
                'test': {
                    'anchor_col': {
                        'arkumu_type': 'test_anchor',
                        'is_anchor': True
                    },
                    'multi_col': {
                        'arkumu_type': 'test_multi',
                        'is_multi_value': True
                    },
                    'external_col': {
                        'arkumu_type': 'test_external',
                        'is_external_ontology': True
                    },
                    'regular_col': {
                        'arkumu_type': 'test_regular'
                    }
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        assert result.column_configurations['test.anchor_col'].column_type == ColumnType.ANCHOR
        assert result.column_configurations['test.multi_col'].column_type == ColumnType.MULTI_VALUE
        assert result.column_configurations['test.external_col'].column_type == ColumnType.EXTERNAL_ONTOLOGY
        assert result.column_configurations['test.regular_col'].column_type == ColumnType.REGULAR
    
    def test_translate_fk_relationships(self, config_translator):
        """Test FK relationship translation."""
        mapping_config = {
            'selected_datasets': [],
            'workspace_columns': {},
            'fk_relationships': {
                'rel1': {
                    'source_column': 'src_col',
                    'source_dataset': 'src_dataset',
                    'target_column': 'tgt_col',
                    'target_dataset': 'tgt_dataset',
                    'relationship_type': 'relates_to',
                    'direction': 'incoming',
                    'is_multi_value': True,
                    'multi_value_separator': ';',
                    'confidence': 0.85
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        assert len(result.fk_relationships) == 1
        fk_rel = result.fk_relationships[0]
        assert fk_rel.source_column == 'src_col'
        assert fk_rel.source_dataset == 'src_dataset'
        assert fk_rel.target_column == 'tgt_col'
        assert fk_rel.target_dataset == 'tgt_dataset'
        assert fk_rel.relationship_type == 'relates_to'
        assert fk_rel.direction == 'incoming'
        assert fk_rel.is_multi_value is True
        assert fk_rel.multi_value_separator == ';'
        assert fk_rel.confidence == 0.85
    
    def test_translate_relationship_contexts(self, config_translator):
        """Test relationship context translation."""
        mapping_config = {
            'selected_datasets': [],
            'workspace_columns': {},
            'relationship_contexts': {
                'context1': {
                    'context_id': 'test_context',
                    'primary_fk': 'pk_col',
                    'secondary_fk': 'sk_col',
                    'context_columns': ['attr1', 'attr2'],
                    'context_type': 'junction',
                    'dataset_name': 'junction_table'
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        assert len(result.relationship_contexts) == 1
        rel_context = result.relationship_contexts[0]
        assert rel_context.context_id == 'context1'
        assert rel_context.primary_fk == 'pk_col'
        assert rel_context.secondary_fk == 'sk_col'
        assert rel_context.context_columns == ['attr1', 'attr2']
        assert rel_context.context_type == 'junction'
        assert rel_context.dataset_name == 'junction_table'
    
    def test_translate_external_ontologies(self, config_translator):
        """Test external ontology translation."""
        mapping_config = {
            'selected_datasets': [],
            'workspace_columns': {},
            'external_ontologies': {
                'ont1': {
                    'column_name': 'ext_col',
                    'dataset_name': 'ext_dataset',
                    'ontology_type': 'wikidata',
                    'uri_template': 'http://wikidata.org/{identifier}',
                    'identifier_column': 'id_col',
                    'validation_enabled': False
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        assert len(result.external_ontologies) == 1
        ext_ont = result.external_ontologies[0]
        assert ext_ont.column_name == 'ext_col'
        assert ext_ont.dataset_name == 'ext_dataset'
        assert ext_ont.ontology_type == 'wikidata'
        assert ext_ont.uri_template == 'http://wikidata.org/{identifier}'
        assert ext_ont.identifier_column == 'id_col'
        assert ext_ont.validation_enabled is False
    
    def test_translate_import_strategy(self, config_translator):
        """Test import strategy translation."""
        mapping_config = {
            'selected_datasets': [],
            'workspace_columns': {},
            'import_strategy': {
                'processing_strategy': 'multi_phase',
                'chunk_size': 2000,
                'parallel_processing': True,
                'custom_setting': 'value'
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        assert result.processing_strategy == ProcessingStrategy.MULTI_PHASE
        # Import strategy gets normalized to specific keys
        assert 'bulk_size' in result.import_strategy
        assert 'update_strategy' in result.import_strategy
        assert 'link_topology' in result.import_strategy
    
    def test_build_dataset_configurations(self, config_translator):
        """Test dataset configuration building."""
        mapping_config = {
            'selected_datasets': ['dataset1', 'dataset2'],
            'workspace_columns': {
                'dataset1': {
                    'col1': {'arkumu_type': 'type1', 'is_anchor': True},
                    'col2': {'arkumu_type': 'type2'}
                },
                'dataset2': {
                    'col3': {'arkumu_type': 'type3'}
                }
            }
        }
        
        result = config_translator.translate_mapping_config(mapping_config)
        
        # Should create 2 datasets
        assert len(result.datasets) == 2
        
        # Find datasets by name
        dataset1 = next((d for d in result.datasets if d.dataset_name == 'dataset1'), None)
        dataset2 = next((d for d in result.datasets if d.dataset_name == 'dataset2'), None)
        
        assert dataset1 is not None
        assert dataset2 is not None
        
        # Check dataset1 configuration
        assert len(dataset1.columns) == 2
        assert dataset1.primary_key_columns == ['col1']  # Anchor column
        
        # Check dataset2 configuration
        assert len(dataset2.columns) == 1
        assert dataset2.primary_key_columns == []  # No anchor columns
    
    def test_get_dataset_config(self, config_translator, sample_mapping_config):
        """Test ExecutionConfig.get_dataset_config method."""
        result = config_translator.translate_mapping_config(sample_mapping_config)
        
        people_config = result.get_dataset_config('people')
        assert people_config is not None
        assert people_config.dataset_name == 'people'
        
        nonexistent_config = result.get_dataset_config('nonexistent')
        assert nonexistent_config is None
    
    def test_get_column_config(self, config_translator, sample_mapping_config):
        """Test ExecutionConfig.get_column_config method."""
        result = config_translator.translate_mapping_config(sample_mapping_config)
        
        people_name_config = result.get_column_config('people', 'name')
        assert people_name_config is not None
        assert people_name_config.column_name == 'name'
        assert people_name_config.dataset_name == 'people'
        
        nonexistent_config = result.get_column_config('people', 'nonexistent')
        assert nonexistent_config is None
    
    def test_get_fk_relationships_for_dataset(self, config_translator, sample_mapping_config):
        """Test ExecutionConfig.get_fk_relationships_for_dataset method."""
        result = config_translator.translate_mapping_config(sample_mapping_config)
        
        people_fk_rels = result.get_fk_relationships_for_dataset('people')
        assert len(people_fk_rels) == 1
        assert people_fk_rels[0].source_dataset == 'people'
        
        departments_fk_rels = result.get_fk_relationships_for_dataset('departments')
        assert len(departments_fk_rels) == 1
        assert departments_fk_rels[0].target_dataset == 'departments'
        
        nonexistent_fk_rels = result.get_fk_relationships_for_dataset('nonexistent')
        assert len(nonexistent_fk_rels) == 0


class TestExecutionConfigMethods:
    """Test ExecutionConfig helper methods."""
    
    def test_execution_config_creation_with_defaults(self):
        """Test ExecutionConfig creation with default values."""
        config = ExecutionConfig(
            mapping_id=1,
            mapping_name="test",
            organization="test_org"
        )
        
        assert config.mapping_id == 1
        assert config.mapping_name == "test"
        assert config.organization == "test_org"
        assert config.version == "1.1"
        assert config.processing_strategy == ProcessingStrategy.AUTO
        assert len(config.datasets) == 0
        assert len(config.column_configurations) == 0
        assert len(config.fk_relationships) == 0
        assert len(config.relationship_contexts) == 0
        assert len(config.external_ontologies) == 0
        assert len(config.processing_phases) == 0
        assert config.estimated_complexity == "medium"
        assert len(config.import_strategy) == 0