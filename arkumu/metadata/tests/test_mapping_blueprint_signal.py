"""
Test that mapping blueprint signal creates dataset URIs when mapping is saved
"""
import pytest
from django.test import TestCase
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.models import Resource
from arkumu.storage.services.bucket_service import BucketService
import logging

logger = logging.getLogger(__name__)


class TestMappingBlueprintSignal(TestCase):
    """Test the signal handler that creates blueprint structure from mapping"""
    
    def setUp(self):
        """Set up test data"""
        # Load real FUK mapping for testing
        self.bucket_service = BucketService()
        try:
            self.mapping_data = self.bucket_service.load_json_file('fuk', 'metadata/fuk_mapping.json')
        except Exception as e:
            self.skipTest(f"Cannot load FUK mapping from S3: {e}")
    
    def test_blueprint_created_for_validated_mapping(self):
        """Test that dataset URIs are created when mapping status is 'validated'"""
        
        # Create a mapping with validated status
        mapping = Mapping.objects.create(
            name='test-fuk-mapping-validated',
            organization_id='fuk',
            mapping_config=self.mapping_data,
            validation_status='validated'
        )
        
        # Check that dataset URIs were created
        dataset_uris = Resource.objects.filter(
            uri__contains='/datasets/'
        ).filter(
            uri__contains='http://arkumu.org/data/fuk/'
        )
        
        # Should have created URIs for all 35 datasets
        self.assertGreaterEqual(dataset_uris.count(), 35, "Should have at least 35 dataset URIs")
        
        # Check specifically for Sammlung
        sammlung_uri = dataset_uris.filter(uri__contains='/datasets/sammlung').first()
        self.assertIsNotNone(sammlung_uri, "Sammlung dataset URI should exist")
        
        logger.info(f"Created {dataset_uris.count()} dataset URIs for validated mapping")
    
    def test_blueprint_created_for_active_mapping(self):
        """Test that dataset URIs are created when mapping status is 'active'"""
        
        # Create a mapping with active status
        mapping = Mapping.objects.create(
            name='test-fuk-mapping-active',
            organization_id='fuk',
            mapping_config=self.mapping_data,
            validation_status='active'
        )
        
        # Check that dataset URIs were created
        dataset_uris = Resource.objects.filter(
            uri__contains='/datasets/'
        ).filter(
            uri__contains='http://arkumu.org/data/fuk/'
        )
        
        # Should have created URIs for all 35 datasets
        self.assertGreaterEqual(dataset_uris.count(), 35, "Should have at least 35 dataset URIs")
        
        logger.info(f"Created {dataset_uris.count()} dataset URIs for active mapping")
    
    def test_no_blueprint_for_draft_mapping(self):
        """Test that dataset URIs are NOT created for draft mappings"""
        
        # Clear any existing URIs
        Resource.objects.filter(uri__contains='http://arkumu.org/data/fuk/').delete()
        
        # Create a mapping with draft status
        mapping = Mapping.objects.create(
            name='test-fuk-mapping-draft',
            organization_id='fuk',
            mapping_config=self.mapping_data,
            validation_status='draft'  # Should not trigger blueprint creation
        )
        
        # Check that no dataset URIs were created
        dataset_uris = Resource.objects.filter(
            uri__contains='/datasets/'
        ).filter(
            uri__contains='http://arkumu.org/data/fuk/'
        )
        
        self.assertEqual(dataset_uris.count(), 0, "Should not create URIs for draft mappings")
        
        logger.info("Correctly skipped blueprint creation for draft mapping")
    
    def test_updating_mapping_to_validated_creates_blueprint(self):
        """Test that updating a mapping to validated status creates the blueprint"""
        
        # Create a draft mapping first
        mapping = Mapping.objects.create(
            name='test-fuk-mapping-update',
            organization_id='fuk',
            mapping_config=self.mapping_data,
            validation_status='draft'
        )
        
        # Verify no URIs initially
        initial_count = Resource.objects.filter(
            uri__contains='/datasets/'
        ).filter(
            uri__contains='http://arkumu.org/data/fuk/'
        ).count()
        
        # Update to validated
        mapping.validation_status = 'validated'
        mapping.save()
        
        # Check that dataset URIs were created
        dataset_uris = Resource.objects.filter(
            uri__contains='/datasets/'
        ).filter(
            uri__contains='http://arkumu.org/data/fuk/'
        )
        
        new_count = dataset_uris.count()
        self.assertGreater(new_count, initial_count, "Should have created URIs when updated to validated")
        self.assertGreaterEqual(new_count, 35, "Should have at least 35 dataset URIs")
        
        logger.info(f"Created {new_count - initial_count} new dataset URIs when mapping was updated to validated")
    
    def test_signal_handles_missing_mapping_config_gracefully(self):
        """Test that signal doesn't crash when mapping has no config"""
        
        # Create mapping without config
        mapping = Mapping.objects.create(
            name='test-empty-mapping',
            organization_id='fuk',
            mapping_config={},  # Empty config
            validation_status='validated'
        )
        
        # Should not crash - signal should handle this gracefully
        # Test passes if no exception is raised
        logger.info("Signal handled empty mapping config gracefully")