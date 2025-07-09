"""
Error Manager Service for structured error handling and persistence.
Provides centralized error tracking, validation issue management, and communication.
"""

import logging
import traceback
from typing import Dict, List, Optional, Any, Union
from uuid import UUID
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from arkumu.importer.models.error_tracking import (
    ImportPipelineError,
    MappingValidationIssue,
    FileProcessingIssue,
    ExecutionPhaseError,
    ErrorCommunication
)
from arkumu.importer.models.ingest_sessions import IngestSession


logger = logging.getLogger(__name__)


class ErrorManager:
    """
    Centralized error management for the import pipeline.
    Handles error persistence, categorization, and communication.
    """
    
    def __init__(self, ingest_session: Optional[IngestSession] = None):
        self.ingest_session = ingest_session
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def record_error(
        self,
        error_code: str,
        error_type: str,
        error_message: str,
        error_category: str = 'system',
        severity: str = 'error',
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ImportPipelineError:
        """
        Record a pipeline error with full context.
        
        Args:
            error_code: Unique error code for categorization
            error_type: Python exception type or error class
            error_message: Human-readable error message
            error_category: Category of error (validation, file_processing, etc.)
            severity: Error severity (critical, error, warning, info)
            context: Additional context data
            **kwargs: Additional fields for the error record
        
        Returns:
            ImportPipelineError: Created or updated error record
        """
        
        # Get stack trace if available
        stack_trace = traceback.format_exc() if traceback.format_exc() != 'NoneType: None\n' else ""
        
        # Prepare error data
        error_data = {
            'error_category': error_category,
            'severity': severity,
            'ingest_session': self.ingest_session,
            'stack_trace': stack_trace,
            'context_data': context or {},
            **kwargs
        }
        
        # Create or increment existing error
        error_record = ImportPipelineError.create_or_increment(
            error_code=error_code,
            error_type=error_type,
            error_message=error_message,
            **error_data
        )
        
        # Log the error
        self.logger.error(
            f"Pipeline Error [{error_code}]: {error_message}",
            extra={
                'error_id': str(error_record.id),
                'error_category': error_category,
                'severity': severity,
                'context': context
            }
        )
        
        # Handle critical errors immediately
        if severity == 'critical':
            self._handle_critical_error(error_record)
        
        return error_record
    
    def record_validation_issue(
        self,
        mapping_id: UUID,
        mapping_name: str,
        organization: str,
        issue_type: str,
        severity: str,
        issue_code: str,
        issue_message: str,
        **kwargs
    ) -> MappingValidationIssue:
        """
        Record a mapping validation issue.
        
        Args:
            mapping_id: Associated mapping ID
            mapping_name: Mapping name for reference
            organization: Organization code
            issue_type: Type of validation issue
            severity: Issue severity
            issue_code: Unique issue code
            issue_message: Human-readable issue description
            **kwargs: Additional fields for the issue record
        
        Returns:
            MappingValidationIssue: Created issue record
        """
        
        issue = MappingValidationIssue.objects.create(
            mapping_id=mapping_id,
            mapping_name=mapping_name,
            organization=organization,
            issue_type=issue_type,
            severity=severity,
            issue_code=issue_code,
            issue_message=issue_message,
            **kwargs
        )
        
        self.logger.warning(
            f"Mapping Validation Issue [{issue_code}]: {issue_message}",
            extra={
                'mapping_id': str(mapping_id),
                'organization': organization,
                'severity': severity
            }
        )
        
        return issue
    
    def record_file_issue(
        self,
        file_path: str,
        issue_type: str,
        issue_message: str,
        **kwargs
    ) -> FileProcessingIssue:
        """
        Record a file processing issue.
        
        Args:
            file_path: Path to problematic file
            issue_type: Type of file issue
            issue_message: Issue description
            **kwargs: Additional fields for the issue record
        
        Returns:
            FileProcessingIssue: Created issue record
        """
        
        if not self.ingest_session:
            raise ValueError("IngestSession required for file issues")
        
        issue = FileProcessingIssue.objects.create(
            ingest_session=self.ingest_session,
            file_path=file_path,
            file_name=file_path.split('/')[-1],
            issue_type=issue_type,
            issue_message=issue_message,
            **kwargs
        )
        
        self.logger.error(
            f"File Processing Issue: {issue_message}",
            extra={
                'file_path': file_path,
                'issue_type': issue_type,
                'session_id': str(self.ingest_session.id)
            }
        )
        
        return issue
    
    def record_phase_error(
        self,
        phase: str,
        error_type: str,
        error_message: str,
        **kwargs
    ) -> ExecutionPhaseError:
        """
        Record an execution phase error.
        
        Args:
            phase: Execution phase where error occurred
            error_type: Python exception type
            error_message: Error message
            **kwargs: Additional fields for the error record
        
        Returns:
            ExecutionPhaseError: Created error record
        """
        
        if not self.ingest_session:
            raise ValueError("IngestSession required for phase errors")
        
        # Get stack trace
        stack_trace = traceback.format_exc() if traceback.format_exc() != 'NoneType: None\n' else ""
        
        error = ExecutionPhaseError.objects.create(
            ingest_session=self.ingest_session,
            phase=phase,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            **kwargs
        )
        
        self.logger.error(
            f"Execution Phase Error [{phase}]: {error_message}",
            extra={
                'phase': phase,
                'error_type': error_type,
                'session_id': str(self.ingest_session.id)
            }
        )
        
        return error
    
    def get_session_errors(self) -> Dict[str, List]:
        """
        Get all errors for the current ingest session.
        
        Returns:
            Dict containing categorized errors
        """
        
        if not self.ingest_session:
            return {}
        
        return {
            'pipeline_errors': list(self.ingest_session.pipeline_errors.all()),
            'file_issues': list(self.ingest_session.file_issues.all()),
            'phase_errors': list(self.ingest_session.phase_errors.all()),
        }
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get error summary for the current session.
        
        Returns:
            Dict containing error counts and severity breakdown
        """
        
        if not self.ingest_session:
            return {}
        
        pipeline_errors = self.ingest_session.pipeline_errors.all()
        file_issues = self.ingest_session.file_issues.all()
        phase_errors = self.ingest_session.phase_errors.all()
        
        # Count by severity
        severity_counts = {
            'critical': 0,
            'error': 0,
            'warning': 0,
            'info': 0
        }
        
        for error in pipeline_errors:
            severity_counts[error.severity] += 1
        
        return {
            'total_errors': len(pipeline_errors),
            'file_issues': len(file_issues),
            'phase_errors': len(phase_errors),
            'severity_breakdown': severity_counts,
            'has_blocking_errors': severity_counts['critical'] > 0,
            'latest_error': pipeline_errors.first() if pipeline_errors else None
        }
    
    def notify_error(
        self,
        error: ImportPipelineError,
        recipients: List[str],
        communication_type: str = 'email'
    ) -> List[ErrorCommunication]:
        """
        Send error notifications to specified recipients.
        
        Args:
            error: Error to notify about
            recipients: List of recipient email addresses
            communication_type: Type of communication
        
        Returns:
            List of ErrorCommunication records
        """
        
        communications = []
        
        for recipient in recipients:
            # Create communication record
            comm = ErrorCommunication.objects.create(
                pipeline_error=error,
                communication_type=communication_type,
                recipient=recipient,
                subject=f"Import Pipeline Error: {error.error_code}",
                message=self._format_error_message(error)
            )
            
            # Send notification
            try:
                if communication_type == 'email':
                    self._send_email_notification(comm)
                # Add other communication types as needed
                
                comm.mark_sent()
                
            except Exception as e:
                self.logger.error(f"Failed to send notification: {e}")
                comm.status = 'failed'
                comm.error_details = {'error': str(e)}
                comm.save()
            
            communications.append(comm)
        
        return communications
    
    def _handle_critical_error(self, error: ImportPipelineError):
        """Handle critical errors with immediate notifications"""
        
        # Get admin email addresses
        admin_emails = getattr(settings, 'IMPORT_PIPELINE_ADMIN_EMAILS', [])
        
        if admin_emails:
            self.notify_error(error, admin_emails)
    
    def _format_error_message(self, error: ImportPipelineError) -> str:
        """Format error message for notifications"""
        
        message = f"""
Import Pipeline Error Report

Error Code: {error.error_code}
Error Type: {error.error_type}
Severity: {error.severity.upper()}
Category: {error.error_category}

Message: {error.error_message}

Context:
- Session: {error.ingest_session.id if error.ingest_session else 'N/A'}
- Dataset: {error.dataset_name or 'N/A'}
- File: {error.file_path or 'N/A'}
- Row: {error.row_number or 'N/A'}

Occurred: {error.occurred_at}
Occurrence Count: {error.occurrence_count}

Stack Trace:
{error.stack_trace}

---
This is an automated notification from the Arkumu Import Pipeline.
"""
        
        return message.strip()
    
    def _send_email_notification(self, communication: ErrorCommunication):
        """Send email notification"""
        
        send_mail(
            subject=communication.subject,
            message=communication.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[communication.recipient],
            fail_silently=False
        )


class ValidationIssueManager:
    """
    Specialized manager for mapping validation issues.
    Provides validation-specific error handling and reporting.
    """
    
    def __init__(self, mapping_id: UUID, mapping_name: str, organization: str):
        self.mapping_id = mapping_id
        self.mapping_name = mapping_name
        self.organization = organization
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def record_issue(
        self,
        issue_type: str,
        severity: str,
        issue_code: str,
        issue_message: str,
        **kwargs
    ) -> MappingValidationIssue:
        """Record a validation issue"""
        
        return MappingValidationIssue.objects.create(
            mapping_id=self.mapping_id,
            mapping_name=self.mapping_name,
            organization=self.organization,
            issue_type=issue_type,
            severity=severity,
            issue_code=issue_code,
            issue_message=issue_message,
            **kwargs
        )
    
    def get_blocking_issues(self) -> List[MappingValidationIssue]:
        """Get issues that block execution"""
        
        return MappingValidationIssue.objects.filter(
            mapping_id=self.mapping_id,
            severity__in=['blocker', 'critical']
        ).order_by('-detected_at')
    
    def get_issue_summary(self) -> Dict[str, Any]:
        """Get validation issue summary"""
        
        issues = MappingValidationIssue.objects.filter(mapping_id=self.mapping_id)
        
        # Count by severity
        severity_counts = {
            'blocker': 0,
            'critical': 0,
            'major': 0,
            'minor': 0,
            'info': 0
        }
        
        for issue in issues:
            severity_counts[issue.severity] += 1
        
        blocking_count = severity_counts['blocker'] + severity_counts['critical']
        
        return {
            'total_issues': len(issues),
            'blocking_issues': blocking_count,
            'severity_breakdown': severity_counts,
            'can_execute': blocking_count == 0,
            'latest_issue': issues.first() if issues else None
        }
    
    def clear_previous_issues(self, validation_run_id: UUID):
        """Clear issues from previous validation runs"""
        
        MappingValidationIssue.objects.filter(
            mapping_id=self.mapping_id,
            validation_run_id=validation_run_id
        ).delete()


class ErrorReportingService:
    """
    Service for generating error reports and analytics.
    Provides insights into error patterns and trends.
    """
    
    @staticmethod
    def generate_session_report(ingest_session: IngestSession) -> Dict[str, Any]:
        """Generate comprehensive error report for a session"""
        
        error_manager = ErrorManager(ingest_session)
        errors = error_manager.get_session_errors()
        summary = error_manager.get_error_summary()
        
        return {
            'session_id': str(ingest_session.id),
            'dataset_name': ingest_session.dataset_name,
            'organization': ingest_session.organization,
            'status': ingest_session.status,
            'error_summary': summary,
            'errors': errors,
            'recommendations': ErrorReportingService._generate_recommendations(errors, summary)
        }
    
    @staticmethod
    def generate_mapping_report(mapping_id: UUID) -> Dict[str, Any]:
        """Generate validation report for a mapping"""
        
        issues = MappingValidationIssue.objects.filter(mapping_id=mapping_id)
        
        if not issues:
            return {'mapping_id': str(mapping_id), 'status': 'no_issues'}
        
        # Group by type and severity
        by_type = {}
        by_severity = {}
        
        for issue in issues:
            by_type.setdefault(issue.issue_type, []).append(issue)
            by_severity.setdefault(issue.severity, []).append(issue)
        
        return {
            'mapping_id': str(mapping_id),
            'mapping_name': issues.first().mapping_name,
            'organization': issues.first().organization,
            'total_issues': len(issues),
            'by_type': {k: len(v) for k, v in by_type.items()},
            'by_severity': {k: len(v) for k, v in by_severity.items()},
            'blocking_issues': len([i for i in issues if i.is_blocking]),
            'can_execute': not any(i.is_blocking for i in issues),
            'issues': list(issues)
        }
    
    @staticmethod
    def _generate_recommendations(errors: Dict[str, List], summary: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on error patterns"""
        
        recommendations = []
        
        if summary['has_blocking_errors']:
            recommendations.append("Address critical errors before retrying import")
        
        if summary['file_issues'] > 0:
            recommendations.append("Check file format and encoding")
        
        if summary['phase_errors'] > 0:
            recommendations.append("Review mapping configuration for data compatibility")
        
        return recommendations