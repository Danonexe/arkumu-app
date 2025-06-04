"""
Test suite for Reference Resolution Service

Tests entity registration, reference resolution strategies, and registry management.
"""

import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, List, Any

# Import the classes to test
from arkumu.metadata.services.metadata_models_mapping.reference_resolution import (
    ReferenceResolutionService,
    ResolutionStrategy,
    ResolutionStatus,
    ResolutionCandidate,
    ResolutionResult,
    EntityRegistry
)


class TestReferenceResolutionService:
    
    @pytest.fixture
    def service(self):
        """Create a fresh service instance for each test"""
        return ReferenceResolutionService()
    
    @pytest.fixture
    def sample_entities(self):
        """Sample entities for testing"""
        return {
            'user_1': {
                'name': 'John Doe',
                'email': 'john.doe@example.com',
                'type': 'user',
                'source_value': 'user_1'
            },
            'user_2': {
                'name': 'Jane Smith',
                'email': 'jane.smith@example.com',
                'type': 'user',
                'source_value': 'user_2'
            },
            'product_100': {
                'title': 'Laptop Computer',
                'sku': 'LAPTOP-001',
                'type': 'product',
                'source_value': 'product_100'
            },
            'product_101': {
                'title': 'Desktop Computer',
                'sku': 'DESKTOP-001',
                'type': 'product',
                'source_value': 'product_101'
            }
        }
    
    def test_init(self):
        """Test service initialization"""
        service = ReferenceResolutionService()
        
        assert isinstance(service.entity_registry, EntityRegistry)
        assert service.entity_registry.entities == {}
        assert service.entity_registry.indices == {}
        assert service.entity_registry.datasets == {}
        assert len(service._resolution_strategies) == 4
    
    def test_register_entities_from_dataset(self, service, sample_entities):
        """Test entity registration from dataset"""
        dataset_path = "/path/to/dataset.csv"
        
        # Register entities
        count = service.register_entities_from_dataset(
            dataset_path=dataset_path,
            entities=sample_entities,
            indexable_fields=['name', 'title', 'source_value']
        )
        
        # Verify registration count
        assert count == 4
        
        # Verify entities are registered
        assert len(service.entity_registry.entities) == 4
        assert 'user_1' in service.entity_registry.entities
        assert service.entity_registry.entities['user_1']['name'] == 'John Doe'
        
        # Verify dataset mapping
        assert service.entity_registry.datasets['user_1'] == dataset_path
        
        # Verify indices are created
        assert 'name' in service.entity_registry.indices
        assert 'john doe' in service.entity_registry.indices['name']
        assert 'user_1' in service.entity_registry.indices['name']['john doe']
    
    def test_register_entities_default_indexable_fields(self, service, sample_entities):
        """Test entity registration with default indexable fields"""
        count = service.register_entities_from_dataset(
            dataset_path="/test/path",
            entities=sample_entities
        )
        
        assert count == 4
        # Should create indices for default fields
        expected_fields = ['source_value', 'name', 'title', 'label']
        for field in expected_fields:
            if any(field in entity for entity in sample_entities.values()):
                assert field in service.entity_registry.indices
    
    def test_resolve_reference_exact_match_found(self, service, sample_entities):
        """Test exact match resolution - successful case"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        result = service.resolve_reference(
            source_value="John Doe",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_entity_id == 'user_1'
        assert result.confidence_score == 1.0
        assert result.resolution_method == 'exact_match'
        assert len(result.candidates) == 1
        assert result.candidates[0].confidence_score == 1.0
    
    def test_resolve_reference_exact_match_not_found(self, service, sample_entities):
        """Test exact match resolution - not found case"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        result = service.resolve_reference(
            source_value="Nonexistent User",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.UNRESOLVED
        assert result.resolved_entity_id is None
        assert result.confidence_score == 0.0
        assert len(result.candidates) == 0
    
    def test_resolve_reference_exact_match_ambiguous(self, service):
        """Test exact match resolution - ambiguous case"""
        # Create entities with same name
        entities = {
            'user_1': {'name': 'John Doe', 'type': 'user'},
            'admin_1': {'name': 'John Doe', 'type': 'admin'}
        }
        service.register_entities_from_dataset("/test", entities)
        
        result = service.resolve_reference(
            source_value="John Doe",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.AMBIGUOUS
        assert result.resolved_entity_id in ['user_1', 'admin_1']
        assert result.confidence_score == 1.0
        assert len(result.candidates) == 2
    
    def test_resolve_reference_with_entity_type_filter(self, service, sample_entities):
        """Test resolution with entity type filtering"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        result = service.resolve_reference(
            source_value="John Doe",
            target_entity_type="user",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_entity_id == 'user_1'
        
        # Test with wrong entity type
        result = service.resolve_reference(
            source_value="John Doe",
            target_entity_type="product",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.UNRESOLVED
    
    def test_resolve_reference_confidence_threshold(self, service, sample_entities):
        """Test resolution with confidence threshold"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        # Test with high threshold that excludes matches
        result = service.resolve_reference(
            source_value="John Doe",
            strategy=ResolutionStrategy.EXACT_MATCH,
            confidence_threshold=1.1  # Impossible threshold
        )
        
        assert result.status == ResolutionStatus.UNRESOLVED
        assert len(result.candidates) == 1  # Candidate exists but below threshold
    
    @patch('arkumu.metadata.services.metadata_models_mapping.reference_resolution.logger')
    def test_resolve_reference_error_handling(self, mock_logger, service):
        """Test resolution error handling"""
        # Mock an error in strategy resolution
        service._resolution_strategies[ResolutionStrategy.EXACT_MATCH] = MagicMock(
            side_effect=Exception("Test error")
        )
        
        result = service.resolve_reference(
            source_value="test",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.ERROR
        assert result.resolved_entity_id is None
        assert result.confidence_score == 0.0
        assert 'error' in result.metadata
        mock_logger.error.assert_called_once()
    
    def test_fuzzy_match_resolution(self, service, sample_entities):
        """Test fuzzy matching strategy"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        # Test similar but not exact match
        result = service.resolve_reference(
            source_value="Jon Doe",  # Typo in "John"
            strategy=ResolutionStrategy.FUZZY_MATCH
        )
        
        assert len(result.candidates) > 0
        # Should find John Doe with reasonable confidence
        best_candidate = max(result.candidates, key=lambda c: c.confidence_score)
        assert best_candidate.entity_id == 'user_1'
        assert best_candidate.confidence_score > 0.6
        assert best_candidate.match_method == 'fuzzy_match'
    
    def test_fuzzy_match_no_similar_matches(self, service, sample_entities):
        """Test fuzzy matching with no similar matches"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        result = service.resolve_reference(
            source_value="Completely Different Name",
            strategy=ResolutionStrategy.FUZZY_MATCH
        )
        
        # Should return empty or very low confidence candidates
        assert all(c.confidence_score < 0.6 for c in result.candidates)
    
    def test_pattern_match_resolution(self, service):
        """Test pattern matching strategy"""
        entities = {
            'USER_123': {'source_value': 'USER_123', 'type': 'user'},
            'PROD_456': {'source_value': 'PROD_456', 'type': 'product'},
            '789': {'source_value': '789', 'type': 'simple_id'}
        }
        service.register_entities_from_dataset("/test", entities)
        
        # Test pattern matching
        result = service.resolve_reference(
            source_value="USER_123",
            strategy=ResolutionStrategy.PATTERN_MATCH
        )
        
        # Should find exact pattern match
        assert len(result.candidates) > 0
        best_candidate = result.candidates[0]
        assert best_candidate.entity_id == 'USER_123'
        assert best_candidate.confidence_score > 0.7
    
    def test_semantic_match_resolution(self, service, sample_entities):
        """Test semantic matching strategy (placeholder)"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        result = service.resolve_reference(
            source_value="John Doe",
            strategy=ResolutionStrategy.SEMANTIC_MATCH
        )
        
        # Currently returns empty list (placeholder implementation)
        assert len(result.candidates) == 0
    
    def test_bulk_resolve_references(self, service, sample_entities):
        """Test bulk reference resolution"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        references = [
            ("John Doe", "user"),
            ("Jane Smith", "user"),
            ("Laptop Computer", "product"),
            ("Nonexistent", None)
        ]
        
        results = service.bulk_resolve_references(
            references=references,
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert len(results) == 4
        assert results["John Doe"].status == ResolutionStatus.RESOLVED
        assert results["Jane Smith"].status == ResolutionStatus.RESOLVED
        assert results["Laptop Computer"].status == ResolutionStatus.RESOLVED
        assert results["Nonexistent"].status == ResolutionStatus.UNRESOLVED
    
    def test_get_resolution_statistics(self, service, sample_entities):
        """Test resolution statistics"""
        service.register_entities_from_dataset("/test/dataset1", sample_entities)
        
        # Add more entities from different dataset
        more_entities = {
            'order_1': {'source_value': 'order_1', 'type': 'order'},
            'order_2': {'source_value': 'order_2', 'type': 'order'}
        }
        service.register_entities_from_dataset("/test/dataset2", more_entities)
        
        stats = service.get_resolution_statistics()
        
        assert stats['total_entities'] == 6
        assert stats['entities_by_type']['user'] == 2
        assert stats['entities_by_type']['product'] == 2
        assert stats['entities_by_type']['order'] == 2
        assert stats['entities_by_dataset']['/test/dataset1'] == 4
        assert stats['entities_by_dataset']['/test/dataset2'] == 2
        assert 'source_value' in stats['indexed_fields']
    
    def test_clear_registry(self, service, sample_entities):
        """Test clearing the entity registry"""
        service.register_entities_from_dataset("/test", sample_entities)
        
        # Verify entities are registered
        assert len(service.entity_registry.entities) == 4
        
        # Clear registry
        service.clear_registry()
        
        # Verify registry is empty
        assert len(service.entity_registry.entities) == 0
        assert len(service.entity_registry.indices) == 0
        assert len(service.entity_registry.datasets) == 0
    
    def test_export_import_registry(self, service, sample_entities):
        """Test exporting and importing registry"""
        # Register entities
        service.register_entities_from_dataset("/test", sample_entities)
        
        # Export registry
        exported_data = service.export_registry()
        
        assert 'entities' in exported_data
        assert 'datasets' in exported_data
        assert len(exported_data['entities']) == 4
        
        # Clear and import
        service.clear_registry()
        service.import_registry(exported_data)
        
        # Verify import
        assert len(service.entity_registry.entities) == 4
        assert 'user_1' in service.entity_registry.entities
        # Indices should be rebuilt
        assert len(service.entity_registry.indices) > 0
    
    def test_import_registry_without_rebuild_indices(self, service, sample_entities):
        """Test importing registry without rebuilding indices"""
        service.register_entities_from_dataset("/test", sample_entities)
        exported_data = service.export_registry()
        
        service.clear_registry()
        service.import_registry(exported_data, rebuild_indices=False)
        
        # Entities should be imported but indices should be empty
        assert len(service.entity_registry.entities) == 4
        assert len(service.entity_registry.indices) == 0
    
    def test_rebuild_indices(self, service, sample_entities):
        """Test rebuilding indices"""
        # Manually add entities without indices
        service.entity_registry.entities = sample_entities
        service.entity_registry.datasets = {eid: "/test" for eid in sample_entities.keys()}
        
        # Verify no indices
        assert len(service.entity_registry.indices) == 0
        
        # Rebuild indices
        service._rebuild_indices()
        
        # Verify indices are created
        assert len(service.entity_registry.indices) > 0
        assert 'name' in service.entity_registry.indices
        assert 'john doe' in service.entity_registry.indices['name']
    
    def test_extract_id_components(self, service):
        """Test ID component extraction"""
        patterns = [r'^(\d+)$', r'^[A-Z]+_(\d+)$']
        
        # Test numeric ID
        components = service._extract_id_components("123", patterns)
        assert components['full_value'] == "123"
        assert components['numeric_part'] == "123"
        
        # Test prefixed ID
        components = service._extract_id_components("USER_456", patterns)
        assert components['full_value'] == "USER_456"
        assert components['numeric_part'] == "456"
        
        # Test non-matching pattern
        components = service._extract_id_components("random_text", patterns)
        assert components['full_value'] == "random_text"
        assert 'numeric_part' not in components
    
    def test_calculate_pattern_match_score(self, service):
        """Test pattern match score calculation"""
        # Exact match
        comp1 = {'full_value': 'USER_123'}
        comp2 = {'full_value': 'USER_123'}
        score = service._calculate_pattern_match_score(comp1, comp2)
        assert score == 1.0
        
        # Pattern and numeric match
        comp1 = {'full_value': 'USER_123', 'pattern': r'^[A-Z]+_(\d+)$', 'numeric_part': '123'}
        comp2 = {'full_value': 'USER_456', 'pattern': r'^[A-Z]+_(\d+)$', 'numeric_part': '123'}
        score = service._calculate_pattern_match_score(comp1, comp2)
        assert score == 1.0  # Pattern match (0.5) + numeric match (0.5)
        
        # Only pattern match
        comp2 = {'full_value': 'USER_789', 'pattern': r'^[A-Z]+_(\d+)$', 'numeric_part': '789'}
        score = service._calculate_pattern_match_score(comp1, comp2)
        assert score == 0.5  # Only pattern match
        
        # No match
        comp1 = {'full_value': 'USER_123'}
        comp2 = {'full_value': 'PROD_456'}
        score = service._calculate_pattern_match_score(comp1, comp2)
        assert score == 0.0


class TestResolutionDataClasses:
    """Test the dataclass structures"""
    
    def test_resolution_candidate(self):
        """Test ResolutionCandidate dataclass"""
        candidate = ResolutionCandidate(
            entity_id="test_id",
            entity_data={"name": "Test"},
            confidence_score=0.95,
            match_method="exact_match",
            match_details={"field": "name"}
        )
        
        assert candidate.entity_id == "test_id"
        assert candidate.confidence_score == 0.95
        assert candidate.match_method == "exact_match"
    
    def test_resolution_result(self):
        """Test ResolutionResult dataclass"""
        result = ResolutionResult(
            source_value="test_value",
            status=ResolutionStatus.RESOLVED,
            resolved_entity_id="entity_1",
            candidates=[],
            confidence_score=0.9,
            resolution_method="exact_match",
            metadata={"test": "data"}
        )
        
        assert result.source_value == "test_value"
        assert result.status == ResolutionStatus.RESOLVED
        assert result.confidence_score == 0.9
    
    def test_entity_registry(self):
        """Test EntityRegistry dataclass"""
        registry = EntityRegistry(
            entities={"id1": {"name": "test"}},
            indices={"name": {"test": ["id1"]}},
            datasets={"id1": "/path/to/dataset"}
        )
        
        assert "id1" in registry.entities
        assert "name" in registry.indices
        assert registry.datasets["id1"] == "/path/to/dataset"


class TestResolutionEnums:
    """Test the enum classes"""
    
    def test_resolution_strategy_enum(self):
        """Test ResolutionStrategy enum values"""
        assert ResolutionStrategy.EXACT_MATCH.value == "exact_match"
        assert ResolutionStrategy.FUZZY_MATCH.value == "fuzzy_match"
        assert ResolutionStrategy.PATTERN_MATCH.value == "pattern_match"
        assert ResolutionStrategy.SEMANTIC_MATCH.value == "semantic_match"
    
    def test_resolution_status_enum(self):
        """Test ResolutionStatus enum values"""
        assert ResolutionStatus.RESOLVED.value == "resolved"
        assert ResolutionStatus.UNRESOLVED.value == "unresolved"
        assert ResolutionStatus.AMBIGUOUS.value == "ambiguous"
        assert ResolutionStatus.ERROR.value == "error"


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_empty_source_value(self):
        """Test resolution with empty source value"""
        service = ReferenceResolutionService()
        
        result = service.resolve_reference(
            source_value="",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.UNRESOLVED
    
    def test_none_source_value(self):
        """Test resolution with None source value"""
        service = ReferenceResolutionService()
        
        result = service.resolve_reference(
            source_value=None,
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        # Should handle None gracefully (converted to string)
        assert result.source_value is None
    
    def test_unknown_resolution_strategy(self):
        """Test with unknown resolution strategy"""
        service = ReferenceResolutionService()
        
        # Remove a strategy to simulate unknown strategy
        del service._resolution_strategies[ResolutionStrategy.EXACT_MATCH]
        
        result = service.resolve_reference(
            source_value="test",
            strategy=ResolutionStrategy.EXACT_MATCH
        )
        
        assert result.status == ResolutionStatus.ERROR
        assert "Unknown resolution strategy" in result.metadata.get('error', '')
    
    def test_register_empty_entities(self):
        """Test registering empty entities dictionary"""
        service = ReferenceResolutionService()
        
        count = service.register_entities_from_dataset("/test", {})
        
        assert count == 0
        assert len(service.entity_registry.entities) == 0
    
    def test_entities_with_missing_fields(self):
        """Test entities with missing indexable fields"""
        service = ReferenceResolutionService()
        entities = {
            'entity_1': {'description': 'Has no name or title'},
            'entity_2': {'name': 'Has name', 'title': None},  # None value
            'entity_3': {'name': '', 'title': 'Has title'}    # Empty string
        }
        
        count = service.register_entities_from_dataset("/test", entities)
        
        assert count == 3
        # Only entities with non-empty values should be indexed
        assert len(service.entity_registry.indices.get('name', {})) == 1  # Only entity_2
        assert len(service.entity_registry.indices.get('title', {})) == 1  # Only entity_3


