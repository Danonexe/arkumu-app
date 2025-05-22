import os
import logging
import polars as pl
from typing import List, Dict, Any, Optional, Tuple
from arkumu.importer.services.importer.data_utils import normalize_string_nfc
from arkumu.importer.services.importer.uri_utils import slugify_uri_part
import chardet

logger = logging.getLogger(__name__)


def get_table_column_dict(csv_file_paths: List[str], delimiter: str = ';') -> Dict[str, List[str]]:
    """
    For each CSV file, return a dictionary where the key is the slugified table name (file name without extension),
    and the value is a list of slugified column names.
    delimiter: The column delimiter to use when reading CSVs (default ';').
    """
    table_columns = {}
    for path in csv_file_paths:
        table_name = os.path.splitext(os.path.basename(path))[0]
        norm_table_name = slugify_uri_part(table_name)
        logger.info(f"[get_table_column_dict] Reading file: {path} as table: {norm_table_name} with delimiter '{delimiter}'")
        # Read first line as bytes and string for debugging
        try:
            with open(path, "rb") as f:
                first_bytes = f.read(200)
            logger.debug(f"[get_table_column_dict] First 200 bytes of {path}: {first_bytes}")
            detected = chardet.detect(first_bytes)
            logger.debug(f"[get_table_column_dict] Detected encoding for {path}: {detected}")
            try:
                first_line = first_bytes.decode(detected['encoding'] or 'utf-8', errors='replace').splitlines()[0]
            except Exception as e:
                first_line = None
                logger.warning(f"[get_table_column_dict] Could not decode first line of {path}: {e}")
            logger.debug(f"[get_table_column_dict] First line as string: {first_line}")
        except Exception as e:
            logger.warning(f"[get_table_column_dict] Could not read first line of {path}: {e}")
        try:
            df = pl.read_csv(path, n_rows=0, separator=delimiter, infer_schema_length=10000, ignore_errors=True)
            logger.info(f"[get_table_column_dict] Columns found in {path}: {df.columns}")
            norm_columns = [slugify_uri_part(col) for col in df.columns]
            logger.info(f"[get_table_column_dict] Normalized columns: {norm_columns}")
            table_columns[norm_table_name] = norm_columns
        except Exception as e:
            logger.error(f"[get_table_column_dict] ERROR reading {path}: {e}")
            table_columns[norm_table_name] = []  # Could not read columns
    return table_columns


def mark_primary_keys(table_column_dict: Dict[str, List[str]], csv_file_paths: List[str], delimiter: str = ';') -> Dict[str, List[Dict[str, Any]]]:
    """
    For each table, mark which column is the most likely primary key using heuristics:
    - Prefer 'id', '{table}_id', '{table}-id', 'uuid', '{table}_uuid' (in that order), if unique.
    - Otherwise, pick the only unique column if there is one.
    - Otherwise, fallback to the first column.
    Returns a dict with each column as a dict: {name, is_pk}.
    Only one column per table will be marked as PK.
    delimiter: The column delimiter to use when reading CSVs (default ';').
    """
    pk_dict = {}
    # Build a map from slugified table name to file path
    table_to_path = {slugify_uri_part(os.path.splitext(os.path.basename(p))[0]): p for p in csv_file_paths}
    for table, columns in table_column_dict.items():
        path = table_to_path.get(table)
        logger.info(f"[mark_primary_keys] Processing table: {table} (file: {path}) with columns: {columns}")
        df = None
        if path:
            try:
                df = pl.read_csv(path, separator=delimiter, infer_schema_length=10000, ignore_errors=True)
                logger.info(f"[mark_primary_keys] DataFrame columns: {df.columns}, shape: {df.shape}")
            except Exception as e:
                logger.error(f"[mark_primary_keys] ERROR reading {path}: {e}")
        # Gather unique columns
        unique_cols = set()
        nonnull_counts = {}
        if df is not None:
            for col in columns:
                orig_col = next((c for c in df.columns if slugify_uri_part(c) == col), None)
                if orig_col:
                    unique_count = df[orig_col].n_unique()
                    null_count = df[orig_col].null_count()
                    nonnull_counts[col] = df.shape[0] - null_count
                    logger.info(f"[mark_primary_keys] Column '{col}' (original: '{orig_col}'): unique_count={unique_count}, null_count={null_count}")
                    if unique_count == df.shape[0] and null_count == 0:
                        unique_cols.add(col)
        # Priority order for PK
        priority = [
            'id',
            f'{table}id',
            f'{table}-id',
            'uuid',
            f'{table}uuid',
        ]
        pk_col = None
        # 1. Prefer priority names if unique
        for pname in priority:
            if pname in columns and pname in unique_cols:
                pk_col = pname
                logger.info(f"[mark_primary_keys] PK selected by priority: {pk_col}")
                break
        # 2. If no priority match, but only one unique col, use it
        if not pk_col and len(unique_cols) == 1:
            pk_col = next(iter(unique_cols))
            logger.info(f"[mark_primary_keys] PK selected as only unique col: {pk_col}")
        # 3. If multiple unique, prefer first by order in columns
        if not pk_col and unique_cols:
            for col in columns:
                if col in unique_cols:
                    pk_col = col
                    logger.info(f"[mark_primary_keys] PK selected as first unique col: {pk_col}")
                    break
        # 4. Fallback: first column
        if not pk_col and columns:
            pk_col = columns[0]
            logger.info(f"[mark_primary_keys] PK fallback to first column: {pk_col}")
        # Build output
        col_dicts = []
        for col in columns:
            col_dicts.append({'name': col, 'is_pk': col == pk_col})
        pk_dict[table] = col_dicts
    return pk_dict


def is_foreign_key_match(col_name: str, target_table: str, pk_col: str) -> bool:
    """
    Determine if a column is likely a foreign key to the target table based on naming patterns.
    Uses more precise matching than simple substring containment.
    
    Args:
        col_name: The name of the column to check
        target_table: The name of the potential target table
        pk_col: The name of the primary key column in the target table
        
    Returns:
        bool: True if the column is likely a foreign key, False otherwise
    """
    # 1. Exact match with the target table's PK
    if col_name == pk_col:
        logger.info(f"FK match: {col_name} == {pk_col} (exact PK match)")
        return True
    
    # 2. Common FK naming patterns
    fk_patterns = [
        f"{target_table}-id",
        f"{target_table}id",
        f"{target_table}_id"
    ]
    if col_name in fk_patterns:
        logger.info(f"FK match: {col_name} in {fk_patterns} (common FK pattern)")
        return True
    
    # 3. Exact match with target table name, but only if target PK follows standard naming
    # This handles cases where "ereignistyp" column references "ereignistyp" table with PK "ereignistyp-id"
    if col_name == target_table and (
        pk_col == f"{target_table}-id" or 
        pk_col == f"{target_table}id" or
        pk_col == f"{target_table}_id" or
        pk_col == "id" or 
        pk_col == "uuid"
    ):
        logger.info(f"FK match: {col_name} == {target_table} (exact table match with standard PK)")
        return True
    
    # 4. Column contains the table name (for composite names like "ereignisort" -> "ort")
    # But avoid cases where the column name is a compound of the target table name and "-id"
    # This prevents cases like "ereignistyp-id" being detected as FK to "ereignis" table
    if target_table in col_name:
        # Check if this looks like a primary key of another table that happens to contain the target table name
        is_likely_pk_of_another_table = (
            col_name.endswith("-id") and 
            col_name != f"{target_table}-id" and
            # Check if the column name without the "-id" suffix contains the target table name
            target_table in col_name[:-3]
        )
        
        if not is_likely_pk_of_another_table:
            logger.info(f"FK potential match: {col_name} contains {target_table} (needs value verification)")
            # This is a potential match, but we'll verify with value checks in the main function
            return True
    
    return False


def check_value_overlap(source_table: str, source_col: str, target_table: str, target_col: str, 
                        csv_file_paths: List[str], delimiter: str = ';', field_delimiter: str = ',') -> bool:
    """
    Check if values in source_col of source_table overlap significantly with values in target_col of target_table.
    This is used to verify FK relationships based on actual data values.
    If no significant overlap is found with the target column, also checks other columns in the target table
    that might contain matching values (e.g., wikidata-id, wikidata-q-nummer).
    
    Args:
        source_table: The name of the source table
        source_col: The name of the potential FK column
        target_table: The name of the target table
        target_col: The name of the target PK column
        csv_file_paths: List of CSV file paths
        delimiter: CSV delimiter
        field_delimiter: Delimiter used within field values (e.g., comma in "1,2,3")
        
    Returns:
        bool: True if there's significant value overlap, False otherwise
    """
    # Build a map from slugified table name to file path
    table_to_path = {slugify_uri_part(os.path.splitext(os.path.basename(p))[0]): p for p in csv_file_paths}
    
    source_path = table_to_path.get(source_table)
    target_path = table_to_path.get(target_table)
    
    logger.info(f"[check_value_overlap] Checking FK relationship: {source_table}.{source_col} -> {target_table}.{target_col}")
    logger.info(f"[check_value_overlap] Source path: {source_path}, Target path: {target_path}")
    
    if not source_path or not target_path:
        logger.warning(f"[check_value_overlap] Missing path for source or target table")
        return False
    
    try:
        # Read both tables
        logger.info(f"[check_value_overlap] Reading source table: {source_path}")
        source_df = pl.read_csv(source_path, separator=delimiter, infer_schema_length=10000, ignore_errors=True)
        
        logger.info(f"[check_value_overlap] Reading target table: {target_path}")
        target_df = pl.read_csv(target_path, separator=delimiter, infer_schema_length=10000, ignore_errors=True)
        
        # Get the original column names (non-slugified)
        source_orig_col = next((c for c in source_df.columns if slugify_uri_part(c) == source_col), None)
        target_orig_col = next((c for c in target_df.columns if slugify_uri_part(c) == target_col), None)
        
        logger.info(f"[check_value_overlap] Source original column: {source_orig_col}, Target original column: {target_orig_col}")
        
        if not source_orig_col:
            logger.warning(f"[check_value_overlap] Could not find original source column name")
            return False
        
        # Get unique values from source column
        source_values_raw = source_df[source_orig_col].unique().to_list()
        logger.info(f"[check_value_overlap] Raw source values (sample): {source_values_raw[:5] if len(source_values_raw) > 5 else source_values_raw}")
        
        # Remove None/null values
        source_values_raw = [v for v in source_values_raw if v is not None]
        
        # Process source values - split by field_delimiter if needed
        source_values = set()
        for value in source_values_raw:
            if isinstance(value, str) and field_delimiter in value:
                # Split the value and add each part
                parts = [part.strip() for part in value.split(field_delimiter)]
                logger.info(f"[check_value_overlap] Split value '{value}' into parts: {parts}")
                source_values.update(parts)
            else:
                source_values.add(value)
        
        logger.info(f"[check_value_overlap] Processed source values (sample): {list(source_values)[:5] if len(source_values) > 5 else list(source_values)}")
        
        if not source_values:
            logger.warning(f"[check_value_overlap] No valid source values to check")
            return False
        
        # First try with the primary target column
        if target_orig_col:
            target_values = set(target_df[target_orig_col].unique().to_list())
            target_values = {v for v in target_values if v is not None}
            
            logger.info(f"[check_value_overlap] Target values from {target_orig_col} (sample): {list(target_values)[:5] if len(target_values) > 5 else list(target_values)}")
            
            # Check overlap
            overlap = source_values.intersection(target_values)
            overlap_ratio = len(overlap) / len(source_values) if source_values else 0
            
            logger.info(f"[check_value_overlap] Overlap values (sample): {list(overlap)[:5] if len(overlap) > 5 else list(overlap)}")
            logger.info(f"[check_value_overlap] Overlap count: {len(overlap)}, Source count: {len(source_values)}, Ratio: {overlap_ratio:.2f}")
            
            # If more than 30% of source values are in target, consider it a FK
            if overlap_ratio >= 0.3:
                logger.info(f"[check_value_overlap] Value overlap between {source_table}.{source_col} and {target_table}.{target_col}: {overlap_ratio:.2f} - FK DETECTED")
                return True
        
        # If no match with primary column, try other columns that might contain matching values
        # Common columns that might contain IDs or references
        potential_id_columns = ['wikidata-id', 'wikidata-q-nummer', 'gnd-nummer', 'id', 'uuid']
        
        for potential_col_slug in potential_id_columns:
            potential_orig_col = next((c for c in target_df.columns if slugify_uri_part(c) == potential_col_slug), None)
            if not potential_orig_col or (target_orig_col and potential_orig_col == target_orig_col):
                continue
                
            logger.info(f"[check_value_overlap] Trying alternative target column: {potential_orig_col}")
            
            target_values = set(target_df[potential_orig_col].unique().to_list())
            target_values = {v for v in target_values if v is not None}
            
            logger.info(f"[check_value_overlap] Target values from {potential_orig_col} (sample): {list(target_values)[:5] if len(target_values) > 5 else list(target_values)}")
            
            # Check overlap
            overlap = source_values.intersection(target_values)
            overlap_ratio = len(overlap) / len(source_values) if source_values else 0
            
            logger.info(f"[check_value_overlap] Overlap values (sample): {list(overlap)[:5] if len(overlap) > 5 else list(overlap)}")
            logger.info(f"[check_value_overlap] Overlap count: {len(overlap)}, Source count: {len(source_values)}, Ratio: {overlap_ratio:.2f}")
            
            # If more than 30% of source values are in target, consider it a FK
            if overlap_ratio >= 0.3:
                logger.info(f"[check_value_overlap] Value overlap between {source_table}.{source_col} and {target_table}.{potential_col_slug}: {overlap_ratio:.2f} - FK DETECTED")
                return True
        
        logger.info(f"[check_value_overlap] Insufficient overlap between {source_table}.{source_col} and any column in {target_table} - NOT A FK")
        return False
    except Exception as e:
        logger.warning(f"[check_value_overlap] Error checking value overlap: {e}")
        return False


def mark_foreign_keys(pk_dict: Dict[str, List[Dict[str, Any]]], csv_file_paths: List[str], delimiter: str = ';', field_delimiter: str = ',') -> Dict[str, List[Dict[str, Any]]]:
    """
    For each table, mark columns that are likely foreign keys.
    Adds 'is_fk' and 'references' (table, column) if detected.
    Uses slugified names and PKs from other tables.
    Uses precise pattern matching to detect FKs, not just substring containment.
    For potential matches based on substring, verifies with value overlap.
    Prevents circular references between tables.
    
    Args:
        pk_dict: Dictionary of tables and their columns with PK flags
        csv_file_paths: List of CSV file paths
        delimiter: CSV delimiter (default ';')
        field_delimiter: Delimiter used within field values for multi-value FKs (default ',')
        
    Returns:
        Dictionary of tables and their columns with FK flags and references
    """
    # Build a map of all PKs: {table: [pk_col, ...]}
    table_to_path = {slugify_uri_part(os.path.splitext(os.path.basename(p))[0]): p for p in csv_file_paths}
    pk_map = {table: [c['name'] for c in cols if c['is_pk']] for table, cols in pk_dict.items()}
    logger.info(f"[mark_foreign_keys] PK map: {pk_map}")
    fk_dict = {}
    
    # Track detected FK relationships to prevent circular references
    detected_fk_relationships = set()
    
    # Log all columns that contain table names for debugging
    for table, columns in pk_dict.items():
        for col in columns:
            col_name = col['name']
            for target_table in pk_map.keys():
                if target_table != table and target_table in col_name:
                    logger.info(f"[mark_foreign_keys] POTENTIAL FK by name: {table}.{col_name} might reference {target_table}")
    
    for table, columns in pk_dict.items():
        logger.info(f"[mark_foreign_keys] Processing table: {table} with columns: {[c['name'] for c in columns]}")
        col_dicts = []
        for col in columns:
            is_fk = False
            references = None
            # Use precise pattern matching for FK detection
            for target_table, pk_cols in pk_map.items():
                if target_table == table:
                    continue
                
                # Skip if this would create a circular reference
                if (target_table, table) in detected_fk_relationships:
                    logger.info(f"[mark_foreign_keys] Skipping potential FK: {table}.{col['name']} -> {target_table} to avoid circular reference")
                    continue
                
                # Skip if the target table's PK is referencing this table's column
                # This prevents cases where both tables think they reference each other
                if col['is_pk'] and any(is_foreign_key_match(pk_col, table, col['name']) for pk_col in pk_cols):
                    logger.info(f"[mark_foreign_keys] Skipping potential FK: {table}.{col['name']} -> {target_table} to avoid bidirectional PK reference")
                    continue
                
                # Skip if this is a PK column and this table name is a substring of the target table name
                # This prevents false positives in the other direction
                if col['is_pk'] and table in target_table and table != target_table:
                    logger.info(f"[mark_foreign_keys] Skipping potential FK: {table}.{col['name']} -> {target_table} to avoid false positive with nested table names")
                    continue
                
                # Skip if this is a PK column and the target table name is a substring of this table name
                # This prevents cases like "ereignistyp.ereignistyp-id" being detected as FK to "ereignis" table
                if col['is_pk'] and target_table in table and table != target_table:
                    logger.info(f"[mark_foreign_keys] Skipping potential FK: {table}.{col['name']} -> {target_table} to avoid false positive with nested table names")
                    continue
                
                for pk_col in pk_cols:
                    pattern_match = is_foreign_key_match(col['name'], target_table, pk_col)
                    
                    # Log all pattern matches for debugging
                    if pattern_match:
                        logger.info(f"[mark_foreign_keys] Pattern match found: {table}.{col['name']} -> {target_table}.{pk_col}")
                    
                    # If it's a potential match based on substring (case 4 in is_foreign_key_match),
                    # verify with value overlap
                    if pattern_match and target_table in col['name'] and col['name'] != target_table:
                        logger.info(f"[mark_foreign_keys] Checking value overlap for potential FK: {table}.{col['name']} -> {target_table}.{pk_col}")
                        # This is a potential match based on substring, verify with value overlap
                        value_match = check_value_overlap(table, col['name'], target_table, pk_col, 
                                                         csv_file_paths, delimiter, field_delimiter)
                        if value_match:
                            is_fk = True
                            references = (target_table, pk_col)
                            detected_fk_relationships.add((table, target_table))
                            logger.info(f"[mark_foreign_keys] FK detected (pattern + value match): {table}.{col['name']} -> {target_table}.{pk_col}")
                            break
                        else:
                            logger.info(f"[mark_foreign_keys] Value check failed for potential FK: {table}.{col['name']} -> {target_table}.{pk_col}")
                    elif pattern_match:
                        # This is a strong pattern match (cases 1-3), no need for value verification
                        is_fk = True
                        references = (target_table, pk_col)
                        detected_fk_relationships.add((table, target_table))
                        logger.info(f"[mark_foreign_keys] FK detected (strong pattern match): {table}.{col['name']} -> {target_table}.{pk_col}")
                        break
                if is_fk:
                    break
            col_dict = dict(col)
            col_dict['is_fk'] = is_fk
            col_dict['references'] = references
            col_dicts.append(col_dict)
        fk_dict[table] = col_dicts
    return fk_dict


def generate_structure_report(table_column_dict, pk_dict, fk_dict):
    """
    Generate a human-readable report of the table structure, PKs, and FKs.
    Returns a string suitable for CLI or API output.
    """
    lines = []
    for table, columns in table_column_dict.items():
        lines.append(f"Table: {table}")
        pk_cols = [c['name'] for c in pk_dict.get(table, []) if c.get('is_pk')]
        lines.append(f"  Columns: {', '.join(columns)}")
        if pk_cols:
            lines.append(f"  Primary Key: {', '.join(pk_cols)}")
        else:
            lines.append(f"  Primary Key: (none detected)")
        fk_cols = [c for c in fk_dict.get(table, []) if c.get('is_fk')]
        if fk_cols:
            lines.append(f"  Foreign Keys:")
            for c in fk_cols:
                ref = c.get('references')
                if ref:
                    lines.append(f"    {c['name']} -> {ref[0]}.{ref[1]}")
                else:
                    lines.append(f"    {c['name']} (reference not resolved)")
        else:
            lines.append(f"  Foreign Keys: (none detected)")
        lines.append("")
    return "\n".join(lines)
