from typing import Dict, Any, List
import os
import logging

from arkumu.importer.services.importer.uri_utils import slugify_uri_part
import polars as pl
import csv

logger = logging.getLogger(__name__)

def is_multi_valued_column_csv(csv_file_path, column_slug, delimiter=';', field_delimiter=',', max_rows=100, has_quoted_fields=False):
    """
    Check if a column in a CSV file is likely to be multi-valued (contains the field_delimiter),
    using the standard csv module for robust parsing.
    Only checks the first `max_rows` non-null values for efficiency.
    
    Args:
        csv_file_path: Path to the CSV file
        column_slug: Slugified column name to check
        delimiter: CSV column delimiter
        field_delimiter: Multi-value field delimiter
        max_rows: Maximum number of rows to check
        has_quoted_fields: Whether fields in the CSV are quoted (e.g., FileMaker CSV exports)
    """
    try:
        with open(csv_file_path, newline='', encoding='utf-8') as f:
            # Always use QUOTE_ALL for reading to properly handle quoted fields
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.reader(f, delimiter=delimiter, quoting=quoting)
            headers = next(reader)
            # Find the index of the column by slug
            col_indices = {slugify_uri_part(h): i for i, h in enumerate(headers)}
            idx = col_indices.get(column_slug)
            if idx is None:
                return False
            
            count = 0
            for row in reader:
                if len(row) <= idx:
                    continue
                value = row[idx].strip()
                # Skip empty values
                if not value:
                    continue
                # Check if field_delimiter is present in the value
                if field_delimiter in value:
                    return True
                count += 1
                if count >= max_rows:
                    break
        return False
    except Exception as e:
        logger.error(f"Error checking multi-valued column: {e}")
        return False

def generate_draft_mapping_from_csvs(
    csv_file_paths: List[str],
    institution: str = "TODO",
    domain: str = None,
    delimiter: str = ';',
    field_delimiter: str = ',',
    require_pk_for_anchor: bool = False,
    anchor_column: str = None,
    has_quoted_fields: bool = False,
    relationship_hints: Dict[str, Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Generate a draft mapping JSON for each CSV file, only detecting multi-valued columns.
    
    Args:
        csv_file_paths: List of paths to CSV files
        institution: Institution code
        domain: CIDOC CRM domain class, or None to use table name
        delimiter: CSV column delimiter
        field_delimiter: Multi-value field delimiter
        require_pk_for_anchor: If True, only select primary key columns as anchor
        anchor_column: Optional specific column name to use as anchor
        has_quoted_fields: Whether fields in the CSV are quoted (e.g., FileMaker CSV exports)
        relationship_hints: Dict mapping column names to target tables and properties
                           e.g. {"Proj_ID_fk": {"target_table": "00_Projekte", "target_column": "Projekt_ID"}}
    
    Returns:
        Dict mapping filename to generated mapping JSON
    """
    result = {}
    base_comment = "Maps CSV to RDF (S-P-O). 'domain' is the main Subject's CIDOC CRM class, acting as the 'rdfs:domain' for mapped properties. Rules: 'property' is Predicate. 'range' is Object's kind."
    
    relationship_hints = relationship_hints or {}
    
    # First pass: collect all table names and their primary key columns
    table_primary_keys = {}
    for path in csv_file_paths:
        file_name = os.path.basename(path)
        file_base_name = os.path.splitext(file_name)[0]
        
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL)
                headers = next(reader)
                
                # Identify likely primary key columns (first column or containing 'id'/'key')
                pk_candidates = [h for h in headers if "id" in h.lower() or "key" in h.lower()]
                primary_key = pk_candidates[0] if pk_candidates else headers[0]
                table_primary_keys[file_base_name] = primary_key
        except Exception as e:
            logger.error(f"Error processing file {path} for primary key detection: {e}")
            continue
    
    # Second pass: generate mappings with relationship awareness
    for path in csv_file_paths:
        file_name = os.path.basename(path)
        file_base_name = os.path.splitext(file_name)[0]  # Get filename without extension
        
        # Determine domain - either provided or derived from filename 
        table_domain = domain
        if not table_domain:
            table_domain = file_base_name
            comment = f"{base_comment} NOTE: The domain is currently set to the table name '{file_base_name}'. Please replace with an appropriate CIDOC CRM class (e.g., E22_Human-Made_Object, E7_Activity)."
        else:
            comment = base_comment
        
        try:
            with open(path, newline='', encoding='utf-8') as f:
                # Always use QUOTE_ALL for reading to properly handle quoted fields
                reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL)
                headers = next(reader)
                columns = headers.copy()  # Keep original headers for anchor selection
                slugified_headers = [slugify_uri_part(h) for h in headers]
            
            # Determine anchor column
            selected_anchor = None
            if anchor_column:
                # Use specified anchor column if provided
                selected_anchor = anchor_column
            elif len(headers) > 0:
                # Default to the first column as anchor if not specified
                id_columns = [h for h in headers if "id" in h.lower() or "key" in h.lower()]
                if id_columns and require_pk_for_anchor:
                    selected_anchor = id_columns[0]
                else:
                    selected_anchor = headers[0]
                
                # Detect if this is likely a relationship table
                is_relationship_table = False
                fk_columns = [h for h in headers if h.lower().endswith('_fk') or h.lower().endswith('_id') and h != selected_anchor]
                if len(fk_columns) >= 2 and len(headers) <= len(fk_columns) + 4:  # +4 for ID, timestamps, etc.
                    is_relationship_table = True
                    
            mappings = []
            for i, col_name in enumerate(columns):
                col_slug = slugified_headers[i]
                mapping_entry = {
                    "source_column": col_name,  # Use original column name, not slugified
                    "property": "",
                    "range": "",
                }
                
                # Check if this column is a foreign key
                is_fk = col_name.lower().endswith('_fk') or col_name.lower().endswith('_id') and col_name != selected_anchor
                
                # Add relationship info if available
                if is_fk:
                    # Try to guess the target table from column name
                    col_base = col_name.replace('_fk', '').replace('_id', '')
                    
                    # Check if we have explicit hints for this column
                    if col_name in relationship_hints:
                        target_info = relationship_hints[col_name]
                        mapping_entry["target_table"] = target_info.get("target_table", "")
                        mapping_entry["target_column"] = target_info.get("target_column", "")
                        mapping_entry["relationship_type"] = "foreign_key"
                    else:
                        # Try to guess based on naming conventions
                        for table_name, pk in table_primary_keys.items():
                            if col_base.lower() in table_name.lower():
                                mapping_entry["target_table"] = table_name
                                mapping_entry["target_column"] = pk
                                mapping_entry["relationship_type"] = "foreign_key"
                                break
                
                # Check for multi-valued columns
                if is_multi_valued_column_csv(path, col_slug, delimiter=delimiter, field_delimiter=field_delimiter, has_quoted_fields=has_quoted_fields):
                    mapping_entry["multi_valued"] = True
                    mapping_entry["delimiter"] = field_delimiter
                    
                mappings.append(mapping_entry)
            
            mapping_json = {
                "_comment": comment,
                "institution": institution,
                "domain": table_domain,
                "anchor_column": selected_anchor,
                "column_delimiter": delimiter,
                "has_quoted_fields": has_quoted_fields,
                "is_relationship_table": is_relationship_table,
                "mappings": mappings
            }
            result[file_name] = mapping_json
        except Exception as e:
            logger.error(f"Error processing file {path}: {e}")
            continue
    
    return result

def generate_relationship_config(
    csv_file_paths: List[str],
    output_path: str = "relationship_tables.json",
    delimiter: str = ';',
    has_quoted_fields: bool = False
) -> Dict[str, List[Dict[str, str]]]:
    """
    Analyze CSV files and generate a relationship table configuration file.
    
    Args:
        csv_file_paths: List of paths to CSV files
        output_path: Path to save the JSON configuration
        delimiter: CSV column delimiter
        has_quoted_fields: Whether fields in the CSV are quoted
        
    Returns:
        Dict mapping table names to FK column configurations
    """
    relationship_config = {}
    
    # First pass: collect all table names and their primary key columns
    table_primary_keys = {}
    for path in csv_file_paths:
        file_name = os.path.basename(path)
        file_base_name = os.path.splitext(file_name)[0]
        
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL)
                headers = next(reader)
                
                # Identify likely primary key columns (first column or containing 'id'/'key')
                pk_candidates = [h for h in headers if "id" in h.lower() or "key" in h.lower()]
                primary_key = pk_candidates[0] if pk_candidates else headers[0]
                table_primary_keys[file_base_name] = primary_key
        except Exception as e:
            logger.error(f"Error processing file {path} for primary key detection: {e}")
            continue
    
    # Second pass: identify relationship tables and their FK columns
    for path in csv_file_paths:
        file_name = os.path.basename(path)
        file_base_name = os.path.splitext(file_name)[0]
        
        try:
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL)
                headers = next(reader)
                
                # Identify likely FK columns (ending with _fk or _id)
                fk_columns = [h for h in headers if h.lower().endswith('_fk') or h.lower().endswith('_id')]
                
                # Skip tables with fewer than 2 FK columns
                if len(fk_columns) < 2:
                    continue
                    
                # Check if this is likely a relationship table (few columns beyond FKs and IDs)
                non_fk_columns = [h for h in headers if not (h.lower().endswith('_fk') or h.lower().endswith('_id') or 
                                                          'uuid' in h.lower() or 'ts' in h.lower() or 'time' in h.lower())]
                
                if len(non_fk_columns) <= 2:  # Allow a couple of extra columns
                    # This is likely a relationship table
                    fk_config = []
                    
                    for fk_col in fk_columns:
                        # Try to guess target table from column name
                        col_base = fk_col.replace('_fk', '').replace('_id', '').replace('_FK', '').replace('_ID', '')
                        
                        # Find best matching target table
                        best_match = None
                        best_score = 0
                        for table_name in table_primary_keys.keys():
                            # Skip self-references
                            if table_name == file_base_name:
                                continue
                                
                            # Check if column name contains table name or vice versa
                            if col_base.lower() in table_name.lower() or table_name.lower() in col_base.lower():
                                score = len(set(col_base.lower()) & set(table_name.lower()))
                                if score > best_score:
                                    best_match = table_name
                                    best_score = score
                        
                        if best_match:
                            fk_config.append({
                                "column": fk_col,
                                "target_table": best_match,
                                "target_column": table_primary_keys.get(best_match, "")
                            })
                    
                    # Only add to config if we found at least 2 FK relationships
                    if len(fk_config) >= 2:
                        relationship_config[file_base_name] = fk_config
                        
        except Exception as e:
            logger.error(f"Error processing file {path} for relationship detection: {e}")
            continue
    
    # Write configuration to file if requested
    if output_path:
        try:
            import json
            with open(output_path, 'w') as f:
                json.dump(relationship_config, f, indent=2)
            logger.info(f"Relationship configuration written to {output_path}")
        except Exception as e:
            logger.error(f"Error writing relationship configuration: {e}")
    
    return relationship_config
