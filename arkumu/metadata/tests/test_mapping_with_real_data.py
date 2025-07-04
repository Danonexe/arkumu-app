"""
Test mapping execution with real data from S3.

Run with: docker compose -f docker-compose.local.yml run --rm django pytest arkumu/metadata/tests/test_mapping_with_real_data.py -v
"""

import pytest
from django.test import TestCase
from django.utils import timezone

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.mapping_executor import MappingExecutor
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer


@pytest.mark.django_db
class TestMappingWithRealData(TestCase):
    """Test mapping execution with real S3 data."""
    
    def setUp(self):
        """Set up test environment."""
        self.organization_id = "rsh"  # Replace with your org
        self.mapping_id = None  # Will be set to your mapping ID
        
    def test_load_and_execute_saved_mapping(self):
        """Test loading a saved mapping and executing it with real data."""
        
        # Step 1: Load your saved mapping
        # Replace this with your actual mapping ID
        mapping_id = "your-mapping-id-here"  # <-- REPLACE THIS
        
        try:
            mapping = Mapping.objects.get(
                id=mapping_id,
                organization_id=self.organization_id
            )
            print(f"\n✅ Found mapping: {mapping.name}")
            print(f"   Datasets: {mapping.source_datasets}")
            print(f"   Columns configured: {len(mapping.mapping_config.get('workspace_columns', {}))}")
            
        except Mapping.DoesNotExist:
            self.skipTest(f"Mapping {mapping_id} not found. Please set a valid mapping ID.")
            
        # Step 2: Load CSV data from S3
        analyzer = S3DirectDataAnalyzer()
        
        # Get available datasets
        available_sources = analyzer.list_data_sources(
            organization_folder=self.organization_id
        )
        print(f"\n📁 Available datasets in S3: {len(available_sources)}")
        
        # Load data for each dataset in the mapping
        all_csv_data = []
        for dataset_name in mapping.source_datasets:
            print(f"\n📊 Loading dataset: {dataset_name}")
            
            # Get sample data (you can adjust the limit)
            try:
                dataset_info = analyzer.analyze_dataset(
                    organization_folder=self.organization_id,
                    dataset_name=dataset_name,
                    sample_size=100  # Adjust as needed
                )
                
                if dataset_info and 'sample_data' in dataset_info:
                    csv_data = dataset_info['sample_data']
                    print(f"   Loaded {len(csv_data)} rows")
                    all_csv_data.extend(csv_data)
                else:
                    print(f"   ⚠️  No data found for {dataset_name}")
                    
            except Exception as e:
                print(f"   ❌ Error loading {dataset_name}: {e}")
        
        # Step 3: Execute the mapping
        if all_csv_data:
            print(f"\n🚀 Executing mapping with {len(all_csv_data)} total rows...")
            
            executor = MappingExecutor(base_uri="http://arkumu.org/data")
            
            try:
                stats = executor.execute_mapping(mapping, all_csv_data)
                
                print(f"\n✅ Execution complete!")
                print(f"   Entities created: {stats.entities_created}")
                print(f"   Entities updated: {stats.entities_updated}")
                print(f"   Triples created: {stats.triples_created}")
                print(f"   Rows processed: {stats.rows_processed}")
                print(f"   Errors: {stats.errors}")
                
                # Verify some data was created
                self.assertGreater(stats.rows_processed, 0)
                self.assertGreaterEqual(stats.entities_created + stats.entities_updated, 0)
                
            except Exception as e:
                self.fail(f"Mapping execution failed: {e}")
        else:
            self.skipTest("No CSV data could be loaded from S3")
    
    def test_execute_mapping_via_api(self):
        """Test executing mapping through the API view."""
        from django.test import Client
        from django.urls import reverse
        
        client = Client()
        
        # Replace with your mapping ID
        mapping_id = "your-mapping-id-here"  # <-- REPLACE THIS
        
        # Make request to execute mapping
        response = client.post(
            reverse('metadata:execute_gui_mapping'),
            data={
                'mapping_id': mapping_id,
                'organization': self.organization_id,
                'strategy': 'SKIP_EXISTING'
            }
        )
        
        # Check response
        if response.status_code == 404:
            self.skipTest(f"Mapping {mapping_id} not found")
        
        self.assertEqual(response.status_code, 200)
        
        # Parse response
        if response.get('Content-Type', '').startswith('application/json'):
            data = response.json()
            print(f"\n📋 API Response: {data}")
            self.assertEqual(data.get('status'), 'success')
        else:
            # HTML response
            self.assertIn(b'success', response.content.lower())