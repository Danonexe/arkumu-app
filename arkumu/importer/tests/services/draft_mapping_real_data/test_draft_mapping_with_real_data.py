import os
import json
import pytest
from arkumu.importer.services.draft_mapping.draft_mapping import generate_draft_mapping_from_csvs, generate_relationship_config

@pytest.mark.skipif(
    not os.environ.get("REAL_DATA_DIR"),
    reason="REAL_DATA_DIR environment variable not set"
)
def test_draft_mapping_with_real_data():
    """Generate draft mapping JSON files for each CSV file in the real data directory."""
    # Get the directory containing the CSV files
    real_data_dir = os.environ.get("REAL_DATA_DIR")
    csv_files = [
        os.path.join(real_data_dir, f)
        for f in os.listdir(real_data_dir)
        if f.endswith('.csv')
    ]
    
    if not csv_files:
        print(f"No CSV files found in {real_data_dir}")
        return
    
    # First, generate relationship configuration
    relationship_config = generate_relationship_config(
        csv_files,
        output_path=os.path.join(real_data_dir, "relationship_tables.json"),
        delimiter=';',
        has_quoted_fields=True
    )
    
    # Print detected relationship tables
    print(f"Detected {len(relationship_config)} relationship tables:")
    for table_name, fk_config in relationship_config.items():
        print(f"  - {table_name} with {len(fk_config)} foreign key columns:")
        for fk in fk_config:
            print(f"    * {fk['column']} → {fk['target_table']}.{fk['target_column']}")
    
    # Convert relationship config to relationship hints format
    relationship_hints = {}
    for table_name, fk_configs in relationship_config.items():
        for fk_config in fk_configs:
            column = fk_config['column']
            relationship_hints[column] = {
                "target_table": fk_config['target_table'],
                "target_column": fk_config['target_column']
            }
    
    # Generate draft mappings with relationship hints
    draft_mappings = generate_draft_mapping_from_csvs(
        csv_files, 
        institution="Test Institution", 
        domain="Test Domain",
        delimiter=';',
        field_delimiter=',',
        has_quoted_fields=True,
        relationship_hints=relationship_hints
    )
    
    # Track statistics
    multi_valued_columns = {}
    relationship_columns = {}
    
    # Write each mapping to a JSON file with the same name as the CSV file plus "_draft" suffix
    for csv_filename, mapping in draft_mappings.items():
        # Get the base filename without path
        base_filename = os.path.basename(csv_filename)
        
        # Generate output path
        output_file = os.path.join(
            real_data_dir,
            os.path.splitext(base_filename)[0] + "_draft.json"
        )
        
        # Count multi-valued columns
        mv_cols = [m['source_column'] for m in mapping['mappings'] if 'multi_valued' in m and m['multi_valued']]
        if mv_cols:
            multi_valued_columns[base_filename] = mv_cols
        
        # Count relationship columns
        rel_cols = [m['source_column'] for m in mapping['mappings'] if 'relationship_type' in m]
        if rel_cols:
            relationship_columns[base_filename] = rel_cols
        
        # Save the mapping as JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
            
        print(f"Generated draft mapping: {output_file}")
        print(f"  * Domain: {mapping['domain']}")
        print(f"  * Anchor column: {mapping['anchor_column']}")
        print(f"  * Multi-valued columns: {len(mv_cols)}")
        print(f"  * Relationship columns: {len(rel_cols)}")
    
    # Print summary of multi-valued columns
    if multi_valued_columns:
        print("\nDetected multi-valued columns:")
        for filename, columns in multi_valued_columns.items():
            print(f"  - {filename}: {', '.join(columns)}")
    
    # Print summary of relationship columns
    if relationship_columns:
        print("\nDetected relationship columns:")
        for filename, columns in relationship_columns.items():
            print(f"  - {filename}: {', '.join(columns)}")
    
    # Verify files were created
    for csv_filename in draft_mappings:
        base_filename = os.path.basename(csv_filename)
        output_file = os.path.join(
            real_data_dir,
            os.path.splitext(base_filename)[0] + "_draft.json"
        )
        assert os.path.isfile(output_file) 