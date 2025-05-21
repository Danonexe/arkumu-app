import pytest
from arkumu.importer.services.draft_mapping.draft_mapping import generate_draft_mapping
from arkumu.importer.services.analyzer.analyze_csv import GlobalAnalysisReport, IntraCSVReport, ColumnProfile, CSVRelationship

def make_col(name, dtype='String', total_rows=4, unique_count=4, null_count=0, is_multivalued=False, detected_delimiter=None):
    return ColumnProfile(
        name=name,
        dtype=dtype,
        total_rows=total_rows,
        unique_count=unique_count,
        null_count=null_count,
        is_multivalued=is_multivalued,
        detected_delimiter=detected_delimiter
    )

def test_generate_draft_mapping_basic():
    # One CSV, one unique column, one multi-valued column
    cols = [
        make_col('ID', unique_count=4, null_count=0),
        make_col('Tags', unique_count=4, null_count=0, is_multivalued=True, detected_delimiter=';'),
        make_col('Other', unique_count=2, null_count=1)
    ]
    report = IntraCSVReport(file_path='test.csv', num_rows=4, num_cols=3, column_profiles=cols)
    analysis = GlobalAnalysisReport(intra_csv_reports=[report], relationships=[], errors={})
    result = generate_draft_mapping(analysis, institution='TEST', domain='DUMMY')
    mapping = result['test.csv']
    assert mapping['institution'] == 'TEST'
    assert mapping['domain'] == 'DUMMY'
    assert mapping['anchor_column'] == 'ID'
    assert mapping['column_delimiter'] == ';'
    tags_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'Tags')
    assert tags_entry['multi_valued'] is True
    assert tags_entry['delimiter'] == ';'
    assert 'Multi-valued' in tags_entry['note']
    id_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'ID')
    assert 'Primary key' in id_entry['note']
    # Placeholders
    assert tags_entry['property'] == ''
    assert tags_entry['range'] == ''

def test_generate_draft_mapping_with_relationship():
    # Two CSVs, one with a reference to the other
    cols1 = [make_col('ID', unique_count=3, null_count=0), make_col('Ref', unique_count=3, null_count=0)]
    cols2 = [make_col('TargetID', unique_count=3, null_count=0)]
    report1 = IntraCSVReport(file_path='a.csv', num_rows=3, num_cols=2, column_profiles=cols1)
    report2 = IntraCSVReport(file_path='b.csv', num_rows=3, num_cols=1, column_profiles=cols2)
    rel = CSVRelationship(
        source_file='a.csv', source_column='Ref',
        target_file='b.csv', target_column='TargetID',
        reason='Reference to b.csv:TargetID'
    )
    analysis = GlobalAnalysisReport(
        intra_csv_reports=[report1, report2],
        relationships=[rel],
        errors={}
    )
    result = generate_draft_mapping(analysis)
    mapping = result['a.csv']
    ref_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'Ref')
    assert 'Foreign key reference to b.csv:TargetID' in ref_entry['note']
    assert ref_entry['object_column'] == 'TargetID'

def test_generate_draft_mapping_with_multivalued_relationship():
    # Two CSVs, one with a multi-valued column referencing the other
    cols1 = [
        make_col('ID', unique_count=3, null_count=0),
        make_col('References', unique_count=3, null_count=0, is_multivalued=True, detected_delimiter=',')
    ]
    cols2 = [make_col('TargetID', unique_count=3, null_count=0)]
    report1 = IntraCSVReport(file_path='event.csv', num_rows=3, num_cols=2, column_profiles=cols1)
    report2 = IntraCSVReport(file_path='digital_object.csv', num_rows=3, num_cols=1, column_profiles=cols2)
    rel = CSVRelationship(
        source_file='event.csv', source_column='References',
        target_file='digital_object.csv', target_column='TargetID',
        reason='Foreign key: References contains references to digital_object.csv.TargetID (multi-valued)'
    )
    analysis = GlobalAnalysisReport(
        intra_csv_reports=[report1, report2],
        relationships=[rel],
        errors={}
    )
    result = generate_draft_mapping(analysis)
    mapping = result['event.csv']
    ref_entry = next(m for m in mapping['mappings'] if m['source_column'] == 'References')
    assert 'Foreign key reference to digital_object.csv:TargetID' in ref_entry['note']
    assert ref_entry['object_column'] == 'TargetID'
    assert ref_entry['multi_valued'] is True
    assert ref_entry['delimiter'] == ','

def test_generate_draft_mapping_no_multivalued():
    cols = [make_col('A', unique_count=2, null_count=0), make_col('B', unique_count=2, null_count=0)]
    report = IntraCSVReport(file_path='foo.csv', num_rows=2, num_cols=2, column_profiles=cols)
    analysis = GlobalAnalysisReport(intra_csv_reports=[report], relationships=[], errors={})
    result = generate_draft_mapping(analysis)
    mapping = result['foo.csv']
    assert mapping['column_delimiter'] is None
    for entry in mapping['mappings']:
        assert 'multi_valued' not in entry
        assert 'delimiter' not in entry
