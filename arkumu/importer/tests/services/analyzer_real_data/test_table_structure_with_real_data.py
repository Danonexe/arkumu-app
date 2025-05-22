import os
import glob
import pytest
from arkumu.importer.services.analyzer.table_structure import (
    get_table_column_dict, mark_primary_keys, mark_foreign_keys, generate_structure_report
)

@pytest.mark.skipif("REAL_DATA_DIR" not in os.environ, reason="Set REAL_DATA_DIR to run this test")
def test_table_structure_with_real_data():
    data_dir = os.environ.get("REAL_DATA_DIR")
    assert data_dir and os.path.isdir(data_dir), f"Data dir not found: {data_dir}"

    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    assert csv_files, "No CSV files found in the data directory"

    delimiter = ';'
    table_column_dict = get_table_column_dict(csv_files, delimiter=delimiter)
    pk_dict = mark_primary_keys(table_column_dict, csv_files, delimiter=delimiter)
    fk_dict = mark_foreign_keys(pk_dict, csv_files, delimiter=delimiter)
    report = generate_structure_report(table_column_dict, pk_dict, fk_dict)

    # Write the report to a file
    out_path = os.path.join(data_dir, "table_structure_report.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Table structure report written to: {out_path}")
    print(report)
    assert os.path.isfile(out_path)
