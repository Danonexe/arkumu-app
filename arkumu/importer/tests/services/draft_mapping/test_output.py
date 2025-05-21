import os
import json
import tempfile
from arkumu.importer.services.draft_mapping.output import write_draft_mappings_to_files, write_single_draft_mapping

def test_write_single_draft_mapping(tmp_path):
    mapping = {
        "institution": "TEST",
        "domain": "DUMMY",
        "anchor_column": "ID",
        "column_delimiter": ";",
        "mappings": [
            {"source_column": "ID", "property": "", "range": "", "note": "Likely identifier"}
        ]
    }
    out_path = tmp_path / "test_draft_mapping.json"
    write_single_draft_mapping(mapping, str(out_path))
    assert out_path.exists()
    with open(out_path, encoding='utf-8') as f:
        data = json.load(f)
    assert data["institution"] == "TEST"
    assert data["anchor_column"] == "ID"
    assert data["mappings"][0]["source_column"] == "ID"

def test_write_draft_mappings_to_files(tmp_path):
    mappings = {
        "foo.csv": {
            "institution": "A",
            "domain": "B",
            "anchor_column": "foo",
            "column_delimiter": None,
            "mappings": [
                {"source_column": "foo", "property": "", "range": ""}
            ]
        },
        "bar.csv": {
            "institution": "C",
            "domain": "D",
            "anchor_column": "bar",
            "column_delimiter": ",",
            "mappings": [
                {"source_column": "bar", "property": "", "range": "", "multi_valued": True, "delimiter": ","}
            ]
        }
    }
    write_draft_mappings_to_files(mappings, str(tmp_path))
    foo_path = tmp_path / "foo_draft_mapping.json"
    bar_path = tmp_path / "bar_draft_mapping.json"
    assert foo_path.exists()
    assert bar_path.exists()
    with open(foo_path, encoding='utf-8') as f:
        foo_data = json.load(f)
    with open(bar_path, encoding='utf-8') as f:
        bar_data = json.load(f)
    assert foo_data["institution"] == "A"
    assert bar_data["institution"] == "C"
    assert bar_data["mappings"][0]["multi_valued"] is True
    assert bar_data["mappings"][0]["delimiter"] == ","
