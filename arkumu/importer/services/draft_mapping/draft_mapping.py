from typing import Dict, Any, List
import os
from arkumu.importer.services.analyzer.table_structure import (
    get_table_column_dict, mark_primary_keys, mark_foreign_keys
)

def generate_draft_mapping_from_csvs(
    csv_file_paths: List[str],
    institution: str = "TODO",
    domain: str = "TODO",
    delimiter: str = ';'
) -> Dict[str, Any]:
    """
    Generate a draft mapping JSON for each CSV file based on table/column/PK/FK analysis.
    Returns a dict: {csv_file_name: mapping_json_dict}
    delimiter: The column delimiter to use when reading CSVs (default ';').
    """
    table_dict = get_table_column_dict(csv_file_paths, delimiter=delimiter)
    pk_dict = mark_primary_keys(table_dict, csv_file_paths, delimiter=delimiter)
    fk_dict = mark_foreign_keys(pk_dict, csv_file_paths, delimiter=delimiter)

    result = {}
    for path in csv_file_paths:
        file_name = os.path.basename(path)
        # Use the slugified table name as the key for fk_dict
        table_name = os.path.splitext(file_name)[0]
        slug_table_name = None
        # Find the matching slugified table name
        for t in fk_dict.keys():
            if t == table_name or file_name.startswith(t):
                slug_table_name = t
                break
        if not slug_table_name:
            # Fallback: slugify the table name
            from arkumu.importer.services.importer.uri_utils import slugify_uri_part
            slug_table_name = slugify_uri_part(table_name)
        columns = fk_dict.get(slug_table_name, [])
        # Find anchor column (PK)
        anchor_column = None
        for col in columns:
            if col.get('is_pk'):
                anchor_column = col['name']
                break
        if not anchor_column and columns:
            anchor_column = columns[0]['name']
        # Build mappings
        mappings = []
        for col in columns:
            mapping_entry = {
                "source_column": col['name'],
                "property": "",  # Placeholder
                "range": "",     # Placeholder
            }
            notes = []
            if col.get('is_pk'):
                notes.append("Primary key")
            if col.get('is_fk'):
                ref = col.get('references')
                if ref:
                    notes.append(f"Foreign key to {ref[0]}:{ref[1]}")
                    mapping_entry["object_column"] = ref[1]
            if notes:
                mapping_entry["note"] = "; ".join(notes)
            mappings.append(mapping_entry)
        mapping_json = {
            "institution": institution,
            "domain": domain,
            "anchor_column": anchor_column,
            "mappings": mappings
        }
        result[file_name] = mapping_json
    return result
