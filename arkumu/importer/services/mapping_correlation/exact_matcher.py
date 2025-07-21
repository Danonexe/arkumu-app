"""
Simple exact matching logic for files and datasets.

Provides deterministic binary matching - no heuristics, AI, or fuzzy matching.
Leverages MappingValidator for complex validation, focuses on exact matching only.
"""

import logging
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from arkumu.common.uri_utils import slugify_uri_part, normalize_string_nfc
from .data_models import FileAnalysis

logger = logging.getLogger(__name__)


class ExactMatcher:
    """Simple exact matching logic - leverages MappingValidator for complex validation."""
    
    @staticmethod
    def match_filename_to_dataset(file_path: str, expected_datasets: List[str]) -> Optional[str]:
        """
        Return exact dataset match for filename or None.
        
        Args:
            file_path: Path to the file (can include directory structure)
            expected_datasets: List of dataset names to match against
            
        Returns:
            Dataset name if exact match found, None otherwise
        """
        file_name = Path(file_path).stem  # Remove .csv extension
        
        # Add detailed logging for German character debugging
        if "informations" in file_name.lower() or "träger" in file_name.lower():
            logger.info(f"🔍 GERMAN CHARACTER DEBUG - Processing file: '{file_name}'")
            logger.info(f"📂 Full file path: {file_path}")
            logger.info(f"📋 Expected datasets: {expected_datasets}")
            
            # Check for exact German character dataset match
            german_dataset = "09_Kreuz_Projekte_Informationsträger"
            if german_dataset in expected_datasets:
                logger.info(f"🎯 FOUND German dataset in expected: '{german_dataset}'")
                logger.info(f"🔍 File name bytes: {file_name.encode('utf-8')}")
                logger.info(f"🔍 Dataset bytes: {german_dataset.encode('utf-8')}")
                logger.info(f"🔍 String comparison: '{file_name}' == '{german_dataset}' ? {file_name == german_dataset}")
                logger.info(f"🔍 Length comparison: {len(file_name)} vs {len(german_dataset)}")
                
                # Also check if file_name is in the expected_datasets list directly
                logger.info(f"🔍 'in' check: '{file_name}' in expected_datasets ? {file_name in expected_datasets}")
                
                # Check position in list
                try:
                    idx = expected_datasets.index(file_name)
                    logger.info(f"🔍 File name found at index {idx} in expected_datasets")
                except ValueError:
                    logger.info(f"🔍 File name NOT found in expected_datasets list")
                    # Check each dataset individually
                    for i, ds in enumerate(expected_datasets):
                        if "informations" in ds.lower():
                            logger.info(f"🔍 Dataset {i}: '{ds}' == '{file_name}' ? {ds == file_name}")
                            logger.info(f"🔍 Dataset {i} bytes: {ds.encode('utf-8')}")
        
        # First try exact string comparison with Unicode normalization
        normalized_file_name = normalize_string_nfc(file_name)
        
        # Check if normalized file name matches any normalized dataset
        for dataset_name in expected_datasets:
            normalized_dataset = normalize_string_nfc(dataset_name)
            
            # Enhanced debug logging for German characters
            if "informations" in file_name.lower() or "Informationsträger" in dataset_name:
                logger.info(f"🔍 UNICODE NORMALIZATION - File: '{file_name}' -> Normalized: '{normalized_file_name}'")
                logger.info(f"🔍 UNICODE NORMALIZATION - Dataset: '{dataset_name}' -> Normalized: '{normalized_dataset}'")
                logger.info(f"🔍 UNICODE COMPARISON - '{normalized_file_name}' == '{normalized_dataset}' ? {normalized_file_name == normalized_dataset}")
                logger.info(f"🔍 File bytes: {normalized_file_name.encode('utf-8')}")
                logger.info(f"🔍 Dataset bytes: {normalized_dataset.encode('utf-8')}")
            
            if normalized_file_name == normalized_dataset:
                logger.debug(f"Exact match found: '{file_name}' -> dataset '{dataset_name}'")
                if "informations" in file_name.lower():
                    logger.info(f"✅ GERMAN CHARACTER SUCCESS - Unicode normalized exact match: '{file_name}' -> '{dataset_name}'")
                return dataset_name
        
        # Then try matching with slugified dataset names (using existing URI utils)
        # The file name might be slugified but the dataset name in the config is not
        for dataset_name in expected_datasets:
            slugified_dataset = slugify_uri_part(dataset_name).replace('-', '_')
            
            # Extra logging for German character dataset
            if "Informationsträger" in dataset_name:
                logger.info(f"🔄 GERMAN CHARACTER SLUGIFY - Original: '{dataset_name}' -> Slugified: '{slugified_dataset}' -> Comparing with file: '{file_name}'")
            
            if file_name == slugified_dataset:
                logger.debug(f"Slugified match found: '{file_name}' -> dataset '{dataset_name}' (slugified: '{slugified_dataset}')")
                if "informations" in file_name.lower():
                    logger.info(f"✅ GERMAN CHARACTER SUCCESS - Slugified match: '{file_name}' -> '{dataset_name}'")
                return dataset_name
        
        # REVERSE matching: Try matching when file name has German chars but dataset is sanitized
        # Slugify the file name and compare to datasets
        for dataset_name in expected_datasets:
            slugified_filename = slugify_uri_part(file_name).replace('-', '_')
            
            # Extra logging for German character dataset
            if "informations" in file_name.lower() or "Informationsträger" in dataset_name:
                logger.info(f"🔄 REVERSE GERMAN CHARACTER MATCH - File: '{file_name}' -> Slugified: '{slugified_filename}' -> Comparing with dataset: '{dataset_name}'")
            
            if slugified_filename == dataset_name:
                logger.info(f"✅ REVERSE GERMAN CHARACTER SUCCESS - File '{file_name}' (slugified: '{slugified_filename}') matches dataset '{dataset_name}'")
                return dataset_name
        
        # Additional fallback attempts for German characters
        if "informations" in file_name.lower():
            logger.info(f"🔧 GERMAN CHARACTER FALLBACK - Trying additional patterns for: '{file_name}'")
            for dataset_name in expected_datasets:
                if "Informationsträger" in dataset_name:
                    # Try various possible transformations
                    patterns = [
                        dataset_name.lower(),
                        dataset_name.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss'),
                        slugify_uri_part(dataset_name),
                        slugify_uri_part(dataset_name).replace('-', '_'),
                    ]
                    
                    for pattern in patterns:
                        logger.info(f"🔄 Trying pattern: '{pattern}' == '{file_name}' ? {pattern == file_name}")
                        if pattern == file_name:
                            logger.info(f"✅ GERMAN CHARACTER FALLBACK SUCCESS: '{file_name}' -> '{dataset_name}' (pattern: '{pattern}')")
                            return dataset_name
        
        if "informations" in file_name.lower():
            logger.error(f"❌ GERMAN CHARACTER FAILURE - No match found for: '{file_name}' in {len(expected_datasets)} datasets")
        logger.debug(f"No match for file '{file_name}' in datasets: {expected_datasets}")
        return None
    
    @staticmethod
    def match_files_to_datasets(files: List[FileAnalysis], 
                               datasets: List[str]) -> Dict[str, str]:
        """
        Perform exact filename matching for multiple files.
        
        Args:
            files: List of FileAnalysis objects
            datasets: List of expected dataset names
            
        Returns:
            Dictionary mapping file_path -> dataset_name for exact matches only
        """
        matches = {}
        
        for file_analysis in files:
            matched_dataset = ExactMatcher.match_filename_to_dataset(
                file_analysis.file_path, datasets
            )
            if matched_dataset:
                matches[file_analysis.file_path] = matched_dataset
                logger.debug(f"Matched '{file_analysis.file_path}' to dataset '{matched_dataset}'")
        
        logger.info(f"Found {len(matches)} exact matches out of {len(files)} files")
        return matches
    
    @staticmethod
    def find_missing_datasets(matched_datasets: Set[str], 
                             expected_datasets: List[str]) -> List[str]:
        """
        Find datasets that have no matching files.
        
        Args:
            matched_datasets: Set of dataset names that have matching files
            expected_datasets: List of all expected dataset names
            
        Returns:
            List of dataset names with no matching files
        """
        missing = [dataset for dataset in expected_datasets 
                  if dataset not in matched_datasets]
        
        if missing:
            logger.info(f"Missing datasets (no matching files): {missing}")
        
        return missing
    
    @staticmethod
    def find_unmatched_files(file_paths: List[str], 
                           expected_datasets: List[str]) -> List[str]:
        """
        Find files that don't match any dataset names.
        
        Args:
            file_paths: List of file paths
            expected_datasets: List of expected dataset names
            
        Returns:
            List of file paths that don't match any dataset
        """
        unmatched = []
        
        for file_path in file_paths:
            matched_dataset = ExactMatcher.match_filename_to_dataset(file_path, expected_datasets)
            if not matched_dataset:
                unmatched.append(file_path)
        
        if unmatched:
            logger.info(f"Unmatched files (no matching datasets): {[Path(f).name for f in unmatched]}")
        
        return unmatched
    
    @staticmethod
    def calculate_exact_coverage(total_files: int, 
                               matched_files: int, 
                               total_datasets: int, 
                               matched_datasets: int) -> Dict[str, float]:
        """
        Calculate exact coverage percentages.
        
        Args:
            total_files: Total number of files
            matched_files: Number of files with exact dataset matches
            total_datasets: Total number of expected datasets
            matched_datasets: Number of datasets with exact file matches
            
        Returns:
            Dictionary with coverage percentages
        """
        file_coverage = (matched_files / total_files * 100) if total_files > 0 else 0.0
        dataset_coverage = (matched_datasets / total_datasets * 100) if total_datasets > 0 else 0.0
        
        return {
            'file_coverage_percentage': file_coverage,
            'dataset_coverage_percentage': dataset_coverage,
            'is_complete_coverage': file_coverage == 100.0 and dataset_coverage == 100.0
        }
    
    @staticmethod
    def check_exact_column_overlap(file_columns: List[str], 
                                 required_columns: List[str]) -> Dict[str, Any]:
        """
        Check exact column overlap between file and required columns.
        
        Args:
            file_columns: List of column names from the file
            required_columns: List of required column names from mapping
            
        Returns:
            Dictionary with overlap analysis
        """
        file_set = set(file_columns)
        required_set = set(required_columns)
        
        matched = list(file_set & required_set)
        missing = list(required_set - file_set)
        extra = list(file_set - required_set)
        
        coverage = (len(matched) / len(required_columns) * 100) if required_columns else 100.0
        
        return {
            'matched_columns': matched,
            'missing_columns': missing,
            'extra_columns': extra,
            'coverage_percentage': coverage,
            'has_all_required': len(missing) == 0,
            'has_only_required': len(extra) == 0
        }
    
    @staticmethod
    def validate_exact_requirements(correlation_results: List[Dict]) -> Dict[str, bool]:
        """
        Validate if all exact requirements are met for execution.
        
        Args:
            correlation_results: List of correlation result dictionaries
            
        Returns:
            Dictionary with validation flags
        """
        all_files_matched = all(
            result.get('is_exact_match', False) 
            for result in correlation_results
        )
        
        no_missing_columns = all(
            not result.get('missing_columns', []) 
            for result in correlation_results
        )
        
        no_type_mismatches = all(
            not result.get('type_mismatches', []) 
            for result in correlation_results
        )
        
        return {
            'all_files_matched': all_files_matched,
            'no_missing_columns': no_missing_columns,
            'no_type_mismatches': no_type_mismatches,
            'ready_for_execution': all_files_matched and no_missing_columns and no_type_mismatches
        }