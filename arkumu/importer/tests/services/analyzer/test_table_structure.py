import os
import tempfile
import polars as pl
import pytest
from arkumu.importer.services.analyzer import table_structure

def create_temp_csv(headers, rows, dir=None):
    fd, path = tempfile.mkstemp(suffix='.csv', dir=dir)
    os.close(fd)
    df = pl.DataFrame({h: [row[i] for row in rows] for i, h in enumerate(headers)})
    df.write_csv(path, separator=';')
    return path

def test_get_table_column_dict_and_normalization():
    headers = ['ID', 'Name', 'Event_ID']
    rows = [
        [1, 'Alice', 100],
        [2, 'Bob', 101],
    ]
    path = create_temp_csv(headers, rows)
    try:
        result = table_structure.get_table_column_dict([path], delimiter=';')
        table_name = table_structure.slugify_uri_part(os.path.splitext(os.path.basename(path))[0])
        assert table_name in result
        assert set(result[table_name]) == {'id', 'name', 'eventid'}
    finally:
        os.remove(path)

def test_mark_primary_keys_basic():
    headers = ['id', 'name', 'event_id']
    rows = [
        [1, 'Alice', 100],
        [2, 'Bob', 101],
    ]
    path = create_temp_csv(headers, rows)
    try:
        table_dict = table_structure.get_table_column_dict([path], delimiter=';')
        pk_dict = table_structure.mark_primary_keys(table_dict, [path], delimiter=';')
        table_name = list(pk_dict.keys())[0]
        pk_cols = [c for c in pk_dict[table_name] if c['is_pk']]
        assert len(pk_cols) == 1
        assert pk_cols[0]['name'] == 'id'
    finally:
        os.remove(path)

def test_mark_primary_keys_fallback():
    headers = ['foo', 'bar']
    rows = [
        [1, 'x'],
        [2, 'y'],
    ]
    path = create_temp_csv(headers, rows)
    try:
        table_dict = table_structure.get_table_column_dict([path], delimiter=';')
        pk_dict = table_structure.mark_primary_keys(table_dict, [path], delimiter=';')
        table_name = list(pk_dict.keys())[0]
        pk_cols = [c for c in pk_dict[table_name] if c['is_pk']]
        assert len(pk_cols) == 1
        assert pk_cols[0]['name'] == 'foo'  # fallback to first column
    finally:
        os.remove(path)

def test_mark_foreign_keys():
    # Table 1: event.csv
    headers1 = ['id', 'name']
    rows1 = [
        [100, 'EventA'],
        [101, 'EventB'],
    ]
    path1 = create_temp_csv(headers1, rows1)
    # Table 2: person.csv
    headers2 = ['id', 'name', 'event-id']  # Use 'event-id' to match semantic FK detection
    rows2 = [
        [1, 'Alice', 100],
        [2, 'Bob', 101],
    ]
    path2 = create_temp_csv(headers2, rows2)
    try:
        table_dict = table_structure.get_table_column_dict([path1, path2], delimiter=';')
        pk_dict = table_structure.mark_primary_keys(table_dict, [path1, path2], delimiter=';')
        fk_dict = table_structure.mark_foreign_keys(pk_dict, [path1, path2], delimiter=';')
        # Use the actual slugified table names from the temp files
        person_table = table_structure.slugify_uri_part(os.path.splitext(os.path.basename(path2))[0])
        event_table = table_structure.slugify_uri_part(os.path.splitext(os.path.basename(path1))[0])
        event_id_col = next(c for c in fk_dict[person_table] if c['name'] == 'event-id')
        assert event_id_col['is_fk']
        assert event_id_col['references'][0] == event_table
        assert event_id_col['references'][1] == 'id'
    finally:
        os.remove(path1)
        os.remove(path2)
