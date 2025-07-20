"""
Test Blueprint Caching Functionality

This test validates that the blueprint caching system works correctly with real production data
while maintaining proper test isolation.
"""
import pytest
import logging
from django.core.cache import cache

from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics
from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy
from arkumu.metadata.models import Resource

logger = logging.getLogger(__name__)


class TestBlueprintCaching:
    """Test blueprint caching functionality with real production data"""
    
    def setup_method(self):
        """Setup test environment"""
        self.mapping_adapter = MappingAdapter()
        self.statistics = ExecutionStatistics()
        self.execution_config = None
    
    def load_production_test_mapping(self, mapping):
        """Load the mapping from test database using the automated system"""
        if self.execution_config is not None:
            return self.execution_config
            
        try:
            # Ensure we're working with a mapping from the test database
            if not mapping.pk:
                raise AssertionError("Mapping must be saved in test database before loading")
                
            logger.info(f"Loading test mapping: ID={mapping.id}, Name={mapping.name} from test database")
            
            # Use the mapping adapter to handle everything automatically
            self.execution_config = self.mapping_adapter.translate_to_execution_config(mapping.id)
            
            logger.info(f"Loaded and translated mapping with {len(self.execution_config.datasets)} datasets")
            logger.info(f"Total columns: {sum(len(ds.columns) for ds in self.execution_config.datasets)}") 
            logger.info(f"FK relationships: {len(self.execution_config.fk_relationships)}")
            
            return self.execution_config
            
        except Exception as e:
            logger.error(f"Failed to load/translate test mapping: {e}")
            raise AssertionError(f"Could not load test mapping: {e}")
    
    @pytest.mark.django_db(transaction=True)
    def test_blueprint_caching_with_real_mapping(self, production_test_mapping, execution_statistics):
        """Test blueprint caching with real production mapping"""
        # Ensure we're using the test database
        assert production_test_mapping.pk is not None, "Mapping must be saved in test database"
        
        # Load and translate mapping using the automated system
        execution_config = self.load_production_test_mapping(production_test_mapping)
        
        # Verify we have a substantial mapping to test with
        assert len(execution_config.datasets) > 0, "No datasets in mapping"
        assert sum(len(ds.columns) for ds in execution_config.datasets) > 0, "No columns in mapping"
        
        logger.info(f"=== BLUEPRINT CACHING TEST ===")
        logger.info(f"Testing with mapping: {production_test_mapping.name}")
        logger.info(f"Datasets: {len(execution_config.datasets)}")
        logger.info(f"Columns: {sum(len(ds.columns) for ds in execution_config.datasets)}")
        logger.info(f"FK relationships: {len(execution_config.fk_relationships)}")
        
        # Clear any existing cache to start fresh
        cache.clear()
        logger.info("🧹 Cleared cache")
        
        # Initialize first processor
        processor1 = MappingAwareProcessor(
            institution="TEST_BLUEPRINT_CACHE",
            base_uri="http://test-cache.arkumu.org/data",
            statistics=execution_statistics
        )
        
        # Generate cache key and verify it's deterministic
        cache_key_hash1 = processor1._generate_mapping_cache_key(execution_config)
        cache_key1 = f"schema_blueprints_{cache_key_hash1}"
        
        logger.info(f"🔑 Cache key: {cache_key1}")
        logger.info(f"🎯 Cache key hash: {cache_key_hash1}")
        
        # Test 1: First call - should create blueprints and cache them
        logger.info("\n🔄 Test 1: First blueprint creation (should create and cache)")
        
        # Check cache is empty initially
        cached_data = cache.get(cache_key1)
        assert cached_data is None, "Cache should be empty initially"
        logger.info("💾 Initial cache state: MISS (as expected)")
        
        # Create blueprints for the first time
        processor1._create_complete_schema_blueprints(execution_config)
        
        blueprint_count1 = len(processor1.dataset_blueprints)
        logger.info(f"📊 Created {blueprint_count1} blueprints")
        
        # Verify blueprints were created
        assert blueprint_count1 > 0, "No blueprints were created"
        
        # Check that data was cached
        cached_data = cache.get(cache_key1)
        assert cached_data is not None, "Data should be cached after creation"
        assert len(cached_data) == blueprint_count1, "Cached blueprint count doesn't match"
        logger.info(f"💾 Cache after creation: HIT with {len(cached_data)} blueprints")
        
        # Test 2: Second processor with same mapping - should load from cache
        logger.info("\n🔄 Test 2: Second processor (should use cache)")
        
        processor2 = MappingAwareProcessor(
            institution="TEST_BLUEPRINT_CACHE_2",  # Different institution
            base_uri="http://test-cache-2.arkumu.org/data",  # Different base URI
            statistics=ExecutionStatistics()
        )
        
        # Generate cache key - should be the same since it's based on mapping content
        cache_key_hash2 = processor2._generate_mapping_cache_key(execution_config)
        cache_key2 = f"schema_blueprints_{cache_key_hash2}"
        
        # Cache keys should be identical because they depend on mapping content, not processor
        assert cache_key_hash1 == cache_key_hash2, "Cache keys should be identical for same mapping"
        logger.info(f"✅ Cache key consistency verified: {cache_key_hash2}")
        
        # Create blueprints - should load from cache
        processor2._create_complete_schema_blueprints(execution_config)
        
        blueprint_count2 = len(processor2.dataset_blueprints)
        logger.info(f"📊 Loaded {blueprint_count2} blueprints")
        
        # Verify counts match
        assert blueprint_count1 == blueprint_count2, f"Blueprint counts don't match: {blueprint_count1} vs {blueprint_count2}"
        logger.info("✅ Blueprint counts match - caching working correctly!")
        
        # Test 3: Verify blueprint structure is preserved
        logger.info("\n🔄 Test 3: Blueprint structure verification")
        
        # Compare a few blueprint structures
        for dataset_name in list(processor1.dataset_blueprints.keys())[:3]:  # Check first 3
            bp1 = processor1.dataset_blueprints[dataset_name]
            bp2 = processor2.dataset_blueprints[dataset_name]
            
            # Verify key structure elements are preserved
            assert bp1['dataset_name'] == bp2['dataset_name'], f"Dataset name mismatch in {dataset_name}"
            assert len(bp1['property_resources']) == len(bp2['property_resources']), f"Property count mismatch in {dataset_name}"
            assert len(bp1['fk_relationships']) == len(bp2['fk_relationships']), f"FK relationship count mismatch in {dataset_name}"
            
            logger.info(f"   ✅ {dataset_name}: {len(bp1['property_resources'])} properties, {len(bp1['fk_relationships'])} FKs")
        
        # Test 4: Cache invalidation test
        logger.info("\n🔄 Test 4: Cache invalidation verification")
        
        # Clear cache manually
        cache.delete(cache_key1)
        cached_data = cache.get(cache_key1)
        assert cached_data is None, "Cache should be empty after deletion"
        logger.info("🧹 Cache cleared manually")
        
        # Create new processor - should recreate blueprints
        processor3 = MappingAwareProcessor(
            institution="TEST_BLUEPRINT_CACHE_3",
            base_uri="http://test-cache-3.arkumu.org/data", 
            statistics=ExecutionStatistics()
        )
        
        processor3._create_complete_schema_blueprints(execution_config)
        blueprint_count3 = len(processor3.dataset_blueprints)
        
        # Should recreate same number of blueprints
        assert blueprint_count3 == blueprint_count1, f"Blueprint count after cache clear: {blueprint_count3} vs {blueprint_count1}"
        logger.info(f"📊 Recreated {blueprint_count3} blueprints after cache clear")
        
        # Verify cache was repopulated
        cached_data = cache.get(cache_key1)
        assert cached_data is not None, "Cache should be repopulated"
        logger.info("💾 Cache repopulated successfully")
        
        logger.info("\n🎉 BLUEPRINT CACHING TEST PASSED!")
        logger.info("✅ Cache creation working")
        logger.info("✅ Cache retrieval working") 
        logger.info("✅ Cache key consistency verified")
        logger.info("✅ Blueprint structure preserved")
        logger.info("✅ Cache invalidation working")
    
    @pytest.mark.django_db(transaction=True)
    def test_cache_key_determinism(self, production_test_mapping):
        """Test that cache keys are deterministic for the same mapping"""
        # Load mapping
        execution_config = self.load_production_test_mapping(production_test_mapping)
        
        logger.info("=== CACHE KEY DETERMINISM TEST ===")
        
        # Create multiple processors with different settings
        processors = []
        for i in range(3):
            processor = MappingAwareProcessor(
                institution=f"TEST_INST_{i}",
                base_uri=f"http://test-{i}.example.org/data",
                statistics=ExecutionStatistics()
            )
            processors.append(processor)
        
        # Generate cache keys from all processors
        cache_keys = []
        for i, processor in enumerate(processors):
            cache_key_hash = processor._generate_mapping_cache_key(execution_config)
            cache_keys.append(cache_key_hash)
            logger.info(f"Processor {i} cache key: {cache_key_hash}")
        
        # Verify all cache keys are identical
        for i in range(1, len(cache_keys)):
            assert cache_keys[0] == cache_keys[i], f"Cache key {i} differs from cache key 0"
        
        logger.info("✅ All cache keys are identical - determinism verified")
    
    @pytest.mark.django_db(transaction=True) 
    def test_cache_performance_benefit(self, production_test_mapping, execution_statistics):
        """Test that caching provides performance benefits"""
        import time
        
        # Load mapping
        execution_config = self.load_production_test_mapping(production_test_mapping)
        
        logger.info("=== CACHE PERFORMANCE BENEFIT TEST ===")
        
        # Clear cache
        cache.clear()
        
        # Time first creation (cache miss)
        processor1 = MappingAwareProcessor(
            institution="TEST_PERF_1",
            base_uri="http://test-perf.arkumu.org/data",
            statistics=execution_statistics
        )
        
        start_time = time.time()
        processor1._create_complete_schema_blueprints(execution_config)
        creation_time = time.time() - start_time
        
        logger.info(f"⏱️  Blueprint creation time: {creation_time:.4f} seconds")
        
        # Time second creation (cache hit)
        processor2 = MappingAwareProcessor(
            institution="TEST_PERF_2", 
            base_uri="http://test-perf-2.arkumu.org/data",
            statistics=ExecutionStatistics()
        )
        
        start_time = time.time()
        processor2._create_complete_schema_blueprints(execution_config)
        cache_time = time.time() - start_time
        
        logger.info(f"⏱️  Blueprint cache load time: {cache_time:.4f} seconds")
        
        # Calculate performance improvement
        if creation_time > 0:
            improvement = ((creation_time - cache_time) / creation_time) * 100
            logger.info(f"🚀 Performance improvement: {improvement:.1f}%")
            
            # Cache should be significantly faster for large mappings
            if len(execution_config.datasets) > 10:
                assert cache_time < creation_time, "Cache should be faster than creation"
                logger.info("✅ Cache is faster than creation for large mapping")
        
        logger.info("✅ Performance test completed")
    
    def teardown_method(self):
        """Clean up after each test"""
        # Clear cache to avoid test interference
        cache.clear()
        
        # Reset cached data
        self.execution_config = None
        
        # Clean up test database resources
        try:
            # Delete all resources created with test URIs
            Resource.objects.filter(uri__contains="test-cache").delete()
            Resource.objects.filter(uri__contains="test-perf").delete()
        except Exception as e:
            logger.warning(f"Error cleaning up test resources: {e}")