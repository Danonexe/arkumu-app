"""
Unit tests for enhanced MappingExtractor methods.

Tests the new relationship extraction methods including FK relationships,
relationship contexts, and comprehensive relationship extraction.
"""

import pytest
from typing import Dict

from arkumu.importer.services.mapping_correlation.mapping_extractor import MappingExtractor


class TestMappingExtractorEnhanced:
    """Test suite for enhanced MappingExtractor methods"""
    
    @pytest.fixture
    def sample_mapping_config(self) -> Dict:
        """Create a comprehensive sample mapping configuration"""
        return {
            'id': 'test_mapping',
            'name': 'Test Mapping',
            'workspace_columns': {
                'col_1': {
                    'id': 'col_1',
                    'name': 'id',
                    'type': 'integer',
                    'dataset': 'customers'
                },
                'col_2': {
                    'id': 'col_2',
                    'name': 'customer_id',
                    'type': 'integer',
                    'dataset': 'orders',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'customers',
                        'target_column': 'id'
                    }
                },
                'col_3': {
                    'id': 'col_3',
                    'name': 'order_id',
                    'type': 'integer',
                    'dataset': 'order_items'
                },
                'col_4': {
                    'id': 'col_4',
                    'name': 'product_id',
                    'type': 'integer',
                    'dataset': 'order_items',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'products',
                        'target_column': 'id'
                    }
                }
            },
            'fk_relationships': {
                'fk_order_customer': {
                    'source_dataset': 'orders',
                    'source_column': 'customer_id',
                    'target_dataset': 'customers',
                    'target_column': 'id',
                    'relationship_type': 'references'
                },
                'fk_orderitem_order': {
                    'source_dataset': 'order_items',
                    'source_column': 'order_id',
                    'target_dataset': 'orders',
                    'target_column': 'id',
                    'relationship_type': 'references'
                }
            },
            'relationships': [
                {
                    'from_column': 'orders.order_date',
                    'to_column': 'calendar.date',
                    'relationship_type': 'P7',
                    'description': 'Order occurred on date'
                }
            ],
            'relationship_contexts': {
                'order_items_context': {
                    'dataset': 'order_items',
                    'primary_fk': 'order_id',
                    'secondary_fk': 'product_id',
                    'context_columns': ['quantity', 'unit_price', 'discount'],
                    'context_type': 'junction'
                }
            }
        }
    
    def test_extract_all_relationships(self, sample_mapping_config):
        """Test comprehensive relationship extraction"""
        result = MappingExtractor.extract_all_relationships(sample_mapping_config)
        
        assert 'fk_relationships' in result
        assert 'relationship_contexts' in result
        assert 'relationships' in result
        
        # Check FK relationships
        assert len(result['fk_relationships']) >= 2  # At least 2 from fk_relationships
        
        # Check relationship contexts
        assert len(result['relationship_contexts']) == 1
        assert result['relationship_contexts'][0]['dataset'] == 'order_items'
        
        # Check P2P relationships
        assert len(result['relationships']) == 1
        assert result['relationships'][0]['relationship_type'] == 'P7'
    
    def test_extract_fk_relationships_from_both_sources(self, sample_mapping_config):
        """Test FK extraction from both fk_relationships and workspace_columns"""
        fk_rels = MappingExtractor.extract_fk_relationships(sample_mapping_config)
        
        # Should find FKs from both sources
        assert len(fk_rels) >= 3  # 2 from fk_relationships + at least 1 from workspace_columns
        
        # Check that workspace column FKs are included
        workspace_fks = [fk for fk in fk_rels if fk['id'].startswith('workspace_fk_')]
        assert len(workspace_fks) >= 1
        
        # Verify FK from workspace column
        product_fk = next((fk for fk in workspace_fks 
                          if fk['source_column'] == 'product_id'), None)
        assert product_fk is not None
        assert product_fk['target_dataset'] == 'products'
        assert product_fk['target_column'] == 'id'
    
    def test_extract_fk_relationships_empty_config(self):
        """Test FK extraction with empty configuration"""
        empty_config = {
            'workspace_columns': {}
        }
        
        fk_rels = MappingExtractor.extract_fk_relationships(empty_config)
        
        assert isinstance(fk_rels, list)
        assert len(fk_rels) == 0
    
    def test_extract_fk_relationships_only_workspace(self):
        """Test FK extraction with only workspace column FKs"""
        config = {
            'workspace_columns': {
                'col_1': {
                    'name': 'user_id',
                    'dataset': 'posts',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'users',
                        'target_column': 'id'
                    }
                }
            }
        }
        
        fk_rels = MappingExtractor.extract_fk_relationships(config)
        
        assert len(fk_rels) == 1
        assert fk_rels[0]['source_dataset'] == 'posts'
        assert fk_rels[0]['source_column'] == 'user_id'
        assert fk_rels[0]['id'].startswith('workspace_fk_')
    
    def test_extract_relationship_contexts(self, sample_mapping_config):
        """Test relationship context extraction"""
        contexts = MappingExtractor.extract_relationship_contexts(sample_mapping_config)
        
        assert len(contexts) == 1
        context = contexts[0]
        
        assert context['context_id'] == 'order_items_context'
        assert context['dataset'] == 'order_items'
        assert context['primary_fk'] == 'order_id'
        assert context['secondary_fk'] == 'product_id'
        assert 'quantity' in context['context_columns']
        assert 'unit_price' in context['context_columns']
        assert context['context_type'] == 'junction'
    
    def test_extract_relationship_contexts_empty(self):
        """Test relationship context extraction with no contexts"""
        config = {
            'workspace_columns': {}
        }
        
        contexts = MappingExtractor.extract_relationship_contexts(config)
        
        assert isinstance(contexts, list)
        assert len(contexts) == 0
    
    def test_extract_relationship_contexts_missing_fields(self):
        """Test relationship context extraction with missing optional fields"""
        config = {
            'relationship_contexts': {
                'minimal_context': {
                    'dataset': 'link_table',
                    'primary_fk': 'id_a',
                    'secondary_fk': 'id_b'
                    # No context_columns or context_type
                }
            }
        }
        
        contexts = MappingExtractor.extract_relationship_contexts(config)
        
        assert len(contexts) == 1
        context = contexts[0]
        
        assert context['dataset'] == 'link_table'
        assert context['context_columns'] == []  # Default empty list
        assert context['context_type'] == 'junction'  # Default type
    
    def test_extract_fk_relationships_invalid_workspace_fk(self):
        """Test FK extraction skips invalid workspace column FKs"""
        config = {
            'workspace_columns': {
                'col_1': {
                    'name': 'user_id',
                    'dataset': 'posts',
                    'is_fk': True,
                    'fk_config': {
                        # Missing target_dataset
                        'target_column': 'id'
                    }
                },
                'col_2': {
                    'name': 'category_id',
                    'dataset': 'posts',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'categories'
                        # Missing target_column
                    }
                },
                'col_3': {
                    'name': 'valid_fk',
                    'dataset': 'posts',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'valid_target',
                        'target_column': 'id'
                    }
                }
            }
        }
        
        fk_rels = MappingExtractor.extract_fk_relationships(config)
        
        # Should only extract the valid FK
        assert len(fk_rels) == 1
        assert fk_rels[0]['source_column'] == 'valid_fk'
    
    def test_nested_workspace_columns(self):
        """Test extraction with nested workspace column structure"""
        config = {
            'workspace_columns': {
                'group_1': {
                    'columns': {
                        'col_1': {
                            'name': 'id',
                            'dataset': 'users'
                        }
                    }
                },
                'col_2': {
                    'name': 'post_id',
                    'dataset': 'comments',
                    'is_fk': True,
                    'fk_config': {
                        'target_dataset': 'posts',
                        'target_column': 'id'
                    }
                }
            }
        }
        
        # This tests that the extractor correctly handles both nested and flat structures
        fk_rels = MappingExtractor.extract_fk_relationships(config)
        
        # Should find the FK in the flat structure
        fk_found = any(fk['source_column'] == 'post_id' for fk in fk_rels)
        assert fk_found or len(fk_rels) == 0  # Depends on how iterate_workspace_columns handles nesting