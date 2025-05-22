import re

# Base URIs
RDF_BASE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_BASE_URI = "http://www.w3.org/2000/01/rdf-schema#"
CIDOC_CRM_BASE_URI = "http://cidoc-crm.org/cidoc-crm/"
XSD_BASE_URI = "http://www.w3.org/2001/XMLSchema#"
OWL_BASE_URI = "http://www.w3.org/2002/07/owl#"
DEFAULT_INSTITUTION_BASE_URI = "http://arkumu.nrw/data/" 

def slugify_uri_part(value_str):
    """
    Slugifies a string for use in URIs: lowercase, spaces and special chars replaced with hyphens, 
    no underscores, only a-z, 0-9, and hyphens remain.
    """
    if not isinstance(value_str, str):
        value_str = str(value_str)
    
    # Basic transliteration for common German umlauts / common characters
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss',
        ' ': '-', '_': '-', '/': '-', '\\': '-', '?': '', '#': '', '&': 'and', '+': 'plus',
        '(': '', ')': '', '[': '', ']': '', '{': '', '}': '', '\'': '', '\"': '',
        '`': '', ':': '-', ';': '-', ',': '-', '.': '-', '=': '' 
    }
    for old, new in replacements.items():
        value_str = value_str.replace(old, new)
        
    value_str = value_str.lower()
    
    # Keep only alphanumeric characters and hyphens.
    value_str = re.sub(r'[^a-z0-9-]', '', value_str)
    
    # Replace multiple hyphens with a single hyphen
    value_str = re.sub(r'-+', '-', value_str)
    
    # Remove leading/trailing hyphens
    value_str = value_str.strip('-')
        
    if not value_str: 
        return "n-a" # Fallback for empty slugs
        
    return value_str

def mint_uri(base_uri_for_institution, institution_code_slug, *parts):
    """
    Mints a URI for a resource.
    Output format: <base_uri_for_institution>/<institution_code_slug>/<slugified_part1>/<slugified_part2>/...
    Assumes base_uri_for_institution already ends with a slash if that's the convention.
    institution_code_slug is pre-slugified.
    Other parts are slugified by this function.
    """
    slugged_dynamic_parts = []
    for p in parts:
        if p is None: # Skip None parts
            continue
        slugified = slugify_uri_part(str(p))
        if slugified and slugified != "n-a": # Keep non-empty, non-'n-a' slugs
            slugged_dynamic_parts.append(slugified)
        elif slugified == "n-a" and not any(part_val == "n-a" for part_val in slugged_dynamic_parts):
            # Allow one 'n-a' if value explicitly slugified to it, to represent missing optional part
            slugged_dynamic_parts.append("n-a") 

    if not slugged_dynamic_parts:
        # Fallback if no valid parts to form a URI path beyond institution
        slugged_dynamic_parts = ["unidentified-resource"]

    # Ensure base_uri_for_institution ends with a slash if it doesn't already
    # This is important for clean joining.
    effective_base_uri = base_uri_for_institution
    if not effective_base_uri.endswith('/'):
        effective_base_uri += '/'
        
    # Join parts, ensuring no double slashes if institution_code_slug or parts[0] might be empty (slugify handles this)
    uri_path = institution_code_slug + "/" + "/".join(slugged_dynamic_parts)
    
    # Avoid double slashes if uri_path accidentally starts with one (shouldn't if parts are clean)
    if uri_path.startswith('/'): # This can happen if institution_code_slug is empty
        uri_path = uri_path[1:]

    final_uri = effective_base_uri + uri_path
    # logger.debug(f"Minted URI: {final_uri}") # Logger won't be available here directly
    return final_uri 