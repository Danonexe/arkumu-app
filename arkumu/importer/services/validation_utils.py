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
        self.details: Dict = {}  # Additional structured details about the validation
        
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
    
    def print_report(self):
        """Print a detailed validation report including all information in details"""
        # Print summary first
        print(self.summary())
        
        # Print column details if available
        if self.details and 'columns' in self.details:
            column_stats = self.details.get('columns', {})
            print("\n=== COLUMN STATISTICS ===")
            print(f"Total CSV columns: {column_stats.get('total', 0)}")
            print(f"Referenced columns: {column_stats.get('referenced', 0)}")
            print(f"Missing columns: {column_stats.get('missing', 0)}")
            print(f"Unmapped columns: {column_stats.get('unmapped', 0)}")
            
            # Print anchor column details
            anchor_data = self.details.get('anchor_column')
            if anchor_data:
                if anchor_data.get('found', False):
                    print(f"\n✅ Anchor column '{anchor_data.get('name')}' - FOUND")
                    print(f"   - Contains {anchor_data.get('unique_count')} unique values "
                          f"out of {anchor_data.get('total_rows')} rows")
                else:
                    print(f"\n❌ Anchor column '{anchor_data.get('name')}' - MISSING")
            
            # Print MAPPED columns in a table format
            print("\n=== MAPPING COLUMNS TABLE ===")
            
            # Table header
            print(f"{'COLUMN NAME':<30} {'STATUS':<8} {'RDF PROPERTY':<30} {'RANGE':<20} {'NON-NULL %':<15} {'REFERENCES'}")
            print("-" * 110)
            
            # Print mapped columns details
            regular_columns = [c for c in self.details.get('column_data', []) 
                               if not c.get('is_sub_column', False)]
            
            for column in regular_columns:
                name = column.get('name', '')
                status = "✅ FOUND" if column.get('found', False) else "❌ MISSING"
                property_name = column.get('property', 'Unknown')
                range_value = column.get('range', 'Unknown')
                
                if column.get('found', False) and 'non_null_percent' in column:
                    non_null_count = column.get('non_null_count', 0)
                    total_rows = column.get('total_rows', 0)
                    coverage = f"{column.get('non_null_percent', 0):.1f}% ({non_null_count}/{total_rows})"
                else:
                    coverage = "N/A"
                    
                references = column.get('references_table', '-')
                
                print(f"{name:<30} {status:<8} {property_name:<30} {range_value:<20} {coverage:<15} {references}")
            
            # Print sub-columns if any
            sub_columns = [c for c in self.details.get('column_data', []) 
                           if c.get('is_sub_column', False)]
            
            if sub_columns:
                print("\n--- SUB-COLUMNS ---")
                print(f"{'SUB-COLUMN NAME':<30} {'STATUS':<8} {'PARENT COLUMN':<30} {'RDF PROPERTY':<30}")
                print("-" * 100)
                
                for column in sub_columns:
                    name = column.get('name', '')
                    status = "✅ FOUND" if column.get('found', False) else "❌ MISSING"
                    parent = column.get('parent_column', '-')
                    property_name = column.get('property', 'Unknown')
                    
                    print(f"{name:<30} {status:<8} {parent:<30} {property_name:<30}")
                    
            # Print unmapped columns in a table format
            unmapped = self.details.get('unmapped_columns', [])
            if unmapped:
                print("\n=== UNMAPPED CSV COLUMNS ===")
                # Split unmapped columns into multiple columns for better display
                columns_per_row = 3
                column_width = 35
                
                for i in range(0, len(unmapped), columns_per_row):
                    row = unmapped[i:i + columns_per_row]
                    print("".join(f"{col:<{column_width}}" for col in row))
                    
        print("\n==============================\n")
    
    def to_dict(self):
        """Convert the report to a dictionary for API responses"""
        return {
            "is_valid": self.is_valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "summary": self.summary(),
            "details": self.details
        }