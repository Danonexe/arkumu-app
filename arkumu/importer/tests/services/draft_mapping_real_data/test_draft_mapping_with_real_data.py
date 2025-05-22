import os
import glob
import json
import pytest
from arkumu.importer.services.draft_mapping.draft_mapping import generate_draft_mapping_from_csvs
from arkumu.importer.services.draft_mapping.output import write_draft_mappings_to_files

@pytest.mark.skipif("REAL_DATA_DIR" not in os.environ, reason="Set REAL_DATA_DIR to run this test")
def test_generate_draft_mappings_with_real_data():
    data_dir = os.environ.get("REAL_DATA_DIR")
    assert data_dir and os.path.isdir(data_dir), f"Data dir not found: {data_dir}"

    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    assert csv_files, "No CSV files found in the data directory"

    draft_mappings = generate_draft_mapping_from_csvs(csv_files, institution="REALDATA", domain="TODO", delimiter=';')

    # Write mapping files to the same directory as the CSVs
    write_draft_mappings_to_files(draft_mappings, data_dir)

    out_files = sorted(f for f in os.listdir(data_dir) if f.endswith('_draft_mapping.json'))
    print(f"Generated mapping files in {data_dir}: {out_files}")
    for fname in out_files[:1]:
        with open(os.path.join(data_dir, fname), encoding='utf-8') as f:
            mapping = json.load(f)
            print(json.dumps(mapping, indent=2, ensure_ascii=False))
    assert out_files
