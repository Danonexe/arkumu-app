import logging
from datetime import datetime
from arkumu.importer.services.importer.uri_utils import XSD_BASE_URI # For infer_datatype
import unicodedata
from typing import Dict, List,  Any

# It's common to use the module's logger for utility functions
# or allow a logger to be passed in if more specific context is needed from the caller.
logger = logging.getLogger(__name__) # This will be arkumu.importer.services.data_utils

def extract_expected_source_columns(mappings_list):
    """Extracts all unique source_column names from the mapping rules, including nested ones."""
    # Using the passed logger if different logging context is desired by caller:
    # current_logger = passed_logger or logger 
    # current_logger.debug("Extracting expected source columns from mapping rules")
    logger.debug("Extracting expected source columns from mapping rules")
    expected_columns = set()
    for rule in mappings_list:
        if rule.get('source_column'):
            expected_columns.add(rule['source_column'])
        
        object_props = rule.get('object_properties', [])
        for sub_rule in object_props:
            if sub_rule.get('source_column'):
                expected_columns.add(sub_rule['source_column'])

    logger.debug(f"Found {len(expected_columns)} expected columns: {expected_columns}")
    return expected_columns

def validate_source_headers(expected_columns_set, actual_headers_list):
    """
    Validates a list of actual source headers against expected headers.
    Args:
        expected_columns_set (set): The headers expected based on the mapping.
        actual_headers_list (list or set): The headers found in the source data.
    Returns:
        dict: A dictionary with 'missing_critical_headers' and 'extra_headers'.
              Raises ValueError if critical headers are missing.
    """
    logger.info(f"Validating {len(actual_headers_list)} source headers against {len(expected_columns_set)} expected columns")
    actual_headers_set = set(actual_headers_list)
    missing_critical = expected_columns_set - actual_headers_set
    extra_headers = actual_headers_set - expected_columns_set

    if missing_critical:
        missing_list = sorted(list(missing_critical))
        logger.error(f"Critical columns missing: {', '.join(missing_list)}")
        raise ValueError(
            f"Critical columns from mapping are missing in the source data headers: "
            f"{missing_list}. Please check the source file or mapping."
        )
    
    if extra_headers:
        logger.info(f"Found {len(extra_headers)} extra headers not in mapping: {sorted(list(extra_headers))}")
    else:
        logger.info("All headers match expected columns exactly")
        
    result = {
        "missing_critical_headers": list(missing_critical),
        "extra_headers": sorted(list(extra_headers)),
        "all_expected_present": not bool(missing_critical)
    }
    return result

def infer_datatype(value):
    # Basic inference, extend as needed. Uses XSD_BASE_URI from uri_utils.
    if isinstance(value, int):
        return f"{XSD_BASE_URI}integer"
    if isinstance(value, float):
        return f"{XSD_BASE_URI}float"
    if isinstance(value, str):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return f"{XSD_BASE_URI}date"
        except ValueError:
            pass
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
            return f"{XSD_BASE_URI}dateTime"
        except ValueError:
            pass
    return f"{XSD_BASE_URI}string"  # Default

def infer_language(rule, row_data):
    # Check for explicit language in the rule
    if 'language' in rule:
        lang = rule['language']
        logger.debug(f"Using explicit language from rule: {lang}")
        return lang
    
    lang_column = rule.get('language_column')
    if lang_column and lang_column in row_data:
        lang = row_data[lang_column]
        logger.debug(f"Using language from column '{lang_column}': {lang}")
        return lang
        
    logger.debug("No language identified")
    return None

def split_multi_values(rule, value):
    """Splits a value into multiple values if needed based on the rule."""
    if not isinstance(value, str):
        logger.debug(f"Value is not a string, not splitting: {type(value)}")
        return [value]
        
    separator = rule.get('multi_value_separator')
    used_default_separator = False

    if not separator and rule.get('multi_valued') == True:
        separator = ';' # Default separator
        used_default_separator = True
        logger.debug(f"Using default separator '{separator}' because 'multi_valued': True and no explicit separator found.")

    if separator:
        logger.debug(f"Splitting by {'default' if used_default_separator else 'explicit'} separator: '{separator}'")
        result = [val.strip() for val in value.split(separator) if val.strip()]
        logger.debug(f"Split into {len(result)} values")
        return result
        
    note = rule.get('note', '').lower()
    if "separated by a ';'" in note:
        logger.debug("Splitting by semicolon based on note hint")
        result = [val.strip() for val in value.split(';') if val.strip()]
        logger.debug(f"Split into {len(result)} values")
        return result
        
    logger.debug("No splitting needed")
    return [value]

def lookup_related_data(rule, source_value, related_sources_dict):
    """
    Looks up related data based on the rule and source value.
    Returns a dictionary of found values or None if not applicable.
    related_sources_dict is the dictionary of pre-loaded related data.
    """
    if not rule.get('lookup_type'):
        logger.debug("No lookup_type specified, skipping related data lookup")
        return None
        
    lookup_type = rule['lookup_type']
    logger.debug(f"Performing lookup of type: {lookup_type}")
    
    if lookup_type != 'related_table_literal':
        logger.warning(f"Unsupported lookup_type: {lookup_type}")
        return None
        
    related_source_name = rule.get('related_source')
    if not related_source_name or related_source_name not in related_sources_dict:
        logger.warning(f"Related source '{related_source_name}' not found for lookup")
        return None
        
    related_source = related_sources_dict[related_source_name]
    lookup_key_column = rule.get('related_source_key_column', 'id')
    lookup_value_column = rule.get('related_source_value_column')
    lookup_language_column = rule.get('related_source_language_column')
    
    logger.debug(f"Looking up value '{source_value}' in related source '{related_source_name}' "
                 f"key column: '{lookup_key_column}', value column: '{lookup_value_column}'")
    
    if not lookup_value_column:
        logger.warning("No value column specified for lookup in related source")
        return None
        
    if isinstance(related_source, list):
        for item in related_source:
            if str(item.get(lookup_key_column)) == str(source_value):
                result = {
                    'value': item.get(lookup_value_column)
                }
                if lookup_language_column and lookup_language_column in item:
                    result['language'] = item[lookup_language_column]
                logger.debug(f"Found value in related source: {result}")
                return result
                
    logger.warning(f"Could not find value for '{source_value}' in related source")
    return None 

def normalize_string_nfc(text: str) -> str:
    """
    Normalize a string to Unicode NFC (Normalization Form Canonical Composition).
    
    Args:
        text: The string to normalize
        
    Returns:
        The normalized string
    """
    if not isinstance(text, str):
        return text
        
    return unicodedata.normalize('NFC', text)

def normalize_dict_values_nfc(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply NFC normalization to all string values in a dictionary.
    
    Args:
        data: Dictionary with potentially unnormalized string values
        
    Returns:
        Dictionary with all string values normalized to NFC
    """
    result = {}
    for k, v in data.items():
        if isinstance(v, str):
            result[k] = normalize_string_nfc(v)
        else:
            result[k] = v
    return result

def normalize_csv_data_nfc(data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply NFC normalization to all string values in a list of dictionaries.
    
    This is particularly useful for normalizing CSV data loaded as dictionaries.
    
    Args:
        data_list: List of dictionaries (e.g., from reading a CSV)
        
    Returns:
        List of dictionaries with all string values normalized to NFC
    """
    return [normalize_dict_values_nfc(item) for item in data_list]

def read_csv_with_nfc(file_path: str, delimiter: str = ';', **csv_options) -> List[Dict[str, Any]]:
    """
    Read a CSV file and normalize all string values to NFC.
    
    Args:
        file_path: Path to the CSV file
        delimiter: Column delimiter (default is semicolon)
        csv_options: Additional options to pass to polars.read_csv
        
    Returns:
        List of dictionaries with all string values normalized to NFC
    """
    import polars as pl
    
    # Set default options that work well with our data
    options = {
        'separator': delimiter,
        'infer_schema_length': 0,
        'truncate_ragged_lines': True
    }
    
    # Override with any user-provided options
    options.update(csv_options)
    
    # Read the CSV file
    df = pl.read_csv(file_path, **options)
    
    # Convert to list of dictionaries
    data = df.to_dicts()
    
    # Normalize all string values
    return normalize_csv_data_nfc(data) 