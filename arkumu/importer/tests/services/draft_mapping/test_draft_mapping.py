import os
import tempfile
import polars as pl
import pytest
from arkumu.importer.services.draft_mapping.draft_mapping import generate_draft_mapping_from_csvs

def create_temp_csv(headers, rows, dir=None):
    fd, path = tempfile.mkstemp(suffix='.csv', dir=dir)
    os.close(fd)
    df = pl.DataFrame({h: [row[i] for row in rows] for i, h in enumerate(headers)})
    df.write_csv(path)
    return path

def test_generate_draft_mapping_basic():
    headers = ['ID', 'Tags', 'Other']
    rows = [
        [1, 'a;b', 'x'],
        [2, 'c;d', 'y'],
        [3, 'e;f', 'z'],
        [4, 'g;h', None],
    ]
    path = create_temp_csv(headers, rows)
    try:
        result = generate_draft_mapping_from_csvs([path], institution='TEST', domain='DUMMY', delimiter=';')
        mapping = result[os.path.basename(path)]
        assert mapping['institution'] == 'TEST'
        assert mapping['domain'] == 'DUMMY'
        assert mapping['anchor_column'] == 'id'
        tags_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'tags')
        # No multi_valued/delimiter logic in new draft, but PK note should be present
        id_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'id')
        assert 'Primary key' in id_entry.get('note', '')
        # Placeholders
        assert tags_entry['property'] == ''
        assert tags_entry['range'] == ''
    finally:
        os.remove(path)

def test_generate_draft_mapping_with_fk():
    # Table 1: event.csv
    headers1 = ['id', 'name']
    rows1 = [
        [100, 'EventA'],
        [101, 'EventB'],
    ]
    path1 = create_temp_csv(headers1, rows1)
    # Table 2: person.csv
    headers2 = ['id', 'name', 'event_id']
    rows2 = [
        [1, 'Alice', 100],
        [2, 'Bob', 101],
    ]
    path2 = create_temp_csv(headers2, rows2)
    try:
        result = generate_draft_mapping_from_csvs([path1, path2], delimiter=';')
        person_mapping = result[os.path.basename(path2)]
        event_id_entry = next(m for m in person_mapping['mappings'] if m['source_column'] == 'eventid')
        assert 'Foreign key' in event_id_entry.get('note', '')
        assert event_id_entry['object_column'] == 'id'
    finally:
        os.remove(path1)
        os.remove(path2)

def test_generate_draft_mapping_no_multivalued():
    headers = ['A', 'B']
    rows = [
        [1, 2],
        [3, 4],
    ]
    path = create_temp_csv(headers, rows)
    try:
        result = generate_draft_mapping_from_csvs([path], delimiter=';')
        mapping = result[os.path.basename(path)]
        for entry in mapping['mappings']:
            assert 'multi_valued' not in entry
            assert 'delimiter' not in entry
    finally:
        os.remove(path)
