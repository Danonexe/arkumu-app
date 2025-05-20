import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ValidationError:
    """Class to represent a validation error"""
    def __init__(self, error_type: str, message: str, rule: Optional[Dict] = None, 
                 field: Optional[str] = None, row: Optional[int] = None):
        self.error_type = error_type
        self.message = message
        self.rule = rule
        self.field = field
        self.row = row
    
    def __str__(self):
        location = ""
        if self.field:
            location += f" in field '{self.field}'"
        if self.row is not None:
            location += f" at row {self.row}"
        return f"{self.error_type}: {self.message}{location}"

    def to_dict(self):
        """Convert the error to a dictionary for API responses"""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "field": self.field,
            "row": self.row,
            "rule": self.rule
        }


class ValidationReport:
    """Class to hold validation results"""
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def add_error(self, error_type: str, message: str, rule: Optional[Dict] = None, 
                  field: Optional[str] = None, row: Optional[int] = None):
        self.errors.append(ValidationError(error_type, message, rule, field, row))
    
    def add_warning(self, error_type: str, message: str, rule: Optional[Dict] = None, 
                    field: Optional[str] = None, row: Optional[int] = None):
        self.warnings.append(ValidationError(error_type, message, rule, field, row))
    
    def summary(self) -> str:
        """Return a string summary of validation results"""
        result = []
        
        if self.is_valid:
            result.append("✅ Validation passed!")
        else:
            result.append(f"❌ Validation failed with {len(self.errors)} errors")
        
        if self.warnings:
            result.append(f"⚠️ Found {len(self.warnings)} warnings")
        
        # Add detailed errors
        if self.errors:
            result.append("\nErrors:")
            for error in self.errors:
                result.append(f"  - {str(error)}")
        
        # Add detailed warnings
        if self.warnings:
            result.append("\nWarnings:")
            for warning in self.warnings:
                result.append(f"  - {str(warning)}")
                
        return "\n".join(result)
    
    def to_dict(self):
        """Convert the report to a dictionary for API responses"""
        return {
            "is_valid": self.is_valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "summary": self.summary()
        }