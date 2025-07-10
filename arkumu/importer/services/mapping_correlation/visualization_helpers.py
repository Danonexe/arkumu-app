"""
Visualization helpers for mapping correlation service GUI data preparation.

This module provides utilities for preparing correlation analysis data
for display in the user interface, including status formatting,
badge styling, and data transformation for templates.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path

from .data_models import CorrelationResult, DatasetCorrelation, FileAnalysis


class CorrelationVisualizationHelper:
    """Helper class for preparing correlation data for GUI display."""
    
    @staticmethod
    def format_correlation_for_template(correlation_result: CorrelationResult) -> Dict[str, Any]:
        """
        Format correlation result for template rendering.
        
        Args:
            correlation_result: CorrelationResult to format
            
        Returns:
            Dictionary with formatted data for template display
        """
        if not correlation_result:
            return {
                'has_data': False,
                'correlations': [],
                'summary': {},
                'status_indicators': {}
            }
        
        # Format individual correlations
        formatted_correlations = []
        for correlation in correlation_result.dataset_correlations:
            formatted_correlations.append({
                'file_name': Path(correlation.file_path).name,
                'file_path': correlation.file_path,
                'dataset_name': correlation.dataset_name or 'No match',
                'is_exact_match': correlation.is_exact_match,
                'status': correlation.status,
                'status_badge_class': CorrelationVisualizationHelper._get_status_badge_class(correlation.status),
                'matched_column_count': len(correlation.matched_columns),
                'missing_column_count': len(correlation.missing_columns),
                'extra_column_count': len(correlation.extra_columns),
                'type_mismatch_count': len(correlation.type_mismatches),
                'has_issues': len(correlation.missing_columns) > 0 or len(correlation.type_mismatches) > 0
            })
        
        # Overall summary
        summary = {
            'total_files': len(correlation_result.file_analyses),
            'matched_files': len([c for c in correlation_result.dataset_correlations if c.is_exact_match]),
            'total_expected_datasets': len(correlation_result.mapping_analysis.expected_datasets) if correlation_result.mapping_analysis else 0,
            'matched_datasets': len(correlation_result.exactly_matched_datasets),
            'missing_datasets': len(correlation_result.missing_datasets),
            'unmatched_files': len(correlation_result.unmatched_files),
            'is_ready_for_execution': correlation_result.has_all_required_datasets and correlation_result.has_no_extra_files
        }
        
        # Status indicators
        status_indicators = {
            'overall_status': 'success' if summary['is_ready_for_execution'] else 'warning',
            'overall_icon': '✓' if summary['is_ready_for_execution'] else '⚠',
            'completion_badge': 'Complete' if correlation_result.has_all_required_datasets else 'Incomplete'
        }
        
        return {
            'has_data': True,
            'correlations': formatted_correlations,
            'summary': summary,
            'status_indicators': status_indicators,
            'missing_datasets': correlation_result.missing_datasets,
            'unmatched_files': [Path(f).name for f in correlation_result.unmatched_files],
            'recommendations': correlation_result.recommendations,
            'is_ready_for_execution': summary['is_ready_for_execution']
        }
    
    @staticmethod
    def format_column_details_for_template(correlation: DatasetCorrelation) -> List[Dict[str, Any]]:
        """
        Format column-level details for expandable table display.
        
        Args:
            correlation: DatasetCorrelation to format
            
        Returns:
            List of column detail dictionaries for template display
        """
        column_details = []
        
        # Matched columns
        for column in correlation.matched_columns:
            column_details.append({
                'file_column': column,
                'mapping_column': column,
                'status': 'matched',
                'status_badge_class': 'badge-success',
                'type_compatible': True,  # Assuming matched means compatible
                'issue_description': None
            })
        
        # Missing columns (required by mapping but not in file)
        for column in correlation.missing_columns:
            column_details.append({
                'file_column': '—',
                'mapping_column': column,
                'status': 'missing',
                'status_badge_class': 'badge-error',
                'type_compatible': False,
                'issue_description': 'Required column missing from file'
            })
        
        # Extra columns (in file but not in mapping)
        for column in correlation.extra_columns:
            column_details.append({
                'file_column': column,
                'mapping_column': '—',
                'status': 'extra',
                'status_badge_class': 'badge-warning',
                'type_compatible': None,
                'issue_description': 'Column not defined in mapping'
            })
        
        # Type mismatches
        for mismatch in correlation.type_mismatches:
            column_name = mismatch.get('column_name', 'unknown')
            expected_type = mismatch.get('expected_type', 'unknown')
            actual_type = mismatch.get('file_type', 'unknown')
            
            column_details.append({
                'file_column': column_name,
                'mapping_column': column_name,
                'status': 'type_mismatch',
                'status_badge_class': 'badge-error',
                'type_compatible': False,
                'issue_description': f'Type mismatch: found {actual_type}, expected {expected_type}'
            })
        
        return column_details
    
    @staticmethod
    def _get_status_badge_class(status: str) -> str:
        """Get DaisyUI badge class for correlation status."""
        status_classes = {
            'exact_match': 'badge-success',
            'no_match': 'badge-error',
            'partial_match': 'badge-warning',
            'matched': 'badge-success',
            'missing': 'badge-error',
            'extra': 'badge-warning',
            'type_mismatch': 'badge-error'
        }
        return status_classes.get(status, 'badge-neutral')
    
    @staticmethod
    def get_completion_percentage(correlation_result: CorrelationResult) -> int:
        """
        Calculate completion percentage for progress display.
        
        Args:
            correlation_result: CorrelationResult to analyze
            
        Returns:
            Completion percentage (0-100)
        """
        if not correlation_result.mapping_analysis:
            return 0
        
        total_expected = len(correlation_result.mapping_analysis.expected_datasets)
        if total_expected == 0:
            return 100
        
        matched = len(correlation_result.exactly_matched_datasets)
        return int((matched / total_expected) * 100)
    
    @staticmethod
    def format_file_analysis_summary(file_analyses: List[FileAnalysis]) -> List[Dict[str, Any]]:
        """
        Format file analysis data for summary display.
        
        Args:
            file_analyses: List of FileAnalysis objects
            
        Returns:
            List of formatted file summaries
        """
        summaries = []
        
        for analysis in file_analyses:
            summaries.append({
                'file_name': analysis.file_name,
                'file_path': analysis.file_path,
                'column_count': analysis.column_count,
                'row_count': analysis.row_count,
                'matched_dataset': analysis.matched_dataset_name or 'No match',
                'has_match': analysis.matched_dataset_name is not None,
                'columns_preview': analysis.columns[:5] if len(analysis.columns) > 5 else analysis.columns,
                'has_more_columns': len(analysis.columns) > 5,
                'additional_column_count': max(0, len(analysis.columns) - 5)
            })
        
        return summaries
    
    @staticmethod
    def generate_action_items(correlation_result: CorrelationResult) -> List[Dict[str, Any]]:
        """
        Generate actionable items for users based on correlation results.
        
        Args:
            correlation_result: CorrelationResult to analyze
            
        Returns:
            List of action item dictionaries
        """
        action_items = []
        
        # Missing files
        for missing_dataset in correlation_result.missing_datasets:
            action_items.append({
                'type': 'missing_file',
                'priority': 'high',
                'icon': '📁',
                'title': f'Add {missing_dataset}.csv',
                'description': f'Upload or select a file named "{missing_dataset}.csv" for the {missing_dataset} dataset',
                'action': 'upload_file'
            })
        
        # Extra files
        for unmatched_file in correlation_result.unmatched_files:
            file_name = Path(unmatched_file).name
            action_items.append({
                'type': 'extra_file',
                'priority': 'medium',
                'icon': '❓',
                'title': f'Review {file_name}',
                'description': f'File "{file_name}" does not match any dataset name - remove or rename it',
                'action': 'review_file'
            })
        
        # Column issues
        for correlation in correlation_result.dataset_correlations:
            if correlation.is_exact_match and correlation.missing_columns:
                file_name = Path(correlation.file_path).name
                action_items.append({
                    'type': 'missing_columns',
                    'priority': 'high',
                    'icon': '📊',
                    'title': f'Fix columns in {file_name}',
                    'description': f'Add missing columns: {", ".join(correlation.missing_columns)}',
                    'action': 'fix_columns'
                })
        
        return action_items


class TemplateFilters:
    """Template filters for correlation visualization."""
    
    @staticmethod
    def status_badge(status: str) -> str:
        """Template filter for status badge classes."""
        return CorrelationVisualizationHelper._get_status_badge_class(status)
    
    @staticmethod
    def basename(file_path: str) -> str:
        """Template filter to get basename of file path."""
        return Path(file_path).name
    
    @staticmethod
    def pluralize(count: int, singular: str = '', plural: str = 's') -> str:
        """Template filter for pluralization."""
        if count == 1:
            return singular
        return plural