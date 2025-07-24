"""
KHM Correlation Service Integration Test

This test validates the mapping correlation service with real KHM dataset names,
specifically testing the handling of German characters in dataset names like
"09_Kreuz_Projekte_Informationsträger".

## How It Works

### 1. Data Sources
- **Mapping Configuration**: Creates KHM mapping config with 19 datasets
- **CSV Files**: Creates temporary CSV files with sanitized names  
- **Test Database**: Uses isolated test database, never touches production data

### 2. Component Architecture

**MappingFileCorrelationService** (`arkumu.importer.services.mapping_correlation.correlation_service`)
├── Uses existing S3DirectDataAnalyzer for file analysis
├── Uses existing MappingValidator for validation
├── Uses existing URI utils (slugify_uri_part) for character handling
└── Provides exact file-to-dataset correlation

**ExactMatcher** (`arkumu.importer.services.mapping_correlation.exact_matcher`)
├── Handles exact filename matching
├── Falls back to sanitized name matching using URI utils
└── Properly matches German characters: "Informationsträger" → "informationstraeger"

### 3. Test Flow

1. **Setup**: Create KHM datasets and mapping configuration
2. **CSV Files**: Create temporary files with sanitized names
3. **Correlation**: Run correlation service to match files to datasets  
4. **Verification**: Check that German character dataset matches correctly
5. **Validation**: Ensure 19/19 files match (no missing/extra files)

### 4. Key Benefits

- **Real Dataset Names**: Uses actual KHM dataset names from production
- **German Character Testing**: Specifically tests problematic "Informationsträger" 
- **URI Utils Integration**: Uses existing production URI sanitization
- **Test Isolation**: Complete test isolation with temporary files
- **Error Detection**: Catches correlation issues before they reach production

### 5. Expected Results

- 19 datasets processed from temporary CSV files
- All datasets matched correctly including "09_Kreuz_Projekte_Informationsträger"
- No missing datasets, no unmatched files
- Complete correlation success (19/19 matched)
- Processing completes without errors

The test validates that the correlation service correctly handles German character
datasets using the existing URI sanitization system.
"""
import pytest
import logging
from typing import Dict, List, Any
from pathlib import Path

from arkumu.importer.services.mapping_correlation.correlation_service import MappingFileCorrelationService
from arkumu.importer.services.mapping_correlation.exact_matcher import ExactMatcher
from arkumu.common.uri_utils import slugify_uri_part

logger = logging.getLogger(__name__)


class TestKHMCorrelationIntegration:
    """Integration test for correlation service with KHM datasets including German characters."""
    
    def setup_method(self):
        """Setup test environment."""
        self.correlation_service = MappingFileCorrelationService("khm")  # Use lowercase org code for S3
        
    @pytest.mark.django_db(transaction=True)
    def test_german_character_correlation(self, khm_csv_files_from_s3, khm_mapping_config):
        """Test that correlation service handles German character datasets correctly."""
        
        file_paths = khm_csv_files_from_s3
        
        logger.info(f"=== KHM GERMAN CHARACTER CORRELATION TEST ===")
        logger.info(f"Testing correlation with {len(file_paths)} CSV files")
        logger.info(f"Mapping config has {len(khm_mapping_config['workspace_datasets'])} datasets")
        
        # Show the problematic dataset and expected file
        german_dataset = "09_Kreuz_Projekte_Informationsträger"
        expected_filename = "09_kreuz_projekte_informationstraeger.csv"
        
        logger.info(f"German character dataset: '{german_dataset}'")
        logger.info(f"Expected sanitized filename: '{expected_filename}'")
        logger.info(f"URI sanitization result: '{slugify_uri_part(german_dataset)}'")
        
        # Analyze correlation
        try:
            result = self.correlation_service.analyze_file_dataset_correlation(
                file_paths, 
                khm_mapping_config
            )
            
            logger.info(f"\n=== CORRELATION RESULTS ===")
            logger.info(f"Total files analyzed: {len(result.file_analyses)}")
            logger.info(f"Exactly matched datasets: {len(result.exactly_matched_datasets)}")
            logger.info(f"Missing datasets: {len(result.missing_datasets)}")
            logger.info(f"Unmatched files: {len(result.unmatched_files)}")
            logger.info(f"Has all required datasets: {result.has_all_required_datasets}")
            logger.info(f"Has no extra files: {result.has_no_extra_files}")
            
            if result.missing_datasets:
                logger.error(f"Missing datasets: {result.missing_datasets}")
            
            if result.unmatched_files:
                logger.error(f"Unmatched files: {[Path(f).name for f in result.unmatched_files]}")
            
            if result.recommendations:
                logger.info(f"Recommendations:")
                for rec in result.recommendations:
                    logger.info(f"  - {rec}")
            
            # Check if German character dataset was matched correctly
            german_matched = german_dataset in result.exactly_matched_datasets
            
            logger.info(f"\n=== GERMAN CHARACTER TEST ===")
            logger.info(f"German character dataset '{german_dataset}' matched: {german_matched}")
            
            if german_matched:
                logger.info("✅ SUCCESS: German character dataset correlation working!")
            else:
                logger.error("❌ FAILED: German character dataset not matched")
                logger.error(f"Matched datasets: {result.exactly_matched_datasets}")
            
            # Detailed assertion messages
            assert len(result.file_analyses) > 0, "No files were analyzed"
            assert german_matched, f"German character dataset '{german_dataset}' was not matched"
            assert result.has_all_required_datasets, f"Missing {len(result.missing_datasets)} datasets: {result.missing_datasets}"
            assert result.has_no_extra_files, f"Found {len(result.unmatched_files)} unmatched files: {[Path(f).name for f in result.unmatched_files]}"
            
            logger.info("✅ All correlation tests passed!")
            
            return result
            
        except Exception as e:
            logger.error(f"Error during correlation analysis: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    @pytest.mark.django_db(transaction=True)
    def test_exact_matcher_german_characters(self, khm_datasets):
        """Test the ExactMatcher component specifically with German characters."""
        
        logger.info(f"=== EXACT MATCHER GERMAN CHARACTER TEST ===")
        
        # Test the problematic case directly
        german_dataset = "09_Kreuz_Projekte_Informationsträger"
        expected_filename = "09_kreuz_projekte_informationstraeger.csv"
        
        logger.info(f"Testing exact matcher with:")
        logger.info(f"  Dataset: {german_dataset}")  
        logger.info(f"  Filename: {expected_filename}")
        
        # Test the match
        matched_dataset = ExactMatcher.match_filename_to_dataset(
            expected_filename, 
            [german_dataset]
        )
        
        logger.info(f"  Match result: {matched_dataset}")
        
        assert matched_dataset == german_dataset, f"Expected match for '{german_dataset}' but got '{matched_dataset}'"
        
        logger.info("✅ ExactMatcher German character test passed!")

    @pytest.mark.django_db(transaction=True) 
    def test_uri_utils_integration(self):
        """Test that URI utils properly handle German characters as expected by correlation service."""
        
        logger.info(f"=== URI UTILS INTEGRATION TEST ===")
        
        test_cases = [
            ("09_Kreuz_Projekte_Informationsträger", "09-kreuz-projekte-informationstraeger"),
            ("10_PhysMedien_Informationstraeger", "10-physmedien-informationstraeger"),
            ("05_PersonenBetreuende", "05-personenbetreuende"),
        ]
        
        for original, expected_slug in test_cases:
            actual_slug = slugify_uri_part(original)
            logger.info(f"URI slugify: '{original}' → '{actual_slug}'")
            
            # Convert to filesystem-like format (hyphens to underscores)
            filesystem_version = actual_slug.replace('-', '_')
            logger.info(f"Filesystem version: '{filesystem_version}'")
            
            # The correlation service should be able to match this
            matched = ExactMatcher.match_filename_to_dataset(
                f"{filesystem_version}.csv",
                [original]
            )
            
            logger.info(f"Correlation match: {matched}")
            assert matched == original, f"Failed to match '{original}' with filesystem name '{filesystem_version}.csv'"
        
        logger.info("✅ URI utils integration test passed!")

    @pytest.mark.django_db(transaction=True)
    def test_correlation_coverage_statistics(self, khm_csv_files_from_s3, khm_mapping_config):
        """Test correlation coverage statistics calculation."""
        
        logger.info(f"=== CORRELATION COVERAGE TEST ===")
        
        file_paths = khm_csv_files_from_s3
        
        result = self.correlation_service.analyze_file_dataset_correlation(
            file_paths, 
            khm_mapping_config
        )
        
        # Calculate coverage statistics
        coverage_stats = self.correlation_service.calculate_exact_coverage(result)
        
        logger.info(f"Coverage Statistics:")
        logger.info(f"  File coverage: {coverage_stats.get('file_coverage', 'N/A')}")
        logger.info(f"  Dataset coverage: {coverage_stats.get('dataset_coverage', 'N/A')}")
        logger.info(f"  Overall ready: {coverage_stats.get('overall_ready', False)}")
        
        # Verify we have perfect coverage
        expected_file_count = len(khm_mapping_config['workspace_datasets'])
        expected_dataset_count = len(khm_mapping_config['workspace_datasets'])
        
        assert len(result.file_analyses) == expected_file_count, f"Expected {expected_file_count} files, got {len(result.file_analyses)}"
        assert len(result.exactly_matched_datasets) == expected_dataset_count, f"Expected {expected_dataset_count} matched datasets, got {len(result.exactly_matched_datasets)}"
        
        logger.info("✅ Perfect correlation coverage achieved!")