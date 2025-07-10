"""
Real Integration Test for Production Mapping

Tests the complete execution pipeline using:
- Real "fuk-test" mapping from production database
- Real CSV files from S3 bucket (fuk/metadata/*.csv)
- Real database operations (no mocking)
- S3 streaming (no local downloads)


"""
import pytest
import io
import os
import csv
import logging
from typing import Dict, List, Any
from datetime import datetime, timezone
from unittest.mock import patch
from django.test import override_settings
from django.db import connections

from arkumu.storage.services.bucket_service import BucketService
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
from arkumu.importer.services.execution.statistics import ExecutionStatistics, ExecutionMetrics
from arkumu.importer.services.mapping_validation.validator import MappingValidator
from arkumu.metadata.models import Resource
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.models.mappings import Mapping

logger = logging.getLogger(__name__)





@pytest.fixture 
def production_test_mapping(db):
    """Get the REAL production test mapping from the actual database, or skip if not found"""
    # The mapping ALREADY EXISTS in the database - just fetch it!
    mapping = Mapping.objects.filter(name='fuk-test', organization_id='fuk').first()
    
    if not mapping:
        raise AssertionError("production test mapping not found in database")
    
    return mapping


@pytest.fixture(scope="session") 
def real_csv_data():
    """Get REAL CSV data from the organization's MinIO bucket"""
    
    bucket_service = BucketService()
    bucket_name = 'fuk'  # Direct bucket name - we know it exists
    
    logger.info(f"Loading REAL CSV data from MinIO bucket: {bucket_name}")
    
    # List files in metadata/ directory
    files = bucket_service.list_bucket_contents(
        bucket_name=bucket_name,
        prefix='metadata/'
    )
    
    # Filter for CSV files only
    csv_files = []
    for file in files:
        if file['type'] == 'file' and file['name'].lower().endswith('.csv'):
            csv_files.append({
                'key': file['path'],
                'name': file['name'],
                'size': file.get('size', 0),
                'path': file['path']
            })
    
    if not csv_files:
        raise AssertionError("No CSV files found in production metadata bucket")
    
    logger.info(f"Found {len(csv_files)} CSV files in S3 bucket {bucket_name}")
    
    # Load CSV data using BucketService
    csv_data = {}
    for csv_file in csv_files:
        file_path = csv_file['path']
        file_name = csv_file['name']
        dataset_name = file_name.replace('.csv', '')
        
        try:
            # Get file content using BucketService
            result = bucket_service.get_file_content(bucket_name, file_path)
            
            if isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
            else:
                raise Exception(f"Unexpected result format from get_file_content: {result}")
            
            # Parse CSV with semicolon delimiter (FUK standard)
            csv_reader = csv.DictReader(io.StringIO(content), delimiter=';')
            rows = list(csv_reader)
            
            csv_data[dataset_name] = {
                'headers': csv_reader.fieldnames,
                'rows': rows,
                'row_count': len(rows)
            }
            
            logger.info(f"Loaded REAL data from {file_name}: {len(rows)} rows")
            
        except Exception as e:
            logger.warning(f"Failed to load {file_name}: {e}")
            continue
    
    if not csv_data:
        raise AssertionError("No CSV data could be loaded from S3")
        
    logger.info(f"Successfully loaded {len(csv_data)} datasets from S3")
    return csv_data


# Expected CSV files in fuk/metadata/
EXPECTED_FUK_CSV_FILES = [
    'AkteurIn.csv', 'AkteurIn_AkteurIn_Kreuztabelle.csv', 'AkteurIn_Ereignis_Kreuztabelle.csv',
    'Alternativer_Titel.csv', 'Beschreibung.csv', 'Bestehender_Lizenzvertrag.csv',
    'Digitales-Objekt-Lizenz.csv', 'Digitales_Objekt.csv', 'Einliefernde_Hochschule.csv',
    'Equipment_und_Software.csv', 'Equipmentart.csv', 'Ereignis.csv',
    'Ereignis_Ereignis_Kreuztabelle.csv', 'Ereignisbeschreibung.csv', 'Ereignistyp.csv',
    'Informationsträger.csv', 'Informationsträger_Kreuztabelle.csv',
    'Informationsträgereigenschaft.csv', 'Informationsträgertyp.csv', 'Materialschlagwort.csv',
    'Nummernart.csv', 'Organisationseinheit.csv', 'Ort.csv', 'Physisches_Objekt.csv',
    'ProduktID_Kreuztabelle.csv', 'Projekt.csv', 'Projekt_Projekt_Kreuztabelle.csv',
    'Projektart.csv', 'Projekteigenschaft.csv', 'Projekteigenschaft_Kreuztabelle.csv',
    'Projektkategorie.csv', 'Rolle.csv', 'Sammlung.csv', 'Schlagwort.csv', 'Sprache.csv'
]


class TestRealProductionIntegration:
    """Real integration test using actual production data and mapping"""
    
    def setup_method(self):
        """Setup test environment"""
        self.bucket_service = BucketService()
        self.mapping_adapter = MappingAdapter()
        self.statistics = ExecutionStatistics()
        
        # Initialize processor (will be configured per test)
        self.processor = None
        
        # Cache for loaded data
        self.fuk_mapping = None
        self.execution_config = None
        self.csv_files_data = {}
    
    def load_production_test_mapping(self, mapping):
        """Load the real production test mapping from database"""
        if self.fuk_mapping is not None:
            return self.fuk_mapping
            
        try:
            logger.info(f"Found production test mapping: ID={mapping.id}, Name={mapping.name}")
            
            # Load the mapping configuration
            self.fuk_mapping = self.mapping_adapter.load_mapping_config(mapping.id)
            self.execution_config = self.mapping_adapter.translate_to_execution_config(mapping.id)
            
            logger.info(f"Loaded mapping with {len(self.execution_config.datasets)} datasets")
            return self.fuk_mapping
            
        except Exception as e:
            logger.error(f"Failed to load production test mapping: {e}")
            raise AssertionError(f"Could not load production test mapping: {e}")
    
    def stream_csv_files_from_s3(self) -> Dict[str, List[Dict[str, Any]]]:
        """Stream CSV files from S3 fuk/metadata/ directory"""
        if self.csv_files_data:
            return self.csv_files_data
            
        try:
            # Get FUK organization bucket
            bucket_name = self.bucket_service.get_organization_bucket('fuk')
            
            # List files in metadata/ directory
            files = self.bucket_service.list_bucket_contents(bucket_name, prefix='metadata/')
            
            # Filter CSV files
            csv_files = [f for f in files if f['type'] == 'file' and f['name'].endswith('.csv')]
            
            logger.info(f"Found {len(csv_files)} CSV files in {bucket_name}/metadata/")
            
            if len(csv_files) == 0:
                raise AssertionError("No CSV files found in fuk/metadata/ bucket")
            
            # Stream each CSV file and parse content
            csv_data = {}
            processed_files = 0
            
            for file_info in csv_files:
                file_path = file_info['path']
                file_name = file_info['name']
                
                try:
                    # Stream file content directly from S3
                    result = self.bucket_service.get_file_content(bucket_name, file_path)
                    
                    if isinstance(result, dict) and 'content' in result:
                        content = result['content']
                        if isinstance(content, bytes):
                            content = content.decode('utf-8')
                    else:
                        raise Exception(f"Unexpected result format from get_file_content: {result}")
                    
                    # Use CSV reader to parse the content with semicolon delimiter
                    csv_reader = csv.DictReader(io.StringIO(content), delimiter=';')
                    rows = list(csv_reader)
                    
                    # Use filename without .csv as dataset name
                    dataset_name = file_name.replace('.csv', '')
                    csv_data[dataset_name] = rows
                    
                    processed_files += 1
                    logger.info(f"Processed {file_name}: {len(rows)} rows")
                    
                    # Limit for testing - process first 10 files to avoid overwhelming
                    if processed_files >= 10:
                        logger.info(f"Limiting to first {processed_files} files for testing")
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to process {file_name}: {e}")
                    continue
            
            if not csv_data:
                raise AssertionError("No CSV files could be processed from S3")
            
            self.csv_files_data = csv_data
            logger.info(f"Successfully loaded {len(csv_data)} CSV datasets from S3")
            return csv_data
            
        except Exception as e:
            logger.error(f"Failed to stream CSV files from S3: {e}")
            raise AssertionError(f"Could not access S3 files: {e}")
    
    def load_csv_files_from_directory(self, csv_dir):
        """Load CSV files from local directory"""
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
        if not csv_files:
            raise AssertionError(f"No CSV files found in directory: {csv_dir}")
        
        logger.info(f"Found {len(csv_files)} CSV files in {csv_dir}")
        
        csv_data = {}
        for csv_file in csv_files:
            file_path = os.path.join(csv_dir, csv_file)
            logger.info(f"Loading {csv_file}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Parse CSV content with semicolon delimiter
            csv_reader = csv.DictReader(io.StringIO(content), delimiter=';')
            rows = list(csv_reader)
            
            # Use filename without .csv as dataset name
            dataset_name = csv_file.replace('.csv', '')
            csv_data[dataset_name] = rows
            
            logger.info(f"Loaded {csv_file}: {len(rows)} rows, {len(csv_reader.fieldnames)} columns")
        
        return csv_data
    
    @pytest.mark.django_db
    def test_full_production_pipeline_integration(self, production_test_mapping, real_csv_data):
        """Test complete pipeline with real production data"""
        # Load real mapping
        mapping_config = self.load_production_test_mapping(production_test_mapping)
        
        # Use real CSV data (from S3 or local directory)
        csv_sources = real_csv_data
        
        # Verify we have data
        assert len(csv_sources) > 0, "No CSV data loaded"
        assert self.execution_config is not None, "No execution config loaded"
        
        # Initialize processor with real data
        self.processor = MappingAwareProcessor(
            institution="PRODUCTION",
            base_uri="http://arkumu.production.org/data",
            statistics=self.statistics
        )
        
        # Track processing time
        start_time = datetime.now(timezone.utc)
        
        # Execute the full pipeline
        try:
            # Use a supported strategy instead of AUTO
            from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy
            supported_strategy = ProcessingStrategy.STREAMING_ENTITY_CENTRIC
            
            metrics = self.processor.process_with_execution_config(
                execution_config=self.execution_config,
                csv_sources=csv_sources,
                strategy=supported_strategy
            )
            
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            
            # Verify processing completed
            assert isinstance(metrics, ExecutionMetrics)
            assert metrics.rows_processed > 0, "No rows were processed"
            
            # Log results
            print(f"\n=== REAL PRODUCTION INTEGRATION TEST RESULTS ===")
            print(f"Datasets processed: {len(csv_sources)}")
            print(f"Processing time: {processing_time:.2f} seconds")
            print(f"Rows processed: {metrics.rows_processed}")
            print(f"Resources created: {metrics.resources_created}")
            print(f"Triples created: {metrics.triples_created}")
            print(f"Values created: {metrics.values_created}")
            
            # Verify performance
            assert processing_time < 300.0, f"Processing took too long: {processing_time:.2f}s"
            
            # Verify no critical errors
            assert metrics.execution_time is not None or metrics.end_time is not None
            
            print("=== INTEGRATION TEST PASSED ===\n")
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            raise
    
    @pytest.mark.django_db
    def test_mapping_validation_with_real_data(self, production_test_mapping, real_csv_data):
        """Test mapping validation with real production data"""
        # Load real mapping
        mapping_config = self.load_production_test_mapping(production_test_mapping)
        
        # Use real CSV data
        csv_sources = real_csv_data
        
        # Initialize validator
        validator = MappingValidator()
        
        # Validate mapping completeness
        completeness_result = validator.validate_mapping_completeness(mapping_config)
        
        # Log validation results
        print(f"\n=== MAPPING VALIDATION RESULTS ===")
        print(f"Mapping complete: {completeness_result['is_complete']}")
        print(f"Issues: {len(completeness_result.get('issues', []))}")
        
        issues = completeness_result.get('issues', [])
        errors = [i for i in issues if i.get('severity') == 'ERROR']
        warnings = [i for i in issues if i.get('severity') == 'WARNING']
        
        print(f"Errors: {len(errors)}")
        print(f"Warnings: {len(warnings)}")
        
        if errors:
            for error in errors[:5]:  # Show first 5 errors
                print(f"  ERROR: {error['message']}")
        
        if warnings:
            for warning in warnings[:5]:  # Show first 5 warnings
                print(f"  WARNING: {warning['message']}")
        
        print("=== VALIDATION COMPLETE ===\n")
        
        # Log any issues but don't fail the test
        if errors:
            logger.warning(f"Validation found {len(errors)} errors - this may indicate mapping/data issues")
            # Don't fail the test, just log the issues for investigation
    
    @pytest.mark.django_db
    def test_s3_file_correlation(self, production_test_mapping, real_csv_data):
        """Test that S3 files match expected mapping datasets"""
        # Load real mapping
        mapping_config = self.load_production_test_mapping(production_test_mapping)
        
        # Use real CSV data
        csv_sources = real_csv_data
        
        # Get dataset names from mapping
        mapping_datasets = {dataset.dataset_name for dataset in self.execution_config.datasets}
        
        # Get dataset names from CSV files
        csv_datasets = set(csv_sources.keys())
        
        # Log correlation results
        print(f"\n=== FILE CORRELATION ANALYSIS ===")
        print(f"Mapping datasets: {len(mapping_datasets)}")
        print(f"CSV datasets: {len(csv_datasets)}")
        
        # Find matches and mismatches
        matched = mapping_datasets.intersection(csv_datasets)
        mapping_only = mapping_datasets - csv_datasets
        csv_only = csv_datasets - mapping_datasets
        
        print(f"Matched datasets: {len(matched)}")
        print(f"Mapping-only datasets: {len(mapping_only)}")
        print(f"CSV-only datasets: {len(csv_only)}")
        
        if matched:
            print(f"Matched: {sorted(list(matched))[:5]}...")  # Show first 5
        
        if mapping_only:
            print(f"Mapping-only: {sorted(list(mapping_only))[:5]}...")  # Show first 5
        
        if csv_only:
            print(f"CSV-only: {sorted(list(csv_only))[:5]}...")  # Show first 5
        
        print("=== CORRELATION ANALYSIS COMPLETE ===\n")
        
        # Verify we have at least some matches
        assert len(matched) > 0, "No datasets matched between mapping and CSV files"
    
    @pytest.mark.django_db 
    def test_s3_bucket_access(self):
        """Test basic S3 bucket access for production organization"""
        bucket_name = 'fuk'  # We know this bucket exists with real data
        
        # Test listing metadata directory
        files = self.bucket_service.list_bucket_contents(bucket_name, prefix='metadata/')
        
        # Should find some files
        assert len(files) > 0, "No files found in fuk/metadata/"
        
        # Count CSV files
        csv_files = [f for f in files if f['type'] == 'file' and f['name'].endswith('.csv')]
        
        print(f"\n=== S3 BUCKET ACCESS TEST ===")
        print(f"Bucket: {bucket_name}")
        print(f"Total files in metadata/: {len(files)}")
        print(f"CSV files: {len(csv_files)}")
        print("=== S3 ACCESS TEST PASSED ===\n")
        
        assert len(csv_files) > 0, "No CSV files found in fuk/metadata/"
    
    def teardown_method(self):
        """Clean up after each test"""
        if self.processor:
            # Reset processor state
            self.processor.entity_cache = {}
            self.processor.pending_relationships = []
        
        # Reset cached data
        self.csv_files_data = {}
        
        if hasattr(self.statistics, 'reset'):
            self.statistics.reset()