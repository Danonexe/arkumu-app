"""
Tests for structured error handling and persistence system.
Validates comprehensive error tracking, validation issue management, and communication.
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from django.utils import timezone

from arkumu.importer.models.error_tracking import (
    ImportPipelineError,
    MappingValidationIssue,
    FileProcessingIssue,
    ExecutionPhaseError,
    ErrorCommunication
)
from arkumu.importer.services.error_handling.error_manager import (
    ErrorManager,
    ValidationIssueManager,
    ErrorReportingService
)
from arkumu.importer.services.error_handling.pipeline_integration import (
    PipelineErrorHandler,
    StructuredImportPipeline
)
from arkumu.importer.services.mapping_consumer.validation import ValidationResult


class TestErrorManager:
    """Test suite for ErrorManager functionality"""
    
    def test_record_error_creates_new_error(self, test_ingest_session):
        """Test recording a new error"""
        error_manager = ErrorManager(test_ingest_session)
        
        error_record = error_manager.record_error(
            error_code="TEST_ERROR_001",
            error_type="ValueError",
            error_message="Test error message",
            error_category="validation",
            severity="error",
            context={"test_key": "test_value"}
        )
        
        assert error_record.error_code == "TEST_ERROR_001"
        assert error_record.error_type == "ValueError"
        assert error_record.error_message == "Test error message"
        assert error_record.error_category == "validation"
        assert error_record.severity == "error"
        assert error_record.ingest_session == test_ingest_session
        assert error_record.context_data == {"test_key": "test_value"}
        assert error_record.occurrence_count == 1
    
    def test_record_error_increments_existing_error(self, test_ingest_session):
        """Test that duplicate errors increment occurrence count"""
        error_manager = ErrorManager(test_ingest_session)
        
        # Create first error
        error1 = error_manager.record_error(
            error_code="DUPLICATE_ERROR",
            error_type="ValueError",
            error_message="Duplicate error",
            error_category="validation",
            severity="error"
        )
        
        # Create same error again
        error2 = error_manager.record_error(
            error_code="DUPLICATE_ERROR",
            error_type="ValueError",
            error_message="Duplicate error",
            error_category="validation",
            severity="error"
        )
        
        # Should be the same record with incremented count
        assert error1.id == error2.id
        assert error2.occurrence_count == 2
    
    def test_record_validation_issue(self):
        """Test recording a validation issue"""
        error_manager = ErrorManager()
        mapping_id = uuid.uuid4()
        
        issue = error_manager.record_validation_issue(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org",
            issue_type="missing_field",
            severity="critical",
            issue_code="MISSING_FIELD_001",
            issue_message="Required field 'name' is missing",
            dataset_name="test_dataset",
            field_path="workspace_columns.test_dataset.name"
        )
        
        assert issue.mapping_id == mapping_id
        assert issue.mapping_name == "Test Mapping"
        assert issue.organization == "test_org"
        assert issue.issue_type == "missing_field"
        assert issue.severity == "critical"
        assert issue.issue_code == "MISSING_FIELD_001"
        assert issue.is_blocking is True
    
    def test_record_file_issue(self, test_ingest_session):
        """Test recording a file processing issue"""
        error_manager = ErrorManager(test_ingest_session)
        
        issue = error_manager.record_file_issue(
            file_path="/path/to/test.csv",
            issue_type="encoding_error",
            issue_message="File has invalid UTF-8 encoding",
            file_size=1024,
            detected_encoding="latin-1"
        )
        
        assert issue.ingest_session == test_ingest_session
        assert issue.file_path == "/path/to/test.csv"
        assert issue.file_name == "test.csv"
        assert issue.issue_type == "encoding_error"
        assert issue.issue_message == "File has invalid UTF-8 encoding"
        assert issue.file_size == 1024
    
    def test_record_phase_error(self, test_ingest_session):
        """Test recording an execution phase error"""
        error_manager = ErrorManager(test_ingest_session)
        
        error = error_manager.record_phase_error(
            phase="data_processing",
            error_type="ValueError",
            error_message="Invalid data type in column 'age'",
            dataset_name="people",
            rows_affected=5,
            can_continue=True
        )
        
        assert error.ingest_session == test_ingest_session
        assert error.phase == "data_processing"
        assert error.error_type == "ValueError"
        assert error.error_message == "Invalid data type in column 'age'"
        assert error.dataset_name == "people"
        assert error.rows_affected == 5
        assert error.can_continue is True
    
    def test_get_error_summary(self, test_ingest_session):
        """Test getting error summary for a session"""
        error_manager = ErrorManager(test_ingest_session)
        
        # Create different types of errors
        error_manager.record_error(
            error_code="CRITICAL_ERROR",
            error_type="SystemError",
            error_message="Critical system error",
            severity="critical"
        )
        
        error_manager.record_error(
            error_code="WARNING_ERROR",
            error_type="UserWarning",
            error_message="Warning message",
            severity="warning"
        )
        
        error_manager.record_file_issue(
            file_path="/test.csv",
            issue_type="format_error",
            issue_message="Invalid CSV format"
        )
        
        summary = error_manager.get_error_summary()
        
        assert summary['total_errors'] == 2
        assert summary['file_issues'] == 1
        assert summary['severity_breakdown']['critical'] == 1
        assert summary['severity_breakdown']['warning'] == 1
        assert summary['has_blocking_errors'] is True
    
    @patch('arkumu.importer.services.error_handling.error_manager.send_mail')
    def test_notify_error(self, mock_send_mail, test_ingest_session):
        """Test error notification"""
        error_manager = ErrorManager(test_ingest_session)
        
        error = error_manager.record_error(
            error_code="NOTIFY_ERROR",
            error_type="TestError",
            error_message="Test notification error",
            severity="critical"
        )
        
        communications = error_manager.notify_error(
            error=error,
            recipients=["admin@test.com", "user@test.com"]
        )
        
        assert len(communications) == 2
        assert communications[0].recipient == "admin@test.com"
        assert communications[1].recipient == "user@test.com"
        assert communications[0].status == "sent"
        assert mock_send_mail.call_count == 2


class TestValidationIssueManager:
    """Test suite for ValidationIssueManager functionality"""
    
    def test_record_issue(self):
        """Test recording a validation issue"""
        mapping_id = uuid.uuid4()
        issue_manager = ValidationIssueManager(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org"
        )
        
        issue = issue_manager.record_issue(
            issue_type="invalid_reference",
            severity="major",
            issue_code="INVALID_REF_001",
            issue_message="Reference to non-existent column",
            dataset_name="people",
            column_name="invalid_column"
        )
        
        assert issue.mapping_id == mapping_id
        assert issue.issue_type == "invalid_reference"
        assert issue.severity == "major"
        assert issue.dataset_name == "people"
        assert issue.column_name == "invalid_column"
    
    def test_get_blocking_issues(self):
        """Test getting blocking issues"""
        mapping_id = uuid.uuid4()
        issue_manager = ValidationIssueManager(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org"
        )
        
        # Create blocking issue
        issue_manager.record_issue(
            issue_type="missing_field",
            severity="blocker",
            issue_code="BLOCKER_001",
            issue_message="Critical blocking issue"
        )
        
        # Create non-blocking issue
        issue_manager.record_issue(
            issue_type="best_practice",
            severity="minor",
            issue_code="MINOR_001",
            issue_message="Minor best practice issue"
        )
        
        blocking_issues = issue_manager.get_blocking_issues()
        
        assert len(blocking_issues) == 1
        assert blocking_issues[0].severity == "blocker"
    
    def test_get_issue_summary(self):
        """Test getting issue summary"""
        mapping_id = uuid.uuid4()
        issue_manager = ValidationIssueManager(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org"
        )
        
        # Create various issues
        issue_manager.record_issue(
            issue_type="missing_field",
            severity="blocker",
            issue_code="BLOCKER_001",
            issue_message="Blocking issue"
        )
        
        issue_manager.record_issue(
            issue_type="invalid_type",
            severity="major",
            issue_code="MAJOR_001",
            issue_message="Major issue"
        )
        
        summary = issue_manager.get_issue_summary()
        
        assert summary['total_issues'] == 2
        assert summary['blocking_issues'] == 1
        assert summary['severity_breakdown']['blocker'] == 1
        assert summary['severity_breakdown']['major'] == 1
        assert summary['can_execute'] is False


class TestPipelineErrorHandler:
    """Test suite for PipelineErrorHandler functionality"""
    
    def test_error_context_records_errors(self, test_ingest_session):
        """Test error context records errors properly"""
        error_handler = PipelineErrorHandler(test_ingest_session)
        
        with error_handler.error_context("test_phase", "test_category") as ctx:
            ctx.record_error(
                error_code="CONTEXT_ERROR",
                error_message="Error in context",
                severity="error"
            )
            
            ctx.record_warning(
                warning_code="CONTEXT_WARNING",
                warning_message="Warning in context"
            )
        
        assert ctx.has_errors() is True
        assert len(ctx.errors_recorded) == 1
        assert len(ctx.warnings_recorded) == 1
        
        error_summary = ctx.get_error_summary()
        assert error_summary['phase'] == "test_phase"
        assert error_summary['error_count'] == 1
        assert error_summary['warning_count'] == 1
    
    def test_error_context_handles_exceptions(self, test_ingest_session):
        """Test error context handles exceptions"""
        error_handler = PipelineErrorHandler(test_ingest_session)
        
        with pytest.raises(ValueError):
            with error_handler.error_context("test_phase", "test_category") as ctx:
                raise ValueError("Test exception")
        
        # Check that error was recorded
        errors = error_handler.error_manager.get_session_errors()
        assert len(errors['pipeline_errors']) == 1
        assert errors['pipeline_errors'][0].error_code == "TEST_PHASE_ERROR"
        assert errors['pipeline_errors'][0].error_type == "ValueError"
    
    def test_handle_file_error(self, test_ingest_session):
        """Test handling file errors"""
        error_handler = PipelineErrorHandler(test_ingest_session)
        
        file_error = FileNotFoundError("Test file not found")
        error_handler.handle_file_error("/path/to/test.csv", file_error)
        
        errors = error_handler.error_manager.get_session_errors()
        assert len(errors['file_issues']) == 1
        assert errors['file_issues'][0].issue_type == "file_not_found"
        assert errors['file_issues'][0].file_path == "/path/to/test.csv"
    
    def test_handle_validation_errors(self, test_ingest_session):
        """Test handling validation errors"""
        error_handler = PipelineErrorHandler(test_ingest_session)
        
        # Create mock validation result
        validation_result = ValidationResult(
            is_valid=False,
            errors=["Missing required field", "Invalid reference"],
            warnings=["Performance warning"],
            summary="Validation failed"
        )
        
        mapping_id = str(uuid.uuid4())
        issue_manager = error_handler.handle_validation_errors(
            validation_result=validation_result,
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org"
        )
        
        assert isinstance(issue_manager, ValidationIssueManager)
        
        # Check that issues were recorded
        issues = MappingValidationIssue.objects.filter(mapping_id=mapping_id)
        assert len(issues) == 3  # 2 errors + 1 warning
        
        blocker_issues = [i for i in issues if i.severity == "blocker"]
        minor_issues = [i for i in issues if i.severity == "minor"]
        
        assert len(blocker_issues) == 2
        assert len(minor_issues) == 1
    
    def test_get_execution_readiness(self):
        """Test getting execution readiness"""
        mapping_id = str(uuid.uuid4())
        
        # Create blocking issue
        MappingValidationIssue.objects.create(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org",
            issue_type="missing_field",
            severity="blocker",
            issue_code="BLOCKER_001",
            issue_message="Blocking issue"
        )
        
        error_handler = PipelineErrorHandler()
        readiness = error_handler.get_execution_readiness(mapping_id)
        
        assert readiness['ready_for_execution'] is False
        assert len(readiness['blocking_issues']) == 1
        assert readiness['total_issues'] == 1


class TestStructuredImportPipeline:
    """Test suite for StructuredImportPipeline functionality"""
    
    def test_execute_with_error_handling_success(self, test_ingest_session):
        """Test successful execution with error handling"""
        pipeline = StructuredImportPipeline(test_ingest_session)
        
        # Mock import function
        def mock_import_function():
            return {"success": True, "rows_processed": 100}
        
        result = pipeline.execute_with_error_handling(mock_import_function)
        
        assert result['success'] is True
        assert result['data'] == {"success": True, "rows_processed": 100}
        assert len(result['errors']) == 0
    
    def test_execute_with_error_handling_failure(self, test_ingest_session):
        """Test execution with error handling when function fails"""
        pipeline = StructuredImportPipeline(test_ingest_session)
        
        # Mock import function that fails
        def mock_import_function():
            raise ValueError("Import failed")
        
        result = pipeline.execute_with_error_handling(mock_import_function)
        
        assert result['success'] is False
        assert result['data'] is None
        assert len(result['errors']) == 1
        assert result['errors'][0]['type'] == "ValueError"
        assert result['errors'][0]['message'] == "Import failed"
    
    def test_validate_before_execution(self, test_ingest_session):
        """Test validation before execution"""
        pipeline = StructuredImportPipeline(test_ingest_session)
        
        # Create mock validation result
        validation_result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor warning"],
            summary="Validation passed"
        )
        
        mapping_id = str(uuid.uuid4())
        result = pipeline.validate_before_execution(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org",
            validation_result=validation_result
        )
        
        assert result['validation_completed'] is True
        assert result['can_proceed'] is True
        assert result['execution_readiness']['ready_for_execution'] is True


class TestErrorReportingService:
    """Test suite for ErrorReportingService functionality"""
    
    def test_generate_session_report(self, test_ingest_session):
        """Test generating session error report"""
        error_manager = ErrorManager(test_ingest_session)
        
        # Create some errors
        error_manager.record_error(
            error_code="REPORT_ERROR",
            error_type="TestError",
            error_message="Test error for report",
            severity="error"
        )
        
        report = ErrorReportingService.generate_session_report(test_ingest_session)
        
        assert report['session_id'] == str(test_ingest_session.id)
        assert report['dataset_name'] == test_ingest_session.dataset_name
        assert report['organization'] == test_ingest_session.organization
        assert report['status'] == test_ingest_session.status
        assert 'error_summary' in report
        assert 'errors' in report
        assert 'recommendations' in report
    
    def test_generate_mapping_report(self):
        """Test generating mapping validation report"""
        mapping_id = uuid.uuid4()
        
        # Create validation issue
        MappingValidationIssue.objects.create(
            mapping_id=mapping_id,
            mapping_name="Test Mapping",
            organization="test_org",
            issue_type="missing_field",
            severity="critical",
            issue_code="MISSING_001",
            issue_message="Missing required field"
        )
        
        report = ErrorReportingService.generate_mapping_report(mapping_id)
        
        assert report['mapping_id'] == str(mapping_id)
        assert report['mapping_name'] == "Test Mapping"
        assert report['organization'] == "test_org"
        assert report['total_issues'] == 1
        assert report['blocking_issues'] == 1
        assert report['can_execute'] is False
        assert 'by_type' in report
        assert 'by_severity' in report


class TestErrorCommunication:
    """Test suite for ErrorCommunication functionality"""
    
    def test_error_communication_creation(self, test_ingest_session):
        """Test creating error communication"""
        error_manager = ErrorManager(test_ingest_session)
        
        # Create error
        error = error_manager.record_error(
            error_code="COMM_ERROR",
            error_type="TestError",
            error_message="Test communication error",
            severity="critical"
        )
        
        # Create communication
        comm = ErrorCommunication.objects.create(
            pipeline_error=error,
            communication_type="email",
            recipient="test@example.com",
            subject="Test Error Notification",
            message="Test error occurred"
        )
        
        assert comm.pipeline_error == error
        assert comm.communication_type == "email"
        assert comm.recipient == "test@example.com"
        assert comm.status == "pending"
    
    def test_mark_communication_sent(self, test_ingest_session):
        """Test marking communication as sent"""
        error_manager = ErrorManager(test_ingest_session)
        
        error = error_manager.record_error(
            error_code="SENT_ERROR",
            error_type="TestError",
            error_message="Test sent error",
            severity="error"
        )
        
        comm = ErrorCommunication.objects.create(
            pipeline_error=error,
            communication_type="email",
            recipient="test@example.com",
            subject="Test",
            message="Test"
        )
        
        comm.mark_sent("external_123")
        
        assert comm.status == "sent"
        assert comm.sent_at is not None
        assert comm.external_id == "external_123"