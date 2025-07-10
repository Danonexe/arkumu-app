"""
Unit tests for RelationshipValidator component.

Tests FK relationships, relationship contexts (junction tables), 
join requirements, and dependency order validation.
"""

import pytest
from typing import List, Dict

from arkumu.importer.services.mapping_correlation.relationship_validator import RelationshipValidator
from arkumu.importer.services.mapping_correlation.data_models import FileAnalysis


class TestRelationshipValidator:
    """Test suite for RelationshipValidator"""
    
    @pytest.fixture
    def validator(self):
        """Create a RelationshipValidator instance"""
        return RelationshipValidator()
    
    @pytest.fixture
    def sample_file_analyses(self) -> List[FileAnalysis]:
        """Create sample file analyses for testing"""
        return [
            FileAnalysis(
                file_path="/data/customers.csv",
                file_name="customers",
                column_count=5,
                row_count=100,
                columns=["id", "name", "email", "created_at", "status"],
                column_types={"id": "integer", "name": "string", "email": "string", 
                            "created_at": "datetime", "status": "string"},
                matched_dataset_name="customers"
            ),
            FileAnalysis(
                file_path="/data/orders.csv",
                file_name="orders",
                column_count=6,
                row_count=500,
                columns=["id", "customer_id", "order_date", "total", "status", "notes"],
                column_types={"id": "integer", "customer_id": "integer", 
                            "order_date": "datetime", "total": "float", 
                            "status": "string", "notes": "string"},
                matched_dataset_name="orders"
            ),
            FileAnalysis(
                file_path="/data/products.csv",
                file_name="products",
                column_count=4,
                row_count=50,
                columns=["id", "name", "price", "category"],
                column_types={"id": "integer", "name": "string", 
                            "price": "float", "category": "string"},
                matched_dataset_name="products"
            ),
            FileAnalysis(
                file_path="/data/order_items.csv",
                file_name="order_items",
                column_count=5,
                row_count=1500,
                columns=["order_id", "product_id", "quantity", "unit_price", "discount"],
                column_types={"order_id": "integer", "product_id": "integer",
                            "quantity": "integer", "unit_price": "float", 
                            "discount": "float"},
                matched_dataset_name="order_items"
            )
        ]
    
    def test_validate_fk_relationships_all_valid(self, validator, sample_file_analyses):
        """Test FK validation when all relationships are valid"""
        fk_rels = [
            {
                'id': 'fk_1',
                'source_dataset': 'orders',
                'source_column': 'customer_id',
                'target_dataset': 'customers',
                'target_column': 'id',
                'relationship_type': 'references'
            },
            {
                'id': 'fk_2',
                'source_dataset': 'order_items',
                'source_column': 'order_id',
                'target_dataset': 'orders',
                'target_column': 'id',
                'relationship_type': 'references'
            }
        ]
        
        result = validator.validate_fk_relationships(fk_rels, sample_file_analyses)
        
        assert result['valid'] is True
        assert len(result['issues']) == 0
    
    def test_validate_fk_relationships_missing_column(self, validator, sample_file_analyses):
        """Test FK validation when source column is missing"""
        fk_rels = [
            {
                'id': 'fk_invalid',
                'source_dataset': 'orders',
                'source_column': 'user_id',  # This column doesn't exist
                'target_dataset': 'customers',
                'target_column': 'id',
                'relationship_type': 'references'
            }
        ]
        
        result = validator.validate_fk_relationships(fk_rels, sample_file_analyses)
        
        assert result['valid'] is False
        assert len(result['issues']) == 1
        assert result['issues'][0]['type'] == 'missing_fk_column'
        assert result['issues'][0]['dataset'] == 'orders'
        assert result['issues'][0]['column'] == 'user_id'
    
    def test_validate_fk_relationships_missing_target_dataset(self, validator, sample_file_analyses):
        """Test FK validation when target dataset is missing"""
        fk_rels = [
            {
                'id': 'fk_invalid',
                'source_dataset': 'orders',
                'source_column': 'customer_id',
                'target_dataset': 'users',  # This dataset doesn't exist
                'target_column': 'id',
                'relationship_type': 'references'
            }
        ]
        
        result = validator.validate_fk_relationships(fk_rels, sample_file_analyses)
        
        assert result['valid'] is False
        assert len(result['issues']) == 1
        assert result['issues'][0]['type'] == 'missing_target_dataset'
        assert result['issues'][0]['dataset'] == 'users'
    
    def test_validate_relationship_contexts_valid(self, validator, sample_file_analyses):
        """Test relationship context validation with valid junction table"""
        contexts = [
            {
                'context_id': 'ctx_1',
                'dataset': 'order_items',
                'primary_fk': 'order_id',
                'secondary_fk': 'product_id',
                'context_columns': ['quantity', 'unit_price'],
                'context_type': 'junction'
            }
        ]
        
        result = validator.validate_relationship_contexts(contexts, sample_file_analyses)
        
        assert result['valid'] is True
        assert len(result['issues']) == 0
    
    def test_validate_relationship_contexts_missing_fks(self, validator, sample_file_analyses):
        """Test relationship context validation with missing FK columns"""
        contexts = [
            {
                'context_id': 'ctx_invalid',
                'dataset': 'order_items',
                'primary_fk': 'order_id',
                'secondary_fk': 'item_id',  # This column doesn't exist
                'context_columns': ['quantity'],
                'context_type': 'junction'
            }
        ]
        
        result = validator.validate_relationship_contexts(contexts, sample_file_analyses)
        
        assert result['valid'] is False
        assert len(result['issues']) == 1
        assert result['issues'][0]['type'] == 'missing_junction_fks'
        assert 'item_id' in result['issues'][0]['missing_fks']
    
    def test_validate_join_requirements(self, validator, sample_file_analyses):
        """Test join requirement validation"""
        relationships = [
            {
                'from_column': 'orders.customer_id',
                'to_column': 'customers.id',
                'relationship_type': 'P7',
                'description': 'Order placed by customer'
            },
            {
                'from_column': 'products.category',
                'to_column': 'categories.name',  # categories dataset doesn't exist
                'relationship_type': 'P2',
                'description': 'Product belongs to category'
            }
        ]
        
        result = validator.validate_join_requirements(relationships, sample_file_analyses)
        
        assert result['valid'] is False
        assert len(result['issues']) == 1
        assert result['issues'][0]['type'] == 'missing_join_dataset'
        assert result['issues'][0]['dataset'] == 'categories'
    
    def test_validate_dependency_order_no_cycles(self, validator, sample_file_analyses):
        """Test dependency order validation with no cycles"""
        fk_rels = [
            {
                'id': 'fk_1',
                'source_dataset': 'orders',
                'source_column': 'customer_id',
                'target_dataset': 'customers',
                'target_column': 'id'
            },
            {
                'id': 'fk_2',
                'source_dataset': 'order_items',
                'source_column': 'order_id',
                'target_dataset': 'orders',
                'target_column': 'id'
            },
            {
                'id': 'fk_3',
                'source_dataset': 'order_items',
                'source_column': 'product_id',
                'target_dataset': 'products',
                'target_column': 'id'
            }
        ]
        
        result = validator.validate_dependency_order(sample_file_analyses, fk_rels)
        
        assert result['valid'] is True
        assert result['has_cycles'] is False
        assert len(result['processing_order']) > 0
        # Verify processing order: customers and products should come before orders
        order_idx = {ds: i for i, ds in enumerate(result['processing_order'])}
        if 'orders' in order_idx and 'customers' in order_idx:
            assert order_idx['customers'] < order_idx['orders']
    
    def test_validate_dependency_order_with_cycle(self, validator, sample_file_analyses):
        """Test dependency order validation with circular dependency"""
        fk_rels = [
            {
                'id': 'fk_1',
                'source_dataset': 'orders',
                'source_column': 'customer_id',
                'target_dataset': 'customers',
                'target_column': 'id'
            },
            {
                'id': 'fk_2',
                'source_dataset': 'customers',
                'source_column': 'last_order_id',
                'target_dataset': 'orders',
                'target_column': 'id'
            }
        ]
        
        result = validator.validate_dependency_order(sample_file_analyses, fk_rels)
        
        assert result['valid'] is False
        assert result['has_cycles'] is True
        assert len(result['cycle']) > 0
        # Cycle should contain both orders and customers
        assert 'orders' in result['cycle']
        assert 'customers' in result['cycle']
    
    def test_find_file_for_dataset(self, validator, sample_file_analyses):
        """Test internal helper method _find_file_for_dataset"""
        # Find existing dataset
        file_analysis = validator._find_file_for_dataset('customers', sample_file_analyses)
        assert file_analysis is not None
        assert file_analysis.matched_dataset_name == 'customers'
        
        # Try to find non-existent dataset
        file_analysis = validator._find_file_for_dataset('nonexistent', sample_file_analyses)
        assert file_analysis is None
    
    def test_multiple_fk_issues(self, validator, sample_file_analyses):
        """Test validation with multiple FK issues"""
        fk_rels = [
            {
                'id': 'fk_1',
                'source_dataset': 'orders',
                'source_column': 'user_id',  # Missing column
                'target_dataset': 'users',  # Missing dataset
                'target_column': 'id'
            },
            {
                'id': 'fk_2',
                'source_dataset': 'nonexistent',  # Missing source dataset
                'source_column': 'product_id',
                'target_dataset': 'products',
                'target_column': 'id'
            }
        ]
        
        result = validator.validate_fk_relationships(fk_rels, sample_file_analyses)
        
        assert result['valid'] is False
        assert len(result['issues']) >= 3  # At least 3 issues expected
        issue_types = {issue['type'] for issue in result['issues']}
        assert 'missing_fk_column' in issue_types
        assert 'missing_target_dataset' in issue_types
        assert 'missing_source_dataset' in issue_types