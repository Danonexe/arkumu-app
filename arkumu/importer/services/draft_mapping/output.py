import os
import json
from typing import Dict, Any

def write_draft_mappings_to_files(draft_mappings: Dict[str, Any], output_dir: str):
    """
    Write each draft mapping to a JSON file in the output directory.
    Each file is named <csv_basename>_draft_mapping.json
    """
    os.makedirs(output_dir, exist_ok=True)
    for csv_name, mapping in draft_mappings.items():
        base = os.path.splitext(csv_name)[0]
        out_path = os.path.join(output_dir, f'{base}_draft_mapping.json')
        write_single_draft_mapping(mapping, out_path)

def write_single_draft_mapping(mapping: Dict[str, Any], output_path: str):
    """
    Write a single mapping dictionary to a JSON file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
