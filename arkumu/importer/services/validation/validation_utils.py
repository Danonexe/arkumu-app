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
        self.info: List[ValidationError] = []  # New field for informational messages
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
        
    def add_info(self, info_type: str, message: str, rule: Optional[Dict] = None, 
                field: Optional[str] = None, row: Optional[int] = None):
        """Add an informational message to the report"""
        self.info.append(ValidationError(info_type, message, rule, field, row))
    
    def summary(self) -> str:
        """Return a string summary of validation results"""
        result = []
        
        if self.is_valid:
            result.append("✅ Validation passed!")
        else:
            result.append(f"❌ Validation failed with {len(self.errors)} errors")
        
        if self.warnings:
            result.append(f"⚠️ Found {len(self.warnings)} warnings")
            
        if self.info:
            result.append(f"ℹ️ {len(self.info)} informational messages")
        
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
                
        # Add informational messages
        if self.info:
            result.append("\nInformation:")
            for info in self.info:
                result.append(f"  - {str(info)}")
                
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
            
            # Get column data and referenced tables
            regular_columns = [c for c in self.details.get('column_data', []) 
                              if not c.get('is_sub_column', False)]
            
            # Extract reference tables from column data
            reference_tables = {}
            for column in regular_columns:
                references = column.get('references_table')
                if references and references != '-':
                    reference_tables[references] = {
                        'referenced_by': column.get('name'),
                        'db_status': 'UNKNOWN'  # Default status
                    }
            
            # Update reference status from DB checks if available
            if 'references' in self.details:
                for ref_name, ref_info in self.details['references'].items():
                    if ref_name in reference_tables:
                        db_found = ref_info.get('exists_in_db', False)
                        reference_tables[ref_name]['db_status'] = 'FOUND_IN_DB' if db_found else 'NOT_FOUND_IN_DB'
                        reference_tables[ref_name]['ref_info'] = ref_info
            
            # Print reference tables with clear DB status
            if reference_tables:
                print(f"\n{'TABLE NAME':<35} {'DATABASE STATUS':<25} {'REFERENCED BY COLUMN'}")
                print("-" * 85)
                
                for table_name, table_info in reference_tables.items():
                    status = table_info.get('db_status', 'UNKNOWN')
                    referenced_by = table_info.get('referenced_by', '')
                    
                    # Clear visual indicators
                    if status == 'FOUND_IN_DB':
                        status_text = f"✅ FOUND"
                    elif status == 'NOT_FOUND_IN_DB':
                        status_text = f"❌ NOT FOUND - Import Required"
                    elif status == 'VALIDATION_UNAVAILABLE':
                        status_text = f"⚠️ VALIDATION UNAVAILABLE"
                    else:
                        status_text = f"⚠️ STATUS UNKNOWN"
                        
                    print(f"{table_name:<35} {status_text:<25} {referenced_by}")
                    
                    # If we have detailed info, show it
                    if 'ref_info' in table_info:
                        ref_info = table_info['ref_info']
                        if 'values_to_check' in ref_info:
                            print(f"   - References to check: {ref_info['values_to_check']}")
                        if 'error' in ref_info:
                            print(f"   - Error: {ref_info['error']}")
            
            # Print MAPPED columns in a table format
            print("\n=== MAPPING COLUMNS TABLE ===")
            
            # Table header
            print(f"{'COLUMN NAME':<30} {'STATUS':<8} {'RDF PROPERTY':<30} {'RANGE':<20} {'NON-NULL %':<15} {'REFERENCES'}")
            print("-" * 110)
            
            # Print mapped columns details
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
                
                # Indicate reference DB status in the column table
                if references != '-' and references in reference_tables:
                    ref_status = reference_tables[references].get('db_status', 'UNKNOWN')
                    if ref_status == 'NOT_FOUND_IN_DB':
                        references = f"{references} ❌"
                    elif ref_status == 'FOUND_IN_DB':
                        references = f"{references} ✅"
                    elif ref_status == 'VALIDATION_UNAVAILABLE':
                        references = f"{references} ⚠️"
                    else:
                        references = f"{references} ⚠️"
                
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