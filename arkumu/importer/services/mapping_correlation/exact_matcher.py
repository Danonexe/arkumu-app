"""
Simple exact matching logic for files and datasets.

Provides deterministic binary matching - no heuristics, AI, or fuzzy matching.
Leverages MappingValidator for complex validation, focuses on exact matching only.
"""

import logging
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

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
        
        # Exact string comparison only
        if file_name in expected_datasets:
            logger.debug(f"Exact match found: '{file_name}' -> dataset '{file_name}'")
            return file_name
        
        logger.debug(f"No exact match for file '{file_name}' in datasets: {expected_datasets}")
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
        dataset_set = set(datasets)
        
        for file_analysis in files:
            file_name = Path(file_analysis.file_path).stem
            if file_name in dataset_set:
                matches[file_analysis.file_path] = file_name
                logger.debug(f"Matched '{file_analysis.file_path}' to dataset '{file_name}'")
        
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
        dataset_set = set(expected_datasets)
        unmatched = []
        
        for file_path in file_paths:
            file_name = Path(file_path).stem
            if file_name not in dataset_set:
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