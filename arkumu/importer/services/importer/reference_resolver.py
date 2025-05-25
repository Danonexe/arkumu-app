import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class ReferenceResolver:
    """
    Handles detection and parsing of foreign key references in CSV data.
    """
    
    @staticmethod
    def is_reference_column(column_name: str, value: str) -> bool:
        """
        Determine if a column likely contains a reference to another entity.
        
        Args:
            column_name: Name of the column
            value: Value in the column
            
        Returns:
            bool: True if this looks like a reference column
        """
        if not column_name or not value:
            return False
            
        column_lower = column_name.lower().strip()
        value_stripped = value.strip()
        
        # Skip empty values
        if not value_stripped:
            return False
        
        # Very restrictive detection - only clear reference patterns
        
        # Skip if it's the primary 'id' column
        if column_lower == 'id':
            return False
        
        # Only detect if column name clearly indicates a reference AND value looks like an ID
        is_reference_name = (
            column_lower.endswith('_id') or 
            column_lower.endswith('_ref') or 
            column_lower.endswith('_key') or
            column_lower.startswith('id_') or
            column_lower.startswith('ref_') or
            column_lower.startswith('key_')
        )
        
        if is_reference_name and ReferenceResolver._looks_like_id_value(value_stripped):
            return True
                
        return False
    
    @staticmethod
    def _looks_like_id_value(value: str) -> bool:
        """
        Check if a value looks like an ID based on common ID patterns.
        
        Args:
            value: The value to check
            
        Returns:
            bool: True if value looks like an ID
        """
        if not value:
            return False
            
        value = value.strip()
        
        # Empty or very short values are unlikely to be IDs
        if len(value) < 1:
            return False
        
        # Very long values are unlikely to be simple IDs
        if len(value) > 100:
            return False
        
        # Pure numeric values (common ID pattern)
        if value.isdigit():
            return True
            
        # Alphanumeric values (common ID pattern)
        if value.isalnum():
            return True
            
        # Values with common ID separators (but not emails or URLs)
        if any(sep in value for sep in ['-', '_']):
            # Skip if it looks like an email or URL
            if '@' in value or '.' in value:
                return False
            # Remove separators and check if remaining is alphanumeric
            cleaned = ''.join(char for char in value if char.isalnum())
            if cleaned and len(cleaned) >= 2:
                return True
                
        # Mixed letter-number patterns (like EMP001, PROJ123, etc.)
        has_letters = any(char.isalpha() for char in value)
        has_numbers = any(char.isdigit() for char in value)
        if has_letters and has_numbers:
            # Skip if it looks like an email
            if '@' in value:
                return False
            # Check if it's mostly alphanumeric (allowing some separators)
            alphanumeric_count = sum(1 for char in value if char.isalnum())
            if alphanumeric_count / len(value) >= 0.8:  # At least 80% alphanumeric
                return True
                
        return False
    
    @staticmethod
    def parse_reference(column_name: str, value: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse a reference column to extract target table and ID.
        
        Args:
            column_name: Name of the column
            value: Value in the column
            
        Returns:
            tuple: (target_table, target_id) or (None, None) if can't parse
        """
        try:
            if not column_name or not value:
                return None, None
                
            column_lower = column_name.lower().strip()
            value_stripped = value.strip()
            
            # Skip if it's the primary 'id' column
            if column_lower == 'id':
                return None, None
            
            # Parse based on our strict reference patterns
            if '_' in column_lower:
                parts = column_name.split('_')
                if len(parts) >= 2:
                    # Handle suffix patterns (table_id, table_ref, table_key)
                    if column_lower.endswith(('_id', '_ref', '_key')):
                        potential_table = '_'.join(parts[:-1])
                        if potential_table:
                            return potential_table, value_stripped
                    
                    # Handle prefix patterns (id_table, ref_table, key_table)
                    elif column_lower.startswith(('id_', 'ref_', 'key_')):
                        potential_table = '_'.join(parts[1:])
                        if potential_table:
                            return potential_table, value_stripped
            
            # Fallback: if it matches our reference patterns but no underscore
            # Just use the column name as-is (removing common suffixes/prefixes)
            if column_lower.endswith(('id', 'ref', 'key')) and len(column_lower) > 3:
                # Remove suffix
                for suffix in ['id', 'ref', 'key']:
                    if column_lower.endswith(suffix):
                        potential_table = column_name[:-len(suffix)]
                        if potential_table:
                            return potential_table, value_stripped
            
            if column_lower.startswith(('id', 'ref', 'key')) and len(column_lower) > 3:
                # Remove prefix
                for prefix in ['id', 'ref', 'key']:
                    if column_lower.startswith(prefix):
                        potential_table = column_name[len(prefix):]
                        if potential_table:
                            return potential_table, value_stripped
                    
        except Exception as e:
            logger.debug(f"Error parsing reference {column_name}={value}: {e}")
            
        return None, None
    
    @staticmethod
    def analyze_column_patterns(csv_path: str, delimiter: str = ';') -> dict:
        """
        Analyze a CSV file to identify potential reference columns.
        
        Args:
            csv_path: Path to the CSV file
            delimiter: CSV delimiter
            
        Returns:
            dict: Analysis results with potential reference columns
        """
        import csv
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                
                # Sample first few rows to analyze patterns
                sample_rows = []
                for i, row in enumerate(reader):
                    if i >= 10:  # Sample first 10 rows
                        break
                    sample_rows.append(row)
                
                if not sample_rows:
                    return {"error": "No data rows found"}
                
                # Analyze each column
                column_analysis = {}
                for column_name in sample_rows[0].keys():
                    # Count how many values look like references
                    reference_count = 0
                    total_non_empty = 0
                    
                    for row in sample_rows:
                        value = row.get(column_name, '')
                        if value and value.strip():
                            total_non_empty += 1
                            if ReferenceResolver.is_reference_column(column_name, value):
                                reference_count += 1
                    
                    if total_non_empty > 0:
                        reference_percentage = (reference_count / total_non_empty) * 100
                        
                        column_analysis[column_name] = {
                            "is_likely_reference": reference_percentage > 50,
                            "reference_percentage": reference_percentage,
                            "sample_values": [row.get(column_name, '') for row in sample_rows[:3]],
                            "parsed_references": []
                        }
                        
                        # Try to parse some references
                        for row in sample_rows[:3]:
                            value = row.get(column_name, '')
                            if value and value.strip():
                                target_table, target_id = ReferenceResolver.parse_reference(column_name, value)
                                if target_table and target_id:
                                    column_analysis[column_name]["parsed_references"].append({
                                        "target_table": target_table,
                                        "target_id": target_id
                                    })
                
                return {
                    "total_columns": len(sample_rows[0].keys()) if sample_rows else 0,
                    "rows_analyzed": len(sample_rows),
                    "column_analysis": column_analysis,
                    "likely_reference_columns": [
                        col for col, analysis in column_analysis.items() 
                        if analysis["is_likely_reference"]
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error analyzing column patterns in {csv_path}: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def suggest_relationship_config(csv_files: list, delimiter: str = ';') -> dict:
        """
        Analyze multiple CSV files and suggest a relationship configuration.
        
        Args:
            csv_files: List of CSV file paths
            delimiter: CSV delimiter
            
        Returns:
            dict: Suggested relationship configuration
        """
        try:
            all_tables = set()
            relationship_suggestions = {}
            
            # Analyze each file
            for csv_path in csv_files:
                import os
                table_name = os.path.splitext(os.path.basename(csv_path))[0]
                all_tables.add(table_name)
                
                analysis = ReferenceResolver.analyze_column_patterns(csv_path, delimiter)
                
                if "column_analysis" in analysis:
                    # Look for columns that reference other tables
                    fk_columns = []
                    
                    for column_name, col_analysis in analysis["column_analysis"].items():
                        if col_analysis["is_likely_reference"]:
                            # Try to determine target table from parsed references
                            parsed_refs = col_analysis.get("parsed_references", [])
                            if parsed_refs:
                                target_table = parsed_refs[0]["target_table"]
                                fk_columns.append({
                                    "column": column_name,
                                    "target_table": target_table
                                })
                    
                    if fk_columns:
                        relationship_suggestions[table_name] = fk_columns
            
            return {
                "all_tables": sorted(list(all_tables)),
                "relationship_suggestions": relationship_suggestions,
                "suggested_config": relationship_suggestions
            }
            
        except Exception as e:
            logger.error(f"Error suggesting relationship config: {e}")
            return {"error": str(e)} 