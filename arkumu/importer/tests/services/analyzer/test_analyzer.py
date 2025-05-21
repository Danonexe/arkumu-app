import tempfile
import os
import polars as pl
import pytest
from arkumu.importer.services.analyzer.analyze_csv import analyze_single_csv, analyze_csv_data, find_relationships

def write_csv(path, content):
    with open(path, 'w') as f:
        f.write(content)

def test_analyze_single_csv_basic():
    """Test basic CSV analysis with column profiling."""
    csv_content = """id;name;age\n1;Alice;30\n2;Bob;25\n3;Charlie;30\n4;;\n"""
    with tempfile.NamedTemporaryFile('w+', suffix='.csv', delete=False) as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        report = analyze_single_csv(tmp_path, delimiter=';')
        assert report is not None
        assert report.num_rows == 4
        assert report.num_cols == 3
        
        # Check column profiles
        col_names = [c.name for c in report.column_profiles]
        assert set(col_names) == {'id', 'name', 'age'}
        
        id_col = next(c for c in report.column_profiles if c.name == 'id')
        assert id_col.unique_count == 4
        assert id_col.null_count == 0
        
        name_col = next(c for c in report.column_profiles if c.name == 'name')
        assert name_col.null_count == 1
        
        age_col = next(c for c in report.column_profiles if c.name == 'age')
        assert age_col.null_count == 1
    finally:
        os.unlink(tmp_path)

def test_multivalued_column_detection():
    """Test detection of multi-valued columns with different delimiters."""
    csv_content = """id;tags;items
1;a,b,c;x|y|z
2;d,e;a|b
3;f;c
4;;
"""
    with tempfile.NamedTemporaryFile('w+', suffix='.csv', delete=False) as tmp:
        tmp.write(csv_content)
        tmp_path = tmp.name
    try:
        report = analyze_single_csv(tmp_path, delimiter=';')
        
        # Check tags column (comma delimiter)
        tags_col = next(c for c in report.column_profiles if c.name == 'tags')
        assert tags_col.is_multivalued is True
        assert tags_col.detected_delimiter == ','
        
        # Check items column (pipe delimiter)
        items_col = next(c for c in report.column_profiles if c.name == 'items')
        assert items_col.is_multivalued is True
        assert items_col.detected_delimiter == '|'
        
        # Check id column (not multi-valued)
        id_col = next(c for c in report.column_profiles if c.name == 'id')
        assert id_col.is_multivalued is False
        assert id_col.detected_delimiter is None
    finally:
        os.unlink(tmp_path)

def test_comprehensive_relationship_detection(tmp_path):
    """
    Test all types of relationship detection with a comprehensive schema.
    This test creates a mini-database with multiple tables and various relationship types:
    - Direct ID pattern relationships (person_id -> person.id)
    - Direct table name matches (department -> department.id)
    - Multi-valued columns (tags -> tag.id)
    - Name similarity (digital_object -> digital_object.id)
    - Multiple foreign keys in one table
    """
    # Create person.csv with id as primary key
    person_path = tmp_path / "person.csv"
    person_path.write_text("id;name\n1;Alice\n2;Bob\n3;Charlie\n")
    
    # Create department.csv with id as primary key
    dept_path = tmp_path / "department.csv"
    dept_path.write_text("id;name\n10;HR\n20;IT\n30;Finance\n")
    
    # Create tag.csv with id as primary key
    tag_path = tmp_path / "tag.csv"
    tag_path.write_text("id;name\nt1;Important\nt2;Urgent\nt3;Review\n")
    
    # Create digital_object.csv with digital_object_id as primary key
    object_path = tmp_path / "digital_object.csv"
    object_path.write_text("digital_object_id;name\nobj1;Photo1\nobj2;Photo2\nobj3;Photo3\n")
    
    # Create event.csv with multiple foreign keys of different types
    event_path = tmp_path / "event.csv"
    event_path.write_text("""id;name;person_id;department;tags;Digitales Objekt
e1;Meeting;1;10;t1,t2;obj1
e2;Conference;2;20;t2,t3;obj2
e3;Party;3;30;t1;obj3
""")
    
    # Find relationships
    relationships = find_relationships([
        str(person_path), 
        str(dept_path), 
        str(tag_path), 
        str(object_path), 
        str(event_path)
    ], delimiter=';')
    
    # Check that all relationships were found
    assert len(relationships) >= 4
    
    # Check person_id -> person.id (ID pattern)
    person_rel = next((r for r in relationships 
                      if r.source_file == "event.csv" and r.source_column == "person_id"), None)
    assert person_rel is not None
    assert person_rel.target_file == "person.csv"
    assert person_rel.target_column == "id"
    assert "name pattern" in person_rel.reason.lower()
    
    # Check department -> department.id (table name match)
    dept_rel = next((r for r in relationships 
                    if r.source_file == "event.csv" and r.source_column == "department"), None)
    assert dept_rel is not None
    assert dept_rel.target_file == "department.csv"
    assert dept_rel.target_column == "id"
    assert "name" in dept_rel.reason.lower() or "value" in dept_rel.reason.lower()
    
    # Check tags -> tag.id (multi-valued column)
    tags_rel = next((r for r in relationships 
                    if r.source_file == "event.csv" and r.source_column == "tags"), None)
    assert tags_rel is not None
    assert tags_rel.target_file == "tag.csv"
    assert tags_rel.target_column == "id"
    
    # Check "Digitales Objekt" -> digital_object.digital_object_id (name similarity)
    obj_rel = next((r for r in relationships 
                   if r.source_file == "event.csv" and r.source_column == "Digitales Objekt"), None)
    assert obj_rel is not None
    assert obj_rel.target_file == "digital_object.csv"
    assert obj_rel.target_column == "digital_object_id"
    assert "similarity" in obj_rel.reason.lower() or "value" in obj_rel.reason.lower()

def test_analyze_csv_data_integration(tmp_path):
    """Test the full analyze_csv_data function with a comprehensive schema."""
    # Create the same schema as in the comprehensive test
    person_path = tmp_path / "person.csv"
    person_path.write_text("id;name\n1;Alice\n2;Bob\n3;Charlie\n")
    
    dept_path = tmp_path / "department.csv"
    dept_path.write_text("id;name\n10;HR\n20;IT\n30;Finance\n")
    
    tag_path = tmp_path / "tag.csv"
    tag_path.write_text("id;name\nt1;Important\nt2;Urgent\nt3;Review\n")
    
    object_path = tmp_path / "digital_object.csv"
    object_path.write_text("digital_object_id;name\nobj1;Photo1\nobj2;Photo2\nobj3;Photo3\n")
    
    event_path = tmp_path / "event.csv"
    event_path.write_text("""id;name;person_id;department;tags;Digitales Objekt
e1;Meeting;1;10;t1,t2;obj1
e2;Conference;2;20;t2,t3;obj2
e3;Party;3;30;t1;obj3
""")
    
    # Run the full analysis
    report = analyze_csv_data([
        str(person_path), 
        str(dept_path), 
        str(tag_path), 
        str(object_path), 
        str(event_path)
    ], delimiter=';')
    
    # Check that intra-CSV reports were generated
    assert len(report.intra_csv_reports) == 5
    
    # Check that relationships were found
    assert len(report.relationships) >= 4
    
    # Check for all four expected relationships
    rel_types = [
        ("event.csv", "person_id", "person.csv", "id"),
        ("event.csv", "department", "department.csv", "id"),
        ("event.csv", "tags", "tag.csv", "id"),
        ("event.csv", "Digitales Objekt", "digital_object.csv", "digital_object_id")
    ]
    
    for source_file, source_col, target_file, target_col in rel_types:
        rel = next((r for r in report.relationships 
                   if r.source_file == source_file and 
                      r.source_column == source_col and
                      r.target_file == target_file and
                      r.target_column == target_col), None)
        assert rel is not None, f"Missing relationship: {source_file}.{source_col} -> {target_file}.{target_col}"

def test_multiple_tables_with_similar_columns(tmp_path):
    """Test handling of multiple tables with similar column names."""
    # Create tables with similar column names
    users_path = tmp_path / "users.csv"
    users_path.write_text("user_id;name\n1;User1\n2;User2\n3;User3\n")
    
    products_path = tmp_path / "products.csv"
    products_path.write_text("product_id;name\np1;Product1\np2;Product2\np3;Product3\n")
    
    # Create a table with columns referencing both
    orders_path = tmp_path / "orders.csv"
    orders_path.write_text("id;user_id;product_ids\n101;1;p1,p2\n102;2;p2,p3\n103;3;p1\n")
    
    # Find relationships
    relationships = find_relationships([
        str(users_path),
        str(products_path),
        str(orders_path)
    ], delimiter=';')
    
    # Check that both relationships were found
    assert len(relationships) >= 2
    
    # Check user_id -> users.user_id relationship
    user_rel = next((r for r in relationships 
                    if r.source_file == "orders.csv" and r.source_column == "user_id"), None)
    assert user_rel is not None
    assert user_rel.target_file == "users.csv"
    assert user_rel.target_column == "user_id"
    
    # Check product_ids -> products.product_id relationship
    product_rel = next((r for r in relationships 
                       if r.source_file == "orders.csv" and r.source_column == "product_ids"), None)
    assert product_rel is not None
    assert product_rel.target_file == "products.csv"
    assert product_rel.target_column == "product_id"

def test_uuid_primary_keys(tmp_path):
    """Test handling of UUID primary keys."""
    # Create a table with UUID primary key
    users_path = tmp_path / "users.csv"
    users_path.write_text("uuid;name\nabc-123;User1\ndef-456;User2\nghi-789;User3\n")
    
    # Create a table referencing the UUID
    posts_path = tmp_path / "posts.csv"
    posts_path.write_text("id;title;user_uuid\n1;Post1;abc-123\n2;Post2;def-456\n3;Post3;ghi-789\n")
    
    # Find relationships
    relationships = find_relationships([
        str(users_path),
        str(posts_path)
    ], delimiter=';')
    
    # Check that the relationship was found
    assert len(relationships) >= 1
    
    # Check user_uuid -> users.uuid relationship
    rel = next((r for r in relationships 
               if r.source_file == "posts.csv" and r.source_column == "user_uuid"), None)
    assert rel is not None
    assert rel.target_file == "users.csv"
    assert rel.target_column == "uuid"
