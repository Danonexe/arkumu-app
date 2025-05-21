from typing import Dict, Any
from arkumu.importer.services.analyzer.analyze_csv import GlobalAnalysisReport

def generate_draft_mapping(
    analysis_report: GlobalAnalysisReport,
    institution: str = "TODO",
    domain: str = "TODO",
    anchor_column_strategy: str = "most_unique",  # or 'first', etc.
) -> Dict[str, Any]:
    """
    Generate a draft mapping JSON for each CSV file based on the analysis report.
    Returns a dict: {csv_file_name: mapping_json_dict}
    """
    # Build a lookup for relationships for quick access
    rels_by_source = {}
    for rel in analysis_report.relationships:
        rels_by_source.setdefault((rel.source_file, rel.source_column), []).append(rel)

    result = {}
    for report in analysis_report.intra_csv_reports:
        # Suggest anchor_column: most unique, non-null column
        anchor_column = None
        max_uniqueness = 0
        for col in report.column_profiles:
            if col.null_count == 0 and col.unique_count > max_uniqueness:
                anchor_column = col.name
                max_uniqueness = col.unique_count
        if not anchor_column and report.column_profiles:
            anchor_column = report.column_profiles[0].name

        # Suggest column_delimiter if any column is multi-valued
        column_delimiter = None
        for col in report.column_profiles:
            if col.is_multivalued and col.detected_delimiter:
                column_delimiter = col.detected_delimiter
                break

        # Build mappings
        mappings = []
        for col in report.column_profiles:
            mapping_entry = {
                "source_column": col.name,
                "property": "",  # Placeholder
                "range": "",      # Placeholder
            }
            notes = []
            if col.is_multivalued:
                mapping_entry["multi_valued"] = True
                mapping_entry["delimiter"] = col.detected_delimiter
                notes.append(f"Multi-valued column, delimiter: '{col.detected_delimiter}'")
            
            # Add relationship notes and object_column for foreign keys
            rels = rels_by_source.get((report.file_path, col.name), [])
            for rel in rels:
                # Use more definitive language for foreign keys
                if rel.is_foreign_key:
                    notes.append(f"Foreign key to {rel.target_file}:{rel.target_column}")
                else:
                    notes.append(f"Reference to {rel.target_file}:{rel.target_column}")
                # Add object_column for foreign key relationships
                mapping_entry["object_column"] = rel.target_column
            
            # Use more definitive language for primary keys
            col_lower = col.name.lower()
            if col.unique_count == report.num_rows and col.null_count == 0:
                # Check for ID or UUID column patterns
                if (col_lower.endswith('_id') or col_lower.endswith('-id') or 
                    col_lower == 'id' or col_lower.endswith('_uuid') or 
                    col_lower.endswith('-uuid') or col_lower == 'uuid'):
                    notes.append("Primary key")
                else:
                    # Still definitive but different wording for non-standard names
                    notes.append("Unique identifier (primary key)")
            # Add note for high-uniqueness columns that aren't quite primary keys
            elif col.unique_count > 0 and col.unique_count / report.num_rows > 0.95:
                notes.append("Nearly unique identifier (possible alternate key)")
            
            if notes:
                mapping_entry["note"] = "; ".join(notes)
            mappings.append(mapping_entry)

        mapping_json = {
            "institution": institution,
            "domain": domain,
            "anchor_column": anchor_column,
            "column_delimiter": column_delimiter,
            "mappings": mappings
        }
        result[report.file_path] = mapping_json
    return result
