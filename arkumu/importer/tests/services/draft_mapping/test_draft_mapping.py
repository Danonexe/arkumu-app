#!/usr/bin/env python3
import os
import json
import sys
from pprint import pprint

# Add the project root to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from arkumu.importer.services.draft_mapping.draft_mapping import generate_draft_mapping_from_csvs, generate_relationship_config

def test_draft_mapping():
    """Test the draft mapping generation with real CSV files."""
    # Path to your CSV files
    csv_dir = os.path.join(os.path.dirname(__file__), 'arkumu-metadata', 'khm', 'khm-projektarchiv')
    
    if not os.path.exists(csv_dir):
        print(f"CSV directory not found: {csv_dir}")
        return
    
    # Get all CSV files in the directory
    csv_files = [os.path.join(csv_dir, f) for f in os.listdir(csv_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print(f"No CSV files found in {csv_dir}")
        return
    
    print(f"Found {len(csv_files)} CSV files:")
    for f in csv_files:
        print(f"  - {os.path.basename(f)}")
    
    # Create output directory
    output_dir = os.path.join(os.path.dirname(__file__), 'test_output')
    os.makedirs(output_dir, exist_ok=True)
    
    # Test relationship configuration generation first
    print("\nGenerating relationship configuration...")
    relationship_config = generate_relationship_config(
        csv_files,
        output_path=os.path.join(output_dir, "relationship_tables.json"),
        delimiter=';',
        has_quoted_fields=True
    )
    
    print(f"Detected {len(relationship_config)} relationship tables:")
    for table_name, fk_config in relationship_config.items():
        print(f"  - {table_name} with {len(fk_config)} foreign key columns:")
        for fk in fk_config:
            print(f"    * {fk['column']} → {fk['target_table']}.{fk['target_column']}")
    
    # Test draft mapping generation with relationship hints
    print("\nGenerating draft mappings...")
    
    # Convert relationship config to relationship hints format
    relationship_hints = {}
    for table_name, fk_configs in relationship_config.items():
        for fk_config in fk_configs:
            column = fk_config['column']
            relationship_hints[column] = {
                "target_table": fk_config['target_table'],
                "target_column": fk_config['target_column']
            }
    
    mappings = generate_draft_mapping_from_csvs(
        csv_files,
        institution="KHM",
        delimiter=';',
        has_quoted_fields=True,
        relationship_hints=relationship_hints
    )
    
    # Save mappings to files and analyze results
    multi_valued_columns = {}
    relationship_columns = {}
    
    for filename, mapping in mappings.items():
        output_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_draft.json")
        with open(output_path, 'w') as f:
            json.dump(mapping, f, indent=2)
        
        # Count multi-valued columns
        mv_cols = [m['source_column'] for m in mapping['mappings'] if 'multi_valued' in m and m['multi_valued']]
        if mv_cols:
            multi_valued_columns[filename] = mv_cols
        
        # Count relationship columns
        rel_cols = [m['source_column'] for m in mapping['mappings'] if 'relationship_type' in m]
        if rel_cols:
            relationship_columns[filename] = rel_cols
        
        print(f"  - Generated mapping for {filename}")
        print(f"    * Domain: {mapping['domain']}")
        print(f"    * Anchor column: {mapping['anchor_column']}")
        print(f"    * Multi-valued columns: {len(mv_cols)}")
        print(f"    * Relationship columns: {len(rel_cols)}")
    
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
    
    print("\nTest completed successfully!")
    print(f"Output files saved to {output_dir}")

if __name__ == "__main__":
    test_draft_mapping() 