import logging
import json
import pandas as pd
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple

from arkumu.importer.services.validation_utils import ValidationReport

logger = logging.getLogger(__name__)


class MappingValidator:
    """Service to validate mapping files against data sources"""
    
    # Required fields in the mapping file
    REQUIRED_MAPPING_FIELDS = ["institution", "domain", "anchor_column", "mappings"]
    
    # Required fields for each mapping rule
    REQUIRED_RULE_FIELDS = ["source_column", "property"]
    
    def __init__(self, data_loader=None):
        """
        Initialize the validator
        
        Args:
            data_loader: Optional service to load related data sources
        """
        self.data_loader = data_loader
        self.related_sources = {}
        
    def load_related_sources(self, institution: str, data_dir: str) -> Dict:
        """
        Load related sources for reference validation
        
        Args:
            institution: Institution code
            data_dir: Directory containing data files
            
        Returns:
            Dict of related sources
        """
        if self.data_loader:
            # Use data loader service if provided
            return self.data_loader.load_related_sources(institution)
        
        related_sources = {}
        
        # Simple implementation to find and load CSVs in the directory
        data_path = Path(data_dir)
        csv_files = list(data_path.glob("*.csv"))
        
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file, dtype=str)
                table_name = csv_file.stem
                
                # Store all rows as a list of dictionaries for reference lookup
                related_sources[table_name] = df.to_dict(orient='records')
                
                # Also add specific column indices for faster lookup
                # For example, if there's an ID column, create a dedicated lookup dict
                id_columns = [col for col in df.columns if col.lower().endswith('id')]
                for id_col in id_columns:
                    related_sources[f"{table_name}_{id_col}"] = {
                        str(row[id_col]): row for _, row in df.iterrows() if pd.notna(row[id_col])
                    }
                
            except Exception as e:
                logger.warning(f"Failed to load related source {csv_file}: {e}")
        
        return related_sources
    
    def validate_mapping_file(self, mapping_file: str) -> ValidationReport:
        """
        Validate the structure of a mapping file without data
        
        Args:
            mapping_file: Path to the mapping file
            
        Returns:
            ValidationReport with results
        """
        report = ValidationReport()
        
        # Check if file exists
        if not os.path.exists(mapping_file):
            report.add_error("FILE_NOT_FOUND", f"Mapping file not found: {mapping_file}")
            return report
        
        # Load JSON
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except json.JSONDecodeError as e:
            report.add_error("INVALID_JSON", f"Invalid JSON in mapping file: {e}")
            return report
        
        # Check required fields
        for field in self.REQUIRED_MAPPING_FIELDS:
            if field not in mapping:
                report.add_error("MISSING_FIELD", f"Required field '{field}' missing from mapping", field=field)
        
        # If mappings field doesn't exist or is not a list, stop here
        if not isinstance(mapping.get("mappings"), list):
            report.add_error("INVALID_MAPPINGS", "Mappings must be a list of rules")
            return report
        
        # Validate each mapping rule
        for i, rule in enumerate(mapping.get("mappings", [])):
            self._validate_mapping_rule_structure(rule, i, report)
        
        return report
    
    def _validate_mapping_rule_structure(self, rule: Dict, index: int, report: ValidationReport):
        """Validate the structure of a single mapping rule"""
        
        # Check required fields
        for field in self.REQUIRED_RULE_FIELDS:
            if field not in rule:
                report.add_error(
                    "MISSING_RULE_FIELD", 
                    f"Required field '{field}' missing from rule #{index+1}", 
                    rule=rule, 
                    field=field
                )
        
        # Check range field is present if not a relationship
        if "object_column" not in rule and "range" not in rule:
            report.add_error(
                "MISSING_RANGE",
                f"Either 'range' or 'object_column' must be specified in rule #{index+1}",
                rule=rule
            )
        
        # Validate object_properties if present
        if "object_properties" in rule and isinstance(rule["object_properties"], list):
            for j, sub_rule in enumerate(rule["object_properties"]):
                # Check sub-rule has property
                if "property" not in sub_rule and "predicate" not in sub_rule:
                    report.add_error(
                        "MISSING_PROPERTY",
                        f"Sub-rule #{j+1} in rule #{index+1} is missing 'property' or 'predicate'",
                        rule=sub_rule,
                        field="property"
                    )
                
                # Check sub-rule has a value source
                has_value_source = any(k in sub_rule for k in ["source_column", "fixed_value", "use_parent_value"])
                if not has_value_source:
                    report.add_error(
                        "MISSING_VALUE_SOURCE",
                        f"Sub-rule #{j+1} in rule #{index+1} has no value source (source_column, fixed_value, or use_parent_value)",
                        rule=sub_rule
                    )
    
    def validate_mapping_against_data(self, mapping_file: str, csv_file: str) -> ValidationReport:
        """
        Validate a mapping file against a CSV data file
        
        Args:
            mapping_file: Path to the mapping file
            csv_file: Path to the CSV data file
            
        Returns:
            ValidationReport with results
        """
        report = ValidationReport()
        
        # First validate the mapping file structure
        structure_report = self.validate_mapping_file(mapping_file)
        if not structure_report.is_valid:
            report.errors.extend(structure_report.errors)
            report.warnings.extend(structure_report.warnings)
            return report
        
        # Load mapping
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception as e:
            report.add_error("MAPPING_LOAD_ERROR", f"Error loading mapping file: {e}")
            return report
        
        # Load CSV
        try:
            df = pd.read_csv(csv_file, dtype=str)
        except Exception as e:
            report.add_error("CSV_LOAD_ERROR", f"Error loading CSV file: {e}")
            return report
        
        # Get the list of columns in the CSV
        csv_columns = set(df.columns)
        
        # Check anchor column
        anchor_column = mapping.get("anchor_column")
        if anchor_column not in csv_columns:
            report.add_error(
                "MISSING_ANCHOR_COLUMN",
                f"Anchor column '{anchor_column}' not found in CSV", 
                field=anchor_column
            )
        
        # Check all source_column references
        for i, rule in enumerate(mapping.get("mappings", [])):
            self._validate_rule_against_data(rule, csv_columns, i, report)
        
        return report
    
    def _validate_rule_against_data(self, rule: Dict, csv_columns: Set[str], index: int, report: ValidationReport):
        """Validate a single mapping rule against CSV data"""
        
        # Check source_column exists in CSV
        source_column = rule.get("source_column")
        if source_column and source_column not in csv_columns:
            report.add_error(
                "MISSING_SOURCE_COLUMN",
                f"Source column '{source_column}' not found in CSV",
                rule=rule,
                field=source_column
            )
        
        # Check object_column for extra validation if needed
        object_column = rule.get("object_column")
        if object_column and not self._is_valid_object_column(object_column):
            report.add_warning(
                "UNKNOWN_OBJECT_COLUMN",
                f"Object column '{object_column}' not validated as a reference source",
                rule=rule,
                field=object_column
            )
        
        # Check sub-rules if present
        if "object_properties" in rule and isinstance(rule["object_properties"], list):
            for j, sub_rule in enumerate(rule["object_properties"]):
                sub_source_column = sub_rule.get("source_column")
                if sub_source_column and sub_source_column not in csv_columns:
                    report.add_error(
                        "MISSING_SUB_SOURCE_COLUMN",
                        f"Sub-rule source column '{sub_source_column}' not found in CSV",
                        rule=sub_rule,
                        field=sub_source_column
                    )
    
    def _is_valid_object_column(self, object_column: str) -> bool:
        """
        Check if an object_column is a known reference source
        For proper implementation, this would check registered reference lookup tables
        """
        # Simple implementation, should be replaced with actual reference table validation
        return True  # Placeholder
    
    def validate_references(self, mapping_file: str, csv_file: str, 
                           related_sources: Optional[Dict] = None,
                           data_dir: Optional[str] = None) -> ValidationReport:
        """
        Validate all references in a mapping file against data
        
        Args:
            mapping_file: Path to the mapping file
            csv_file: Path to the CSV data file
            related_sources: Dict of pre-loaded related sources
            data_dir: Directory containing related data files
            
        Returns:
            ValidationReport with results
        """
        report = ValidationReport()
        
        # First validate the mapping and CSV
        basic_report = self.validate_mapping_against_data(mapping_file, csv_file)
        if not basic_report.is_valid:
            report.errors.extend(basic_report.errors)
            report.warnings.extend(basic_report.warnings)
            return report
        
        # Load mapping
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception as e:
            report.add_error("MAPPING_LOAD_ERROR", f"Error loading mapping file: {e}")
            return report
        
        # Load CSV data
        try:
            df = pd.read_csv(csv_file, dtype=str)
        except Exception as e:
            report.add_error("CSV_LOAD_ERROR", f"Error loading CSV file: {e}")
            return report
        
        # Load related sources if not provided
        institution = mapping.get("institution")
        if related_sources is None and data_dir:
            related_sources = self.load_related_sources(institution, data_dir)
        
        if not related_sources:
            report.add_warning(
                "NO_RELATED_SOURCES",
                "No related sources provided or loaded for reference validation"
            )
            return report
        
        # Validate references in each mapping rule
        for i, rule in enumerate(mapping.get("mappings", [])):
            object_column = rule.get("object_column")
            source_column = rule.get("source_column")
            
            if object_column and source_column and source_column in df.columns:
                self._validate_references_in_rule(rule, df, related_sources, report)
        
        return report
    
    def _validate_references_in_rule(self, rule: Dict, df: pd.DataFrame, 
                                    related_sources: Dict, report: ValidationReport):
        """Validate references for a single rule across all rows"""
        
        object_column = rule.get("object_column")
        source_column = rule.get("source_column")
        multi_valued = rule.get("multi_valued", False)
        delimiter = rule.get("delimiter", ",") if multi_valued else None
        
        # Check if the object_column exists in related_sources
        if object_column not in related_sources:
            report.add_warning(
                "MISSING_REFERENCE_SOURCE",
                f"Reference source '{object_column}' not found in related sources",
                rule=rule,
                field=object_column
            )
            return
        
        # Get all values from the source column
        all_values = df[source_column].dropna()
        
        # Handle multi-valued fields
        if multi_valued:
            # Split values and flatten the list
            all_references = []
            for val in all_values:
                if val and isinstance(val, str):
                    all_references.extend([ref.strip() for ref in val.split(delimiter) if ref.strip()])
        else:
            all_references = [str(val) for val in all_values if val]
        
        # Validate each reference
        reference_source = related_sources[object_column]
        
        if isinstance(reference_source, dict):
            # Dict-based lookup
            missing_references = [ref for ref in all_references if ref not in reference_source]
        else:
            # List-based lookup using 'id' field
            reference_ids = {str(item.get('id', '')) for item in reference_source}
            missing_references = [ref for ref in all_references if ref not in reference_ids]
        
        # Report missing references
        if missing_references:
            for ref in missing_references[:10]:  # Limit to first 10 for readability
                report.add_error(
                    "INVALID_REFERENCE",
                    f"Reference '{ref}' for '{object_column}' not found in related sources",
                    rule=rule
                )
            
            if len(missing_references) > 10:
                report.add_warning(
                    "MANY_INVALID_REFERENCES",
                    f"Found {len(missing_references)} invalid references for '{object_column}', "
                    "only showing first 10",
                    rule=rule
                )


def validate_mapping(mapping_file: str, csv_file: str, data_dir: Optional[str] = None,
                    related_sources: Optional[Dict] = None, strict: bool = True) -> bool:
    """
    Convenience function to validate a mapping file against data
    
    Args:
        mapping_file: Path to the mapping file
        csv_file: Path to the CSV data file
        data_dir: Directory containing related data files
        related_sources: Optional pre-loaded related sources
        strict: If True, fail on any error or warning
        
    Returns:
        bool: True if validation passed, False otherwise
    """
    validator = MappingValidator()
    
    # Do full validation including references
    report = validator.validate_references(mapping_file, csv_file, related_sources, data_dir)
    
    # Print the report
    print(report.summary())
    
    if strict:
        return report.is_valid and not report.warnings
    else:
        return report.is_valid
