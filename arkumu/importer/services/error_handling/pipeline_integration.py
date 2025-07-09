"""
Pipeline Integration Service for structured error handling.
Integrates error tracking with existing import pipeline components.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

from arkumu.importer.models.ingest_sessions import IngestSession
from arkumu.importer.models.error_tracking import ImportPipelineError, MappingValidationIssue
from arkumu.importer.services.error_handling.error_manager import ErrorManager, ValidationIssueManager
from arkumu.importer.services.mapping_consumer.validation import ValidationResult


logger = logging.getLogger(__name__)


class PipelineErrorHandler:
    """
    Integration layer for error handling in the import pipeline.
    Provides context managers and decorators for structured error tracking.
    """
    
    def __init__(self, ingest_session: Optional[IngestSession] = None):
        self.ingest_session = ingest_session
        self.error_manager = ErrorManager(ingest_session)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @contextmanager
    def error_context(self, 
                     phase: str, 
                     error_category: str = 'execution',
                     continue_on_error: bool = False):
        """
        Context manager for tracking errors in specific pipeline phases.
        
        Args:
            phase: Pipeline phase name
            error_category: Category of errors in this phase
            continue_on_error: Whether to continue execution after errors
        
        Yields:
            ErrorContext: Context for error tracking
        """
        
        context = ErrorContext(
            phase=phase,
            error_manager=self.error_manager,
            error_category=error_category,
            continue_on_error=continue_on_error
        )
        
        try:
            yield context
        except Exception as e:
            # Record the error
            error_record = self.error_manager.record_error(
                error_code=f"{phase.upper()}_ERROR",
                error_type=type(e).__name__,
                error_message=str(e),
                error_category=error_category,
                severity='critical'
            )
            
            # Record phase-specific error
            if self.ingest_session:
                self.error_manager.record_phase_error(
                    phase=phase,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    can_continue=continue_on_error
                )
            
            if not continue_on_error:
                raise
            
            self.logger.warning(f"Continuing execution after error in {phase}: {e}")
    
    def handle_file_error(self, file_path: str, error: Exception, **kwargs):
        """Handle file processing errors"""
        
        # Determine issue type based on exception
        issue_type = self._classify_file_error(error)
        
        self.error_manager.record_file_issue(
            file_path=file_path,
            issue_type=issue_type,
            issue_message=str(error),
            error_details={'exception_type': type(error).__name__},
            **kwargs
        )
    
    def handle_validation_errors(self, validation_result: ValidationResult, 
                               mapping_id: str, mapping_name: str, 
                               organization: str) -> ValidationIssueManager:
        """
        Handle validation errors from mapping validation.
        
        Args:
            validation_result: Validation result from mapping validation
            mapping_id: ID of the mapping being validated
            mapping_name: Name of the mapping
            organization: Organization code
        
        Returns:
            ValidationIssueManager: Manager for handling validation issues
        """
        
        issue_manager = ValidationIssueManager(
            mapping_id=uuid.UUID(mapping_id),
            mapping_name=mapping_name,
            organization=organization
        )
        
        # Generate validation run ID
        validation_run_id = uuid.uuid4()
        
        # Clear previous issues for this validation run
        issue_manager.clear_previous_issues(validation_run_id)
        
        # Record errors
        for error in validation_result.errors:
            issue_manager.record_issue(
                issue_type=self._classify_validation_error(error),
                severity='blocker',
                issue_code=f"VALIDATION_ERROR_{hash(error) % 10000}",
                issue_message=error,
                validation_run_id=validation_run_id
            )
        
        # Record warnings
        for warning in validation_result.warnings:
            issue_manager.record_issue(
                issue_type=self._classify_validation_warning(warning),
                severity='minor',
                issue_code=f"VALIDATION_WARNING_{hash(warning) % 10000}",
                issue_message=warning,
                validation_run_id=validation_run_id
            )
        
        return issue_manager
    
    def get_execution_readiness(self, mapping_id: str) -> Dict[str, Any]:
        """
        Check if mapping is ready for execution based on validation issues.
        
        Args:
            mapping_id: ID of the mapping to check
        
        Returns:
            Dict containing readiness status and issues
        """
        
        issues = MappingValidationIssue.objects.filter(mapping_id=mapping_id)
        
        blocking_issues = [i for i in issues if i.is_blocking]
        
        return {
            'ready_for_execution': len(blocking_issues) == 0,
            'blocking_issues': blocking_issues,
            'total_issues': len(issues),
            'issue_summary': self._summarize_issues(issues)
        }
    
    def _classify_file_error(self, error: Exception) -> str:
        """Classify file error by exception type"""
        
        error_type = type(error).__name__
        
        classification_map = {
            'FileNotFoundError': 'file_not_found',
            'PermissionError': 'permission_denied',
            'UnicodeDecodeError': 'encoding_error',
            'UnicodeError': 'encoding_error',
            'OSError': 'file_corrupted',
            'IOError': 'file_corrupted',
            'ValueError': 'format_error',
            'ParseError': 'parsing_error',
            'ClientError': 'network_error',
            'BotoCoreError': 'network_error',
        }
        
        return classification_map.get(error_type, 'parsing_error')
    
    def _classify_validation_error(self, error_message: str) -> str:
        """Classify validation error by message content"""
        
        message_lower = error_message.lower()
        
        if 'missing' in message_lower and 'field' in message_lower:
            return 'missing_field'
        elif 'invalid' in message_lower and 'type' in message_lower:
            return 'invalid_type'
        elif 'reference' in message_lower or 'not found' in message_lower:
            return 'invalid_reference'
        elif 'circular' in message_lower or 'cycle' in message_lower:
            return 'circular_dependency'
        elif 'inconsistent' in message_lower:
            return 'inconsistent_config'
        else:
            return 'invalid_type'
    
    def _classify_validation_warning(self, warning_message: str) -> str:
        """Classify validation warning by message content"""
        
        message_lower = warning_message.lower()
        
        if 'performance' in message_lower:
            return 'performance_warning'
        elif 'practice' in message_lower or 'recommend' in message_lower:
            return 'best_practice'
        else:
            return 'best_practice'
    
    def _summarize_issues(self, issues: List[MappingValidationIssue]) -> Dict[str, Any]:
        """Summarize validation issues"""
        
        by_type = {}
        by_severity = {}
        
        for issue in issues:
            by_type.setdefault(issue.issue_type, 0)
            by_type[issue.issue_type] += 1
            
            by_severity.setdefault(issue.severity, 0)
            by_severity[issue.severity] += 1
        
        return {
            'by_type': by_type,
            'by_severity': by_severity,
            'total': len(issues)
        }


class ErrorContext:
    """
    Context object for error tracking within pipeline phases.
    Provides methods for recording phase-specific errors and warnings.
    """
    
    def __init__(self, phase: str, error_manager: ErrorManager, 
                 error_category: str, continue_on_error: bool):
        self.phase = phase
        self.error_manager = error_manager
        self.error_category = error_category
        self.continue_on_error = continue_on_error
        self.errors_recorded = []
        self.warnings_recorded = []
    
    def record_error(self, error_code: str, error_message: str, 
                    severity: str = 'error', **kwargs):
        """Record an error in the current phase"""
        
        error_record = self.error_manager.record_error(
            error_code=error_code,
            error_type=kwargs.get('error_type', 'PhaseError'),
            error_message=error_message,
            error_category=self.error_category,
            severity=severity,
            **kwargs
        )
        
        self.errors_recorded.append(error_record)
        return error_record
    
    def record_warning(self, warning_code: str, warning_message: str, **kwargs):
        """Record a warning in the current phase"""
        
        warning_record = self.error_manager.record_error(
            error_code=warning_code,
            error_type=kwargs.get('error_type', 'PhaseWarning'),
            error_message=warning_message,
            error_category=self.error_category,
            severity='warning',
            **kwargs
        )
        
        self.warnings_recorded.append(warning_record)
        return warning_record
    
    def record_row_error(self, row_number: int, error_message: str, 
                        column_name: str = None, **kwargs):
        """Record a row-specific error"""
        
        return self.record_error(
            error_code=f"{self.phase.upper()}_ROW_ERROR",
            error_message=error_message,
            row_number=row_number,
            column_name=column_name,
            **kwargs
        )
    
    def has_errors(self) -> bool:
        """Check if any errors were recorded"""
        return len(self.errors_recorded) > 0
    
    def has_critical_errors(self) -> bool:
        """Check if any critical errors were recorded"""
        return any(e.severity == 'critical' for e in self.errors_recorded)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors recorded in this context"""
        
        return {
            'phase': self.phase,
            'error_count': len(self.errors_recorded),
            'warning_count': len(self.warnings_recorded),
            'has_critical': self.has_critical_errors(),
            'errors': self.errors_recorded,
            'warnings': self.warnings_recorded
        }


class StructuredImportPipeline:
    """
    Wrapper for import pipeline with structured error handling.
    Provides a high-level interface for running imports with comprehensive error tracking.
    """
    
    def __init__(self, ingest_session: IngestSession):
        self.ingest_session = ingest_session
        self.error_handler = PipelineErrorHandler(ingest_session)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def execute_with_error_handling(self, import_function, *args, **kwargs):
        """
        Execute import function with comprehensive error handling.
        
        Args:
            import_function: Function to execute
            *args: Arguments for import function
            **kwargs: Keyword arguments for import function
        
        Returns:
            Result of import function with error information
        """
        
        result = {
            'success': False,
            'data': None,
            'errors': [],
            'warnings': [],
            'summary': {}
        }
        
        try:
            # Execute the import function
            with self.error_handler.error_context('execution', 'system') as ctx:
                result['data'] = import_function(*args, **kwargs)
                result['success'] = not ctx.has_critical_errors()
                
                # Collect errors and warnings
                error_summary = ctx.get_error_summary()
                result['errors'] = error_summary['errors']
                result['warnings'] = error_summary['warnings']
        
        except Exception as e:
            self.logger.error(f"Import execution failed: {e}")
            result['success'] = False
            result['errors'].append({
                'type': type(e).__name__,
                'message': str(e),
                'phase': 'execution'
            })
        
        finally:
            # Generate final summary
            result['summary'] = self.error_handler.error_manager.get_error_summary()
        
        return result
    
    def validate_before_execution(self, mapping_id: str, mapping_name: str, 
                                organization: str, validation_result: ValidationResult):
        """
        Validate mapping before execution and record issues.
        
        Args:
            mapping_id: ID of the mapping
            mapping_name: Name of the mapping
            organization: Organization code
            validation_result: Validation result
        
        Returns:
            Dict containing validation status and readiness
        """
        
        # Handle validation errors
        issue_manager = self.error_handler.handle_validation_errors(
            validation_result=validation_result,
            mapping_id=mapping_id,
            mapping_name=mapping_name,
            organization=organization
        )
        
        # Check execution readiness
        readiness = self.error_handler.get_execution_readiness(mapping_id)
        
        return {
            'validation_completed': True,
            'issues_recorded': issue_manager.get_issue_summary(),
            'execution_readiness': readiness,
            'can_proceed': readiness['ready_for_execution']
        }