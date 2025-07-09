"""
Integration helpers for the pre-execution validation service.

This module provides helper functions and classes to integrate the pre-execution
validation service with existing components in the import pipeline.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple

from .pre_execution_validator import PreExecutionValidator
from .validation_result import (
    PreExecutionValidationResult,
    ValidationMode,
    ValidationSeverity,
    ValidationCategory
)

# Import existing services
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.file_matching.file_dataset_matcher import FileDatasetMatcher
from arkumu.importer.services.validation.validation_utils import ValidationReport

logger = logging.getLogger(__name__)


class ValidationIntegrationHelper:
    """
    Helper class for integrating pre-execution validation with existing services.
    """
    
    def __init__(self, 
                 mapping_adapter: Optional[MappingAdapter] = None,
                 file_matcher: Optional[FileDatasetMatcher] = None):
        """
        Initialize the integration helper.
        
        Args:
            mapping_adapter: Optional mapping adapter instance
            file_matcher: Optional file matcher instance
        """
        self.mapping_adapter = mapping_adapter or MappingAdapter()
        self.file_matcher = file_matcher or FileDatasetMatcher()
        self.validator = PreExecutionValidator(
            mapping_adapter=self.mapping_adapter,
            file_matcher=self.file_matcher
        )
    
    def validate_mapping_by_id(self, 
                             mapping_id: int, 
                             file_paths: List[str],
                             validation_mode: ValidationMode = ValidationMode.STRICT) -> PreExecutionValidationResult:
        """
        Validate mapping by database ID.
        
        Args:
            mapping_id: Database ID of the mapping
            file_paths: List of file paths to validate
            validation_mode: Validation mode to use
            
        Returns:
            PreExecutionValidationResult with validation results
        """
        try:
            # Load mapping configuration from database
            mapping_config = self.mapping_adapter.load_mapping_config(mapping_id)
            
            # Set validation mode
            self.validator.validation_mode = validation_mode
            
            # Perform validation
            result = self.validator.validate_mapping_execution(mapping_config, file_paths)
            
            # Add mapping metadata to result
            result.mapping_id = mapping_id
            result.mapping_name = mapping_config.get('_metadata', {}).get('mapping_name', 'Unknown')
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to validate mapping {mapping_id}: {str(e)}")
            # Return a failed result
            result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=validation_mode,
                overall_confidence=0.0
            )
            result.add_issue(ValidationIssue(
                code="MAPPING_LOAD_ERROR",
                severity=ValidationSeverity.CRITICAL,
                category=ValidationCategory.CONFIGURATION,
                message=f"Failed to load mapping {mapping_id}: {str(e)}"
            ))
            return result
    
    def validate_with_file_matching(self, 
                                  mapping_id: int, 
                                  file_paths: List[str],
                                  base_directory: Optional[str] = None) -> Tuple[PreExecutionValidationResult, Dict[str, Any]]:
        """
        Validate mapping with automatic file-to-dataset matching.
        
        Args:
            mapping_id: Database ID of the mapping
            file_paths: List of file paths to validate
            base_directory: Optional base directory for file resolution
            
        Returns:
            Tuple of (validation_result, matching_result)
        """
        try:
            # Load mapping and translate to execution config
            execution_config = self.mapping_adapter.translate_to_execution_config(mapping_id)
            
            # Perform file matching
            matching_result = self.file_matcher.match_files_to_datasets(
                file_paths, execution_config, base_directory
            )
            
            # Get mapping config for validation
            mapping_config = self.mapping_adapter.load_mapping_config(mapping_id)
            
            # Validate with matched files
            validation_result = self.validator.validate_mapping_execution(
                mapping_config, 
                [match.file_info.file_path for match in matching_result.successful_matches]
            )
            
            # Add matching information to validation result
            validation_result.file_matching_result = matching_result
            
            return validation_result, matching_result.to_dict() if hasattr(matching_result, 'to_dict') else {}
            
        except Exception as e:
            logger.error(f"Failed to validate with file matching: {str(e)}")
            # Return failed results
            validation_result = PreExecutionValidationResult(
                is_valid=False,
                validation_mode=ValidationMode.STRICT,
                overall_confidence=0.0
            )
            validation_result.add_issue(ValidationIssue(
                code="VALIDATION_WITH_MATCHING_ERROR",
                severity=ValidationSeverity.CRITICAL,
                category=ValidationCategory.CONFIGURATION,
                message=f"Failed to validate with file matching: {str(e)}"
            ))
            return validation_result, {"error": str(e)}
    
    def convert_to_legacy_validation_report(self, 
                                          result: PreExecutionValidationResult) -> ValidationReport:
        """
        Convert PreExecutionValidationResult to legacy ValidationReport format.
        
        Args:
            result: PreExecutionValidationResult to convert
            
        Returns:
            ValidationReport compatible with existing code
        """
        report = ValidationReport()
        
        # Convert issues to legacy format
        for issue in result.all_issues:
            if issue.severity == ValidationSeverity.ERROR:
                report.add_error(
                    error_type=issue.code,
                    message=issue.message,
                    field=issue.column_name,
                    row=issue.line_number
                )
            elif issue.severity == ValidationSeverity.WARNING:
                report.add_warning(
                    error_type=issue.code,
                    message=issue.message,
                    field=issue.column_name,
                    row=issue.line_number
                )
            elif issue.severity == ValidationSeverity.INFO:
                report.add_info(
                    info_type=issue.code,
                    message=issue.message,
                    field=issue.column_name,
                    row=issue.line_number
                )
        
        # Add summary information
        report.details.update({
            'pre_execution_validation': {
                'overall_confidence': result.overall_confidence,
                'validation_mode': result.validation_mode.value,
                'resource_estimate': result.resource_estimate.to_dict() if result.resource_estimate else None,
                'execution_recommendations': result.execution_recommendations,
                'required_actions': result.required_actions
            }
        })
        
        return report
    
    def get_validation_summary_for_api(self, 
                                     result: PreExecutionValidationResult) -> Dict[str, Any]:
        """
        Get a validation summary suitable for API responses.
        
        Args:
            result: PreExecutionValidationResult to summarize
            
        Returns:
            Dictionary with API-friendly validation summary
        """
        return {
            'status': 'passed' if result.is_valid else 'failed',
            'confidence': result.overall_confidence,
            'validation_mode': result.validation_mode.value,
            'summary': result.get_summary(),
            'issues': {
                'total': len(result.all_issues),
                'errors': len(result.errors),
                'warnings': len(result.warnings),
                'infos': len(result.infos)
            },
            'files_validated': len(result.file_validation_results),
            'execution_ready': result.is_valid and not result.has_blocking_issues(),
            'resource_estimate': {
                'execution_time': result.resource_estimate.estimated_execution_time if result.resource_estimate else None,
                'memory_usage': result.resource_estimate.estimated_memory_usage if result.resource_estimate else None,
                'complexity_score': result.resource_estimate.complexity_score if result.resource_estimate else None
            },
            'recommendations': result.execution_recommendations,
            'required_actions': result.required_actions,
            'validation_duration': result.validation_duration,
            'timestamp': result.validation_timestamp.isoformat()
        }
    
    def should_proceed_with_execution(self, 
                                    result: PreExecutionValidationResult,
                                    strict_mode: bool = True) -> Tuple[bool, List[str]]:
        """
        Determine if execution should proceed based on validation results.
        
        Args:
            result: PreExecutionValidationResult to evaluate
            strict_mode: Whether to use strict evaluation
            
        Returns:
            Tuple of (should_proceed, reasons)
        """
        reasons = []
        
        # Check overall validity
        if not result.is_valid:
            reasons.append("Validation failed")
            if strict_mode:
                return False, reasons
        
        # Check for blocking issues
        if result.has_blocking_issues():
            critical_issues = result.get_issues_by_severity(ValidationSeverity.CRITICAL)
            error_issues = result.get_issues_by_severity(ValidationSeverity.ERROR)
            
            if critical_issues:
                reasons.append(f"Critical issues found: {len(critical_issues)}")
                return False, reasons
            
            if error_issues and strict_mode:
                reasons.append(f"Error issues found: {len(error_issues)}")
                return False, reasons
        
        # Check confidence threshold
        if result.overall_confidence < 0.7:
            reasons.append(f"Low confidence score: {result.overall_confidence:.2f}")
            if strict_mode:
                return False, reasons
        
        # Check required actions
        if result.required_actions:
            reasons.append(f"Required actions not completed: {len(result.required_actions)}")
            if strict_mode:
                return False, reasons
        
        # If we get here, execution can proceed
        if result.warnings:
            reasons.append(f"Proceeding with {len(result.warnings)} warnings")
        
        return True, reasons or ["All validations passed"]


def validate_before_import(mapping_id: int, 
                         file_paths: List[str],
                         strict_mode: bool = True) -> Dict[str, Any]:
    """
    Convenience function for validating before import execution.
    
    Args:
        mapping_id: Database ID of the mapping
        file_paths: List of file paths to validate
        strict_mode: Whether to use strict validation
        
    Returns:
        Dictionary with validation results and execution decision
    """
    # Initialize integration helper
    helper = ValidationIntegrationHelper()
    
    # Determine validation mode
    validation_mode = ValidationMode.STRICT if strict_mode else ValidationMode.WARNING_ONLY
    
    # Perform validation
    result = helper.validate_mapping_by_id(mapping_id, file_paths, validation_mode)
    
    # Determine execution decision
    should_proceed, reasons = helper.should_proceed_with_execution(result, strict_mode)
    
    # Get API summary
    api_summary = helper.get_validation_summary_for_api(result)
    
    return {
        'validation_result': api_summary,
        'execution_decision': {
            'should_proceed': should_proceed,
            'reasons': reasons
        },
        'full_result': result.to_dict()
    }


def get_validation_report_for_ui(mapping_id: int, 
                               file_paths: List[str]) -> Dict[str, Any]:
    """
    Get a comprehensive validation report for UI display.
    
    Args:
        mapping_id: Database ID of the mapping
        file_paths: List of file paths to validate
        
    Returns:
        Dictionary with UI-friendly validation report
    """
    helper = ValidationIntegrationHelper()
    
    # Perform validation with file matching
    result, matching_result = helper.validate_with_file_matching(mapping_id, file_paths)
    
    # Organize issues by category
    issues_by_category = {}
    for category in ValidationCategory:
        category_issues = result.get_issues_by_category(category)
        if category_issues:
            issues_by_category[category.value] = [
                {
                    'code': issue.code,
                    'severity': issue.severity.value,
                    'message': issue.message,
                    'file_path': issue.file_path,
                    'column_name': issue.column_name,
                    'line_number': issue.line_number,
                    'suggested_fix': issue.suggested_fix
                }
                for issue in category_issues
            ]
    
    # Organize file validation results
    file_results = []
    for file_result in result.file_validation_results:
        file_results.append({
            'file_path': file_result.file_path,
            'is_valid': file_result.is_valid,
            'file_size': file_result.file_size,
            'column_count': file_result.column_count,
            'row_count': file_result.row_count,
            'missing_columns': file_result.missing_columns,
            'extra_columns': file_result.extra_columns,
            'issues_count': len(file_result.issues)
        })
    
    return {
        'overall_status': 'passed' if result.is_valid else 'failed',
        'confidence': result.overall_confidence,
        'summary': result.get_summary(),
        'file_results': file_results,
        'column_mapping': {
            'coverage_percentage': result.column_mapping_result.coverage_percentage if result.column_mapping_result else 0,
            'mapped_columns': result.column_mapping_result.mapped_columns if result.column_mapping_result else {},
            'unmapped_columns': result.column_mapping_result.unmapped_columns if result.column_mapping_result else [],
            'missing_required': result.column_mapping_result.missing_required_columns if result.column_mapping_result else []
        },
        'relationships': {
            'valid_count': len(result.relationship_validation_result.valid_relationships) if result.relationship_validation_result else 0,
            'invalid_count': len(result.relationship_validation_result.invalid_relationships) if result.relationship_validation_result else 0,
            'missing_dependencies': result.relationship_validation_result.missing_dependencies if result.relationship_validation_result else []
        },
        'resource_estimate': result.resource_estimate.to_dict() if result.resource_estimate else None,
        'issues_by_category': issues_by_category,
        'execution_recommendations': result.execution_recommendations,
        'required_actions': result.required_actions,
        'file_matching_result': matching_result
    }