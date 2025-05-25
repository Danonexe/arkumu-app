#!/usr/bin/env python

import os
import tempfile
import shutil
import pytest
import json

from arkumu.importer.services.importer.relationship_analyzer import analyze_csv_relationships
from arkumu.importer.services.importer.linking_schema_generator import (
    LinkingSchemaGenerator, 
    generate_linking_schema_from_analysis,
    LinkType,
    MergeStrategy
)


def test_linking_schema_generator_basic():
    """Test basic functionality of the linking schema generator"""
    
    # Create temporary directory with test CSV files
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create departments.csv
        departments_data = """id;name;budget
DEPT001;Engineering;500000
DEPT002;Marketing;300000
DEPT003;Sales;400000"""
        
        with open(os.path.join(test_dir, "departments.csv"), 'w') as f:
            f.write(departments_data)
        
        # Create employees.csv (references departments)
        employees_data = """id;name;email;department_id;manager_id
EMP001;John Doe;john@company.com;DEPT001;
EMP002;Jane Smith;jane@company.com;DEPT001;EMP001
EMP003;Bob Johnson;bob@company.com;DEPT002;
EMP004;Alice Brown;alice@company.com;DEPT002;EMP003
EMP005;Grace Lee;grace@company.com;DEPT003;"""
        
        with open(os.path.join(test_dir, "employees.csv"), 'w') as f:
            f.write(employees_data)
        
        # Create projects.csv (references departments and employees)
        projects_data = """project_id;title;department_id;lead_id
PROJ001;Website Redesign;DEPT001;EMP001
PROJ002;Marketing Campaign;DEPT002;EMP003
PROJ003;Sales Dashboard;DEPT003;EMP005"""
        
        with open(os.path.join(test_dir, "projects.csv"), 'w') as f:
            f.write(projects_data)
        
        # Analyze relationships
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        
        # Debug: Print what relationships were found
        print(f"\n🔍 DEBUG: Found {len(analysis['relationships'])} relationships:")
        for i, rel in enumerate(analysis['relationships'][:5], 1):
            print(f"   {i}. {rel['type']}: {rel['file1']}.{rel['column1']} → {rel['file2']}.{rel['column2']}")
            print(f"      Confidence: {rel['confidence']:.3f}, Shared: {rel['shared_count']}")
        
        # Generate linking schema with lower thresholds for testing
        generator = LinkingSchemaGenerator(confidence_thresholds={
            "foreign_key": 0.5,  # Lower threshold for testing
            "duplicate": 0.8,
            "related": 0.3,
            "hierarchical": 0.5
        })
        schema = generator.generate_schema(analysis)
        
        # Verify schema structure
        assert schema.version == "1.0"
        assert schema.generated_at is not None
        assert schema.source_analysis is not None
        assert isinstance(schema.foreign_keys, list)
        assert isinstance(schema.duplicates, list)
        assert isinstance(schema.related_entities, list)
        assert isinstance(schema.hierarchical_links, list)
        assert isinstance(schema.statistics, dict)
        
        # Should find foreign key relationships
        assert len(schema.foreign_keys) > 0
        
        # Check that we found the expected foreign key relationships
        fk_descriptions = [fk.description for fk in schema.foreign_keys]
        
        # Should find department_id -> id relationships
        dept_fks = [fk for fk in schema.foreign_keys 
                   if 'department_id' in fk.source.column and 'id' in fk.target.column]
        assert len(dept_fks) >= 1
        
        # Verify foreign key structure
        for fk in schema.foreign_keys:
            assert fk.link_type == LinkType.FOREIGN_KEY
            assert fk.confidence > 0.5  # Should be reasonable confidence
            assert fk.shared_count > 0
            assert fk.source.file != fk.target.file  # Should link different files
        
        # Verify statistics
        stats = schema.statistics
        assert stats['total_links'] > 0
        assert stats['foreign_keys_count'] == len(schema.foreign_keys)
        assert stats['files_involved'] >= 2
        assert 'confidence_distribution' in stats
        
        print(f"✅ Generated schema with {stats['total_links']} links")
        print(f"   • Foreign keys: {stats['foreign_keys_count']}")
        print(f"   • Duplicates: {stats['duplicates_count']}")
        print(f"   • Related entities: {stats['related_entities_count']}")
        print(f"   • Hierarchical links: {stats['hierarchical_links_count']}")
        
    finally:
        shutil.rmtree(test_dir)


def test_linking_schema_with_duplicates():
    """Test linking schema generation with duplicate detection"""
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create two files with identical ID columns (duplicates)
        users_data = """user_id;name;email
USER001;John Doe;john@example.com
USER002;Jane Smith;jane@example.com
USER003;Bob Johnson;bob@example.com"""
        
        with open(os.path.join(test_dir, "users.csv"), 'w') as f:
            f.write(users_data)
        
        # Create accounts with same IDs (should be detected as duplicates)
        accounts_data = """user_id;account_type;balance
USER001;Premium;1000
USER002;Standard;500
USER003;Premium;750"""
        
        with open(os.path.join(test_dir, "accounts.csv"), 'w') as f:
            f.write(accounts_data)
        
        # Analyze and generate schema
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        schema = generate_linking_schema_from_analysis(analysis)
        
        # Should detect the user_id columns as potential duplicates or foreign keys
        total_relationships = len(schema.foreign_keys) + len(schema.duplicates)
        assert total_relationships > 0
        
        print(f"✅ Detected {total_relationships} relationships in duplicate scenario")
        
    finally:
        shutil.rmtree(test_dir)


def test_linking_schema_serialization():
    """Test that linking schema can be serialized to JSON"""
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create simple test data
        file1_data = """id;name
1;Item A
2;Item B"""
        
        file2_data = """ref_id;description
1;Description A
2;Description B"""
        
        with open(os.path.join(test_dir, "items.csv"), 'w') as f:
            f.write(file1_data)
        
        with open(os.path.join(test_dir, "descriptions.csv"), 'w') as f:
            f.write(file2_data)
        
        # Generate schema
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        
        # Test with output file
        output_file = os.path.join(test_dir, "test_schema.json")
        schema = generate_linking_schema_from_analysis(analysis, output_file)
        
        # Verify file was created
        assert os.path.exists(output_file)
        
        # Verify JSON is valid
        with open(output_file, 'r') as f:
            schema_dict = json.load(f)
        
        # Verify structure
        assert 'version' in schema_dict
        assert 'generated_at' in schema_dict
        assert 'foreign_keys' in schema_dict
        assert 'duplicates' in schema_dict
        assert 'statistics' in schema_dict
        
        # Verify foreign keys structure
        if schema_dict['foreign_keys']:
            fk = schema_dict['foreign_keys'][0]
            assert 'source' in fk
            assert 'target' in fk
            assert 'file' in fk['source']
            assert 'column' in fk['source']
            assert 'link_type' in fk
            assert 'confidence' in fk
        
        print(f"✅ Schema successfully serialized to {output_file}")
        
    finally:
        shutil.rmtree(test_dir)


def test_linking_schema_confidence_thresholds():
    """Test that confidence thresholds work correctly"""
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create test data
        file1_data = """id;name
1;Test A
2;Test B"""
        
        file2_data = """ref_id;value
1;Value A
2;Value B"""
        
        with open(os.path.join(test_dir, "test1.csv"), 'w') as f:
            f.write(file1_data)
        
        with open(os.path.join(test_dir, "test2.csv"), 'w') as f:
            f.write(file2_data)
        
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        
        # Test with high thresholds (should find fewer relationships)
        high_thresholds = {
            "foreign_key": 0.95,
            "duplicate": 0.98,
            "related": 0.8,
            "hierarchical": 0.9
        }
        
        schema_high = generate_linking_schema_from_analysis(analysis, confidence_thresholds=high_thresholds)
        
        # Test with low thresholds (should find more relationships)
        low_thresholds = {
            "foreign_key": 0.5,
            "duplicate": 0.7,
            "related": 0.3,
            "hierarchical": 0.5
        }
        
        schema_low = generate_linking_schema_from_analysis(analysis, confidence_thresholds=low_thresholds)
        
        # Low thresholds should find same or more relationships
        total_high = (len(schema_high.foreign_keys) + len(schema_high.duplicates) + 
                     len(schema_high.related_entities) + len(schema_high.hierarchical_links))
        total_low = (len(schema_low.foreign_keys) + len(schema_low.duplicates) + 
                    len(schema_low.related_entities) + len(schema_low.hierarchical_links))
        
        assert total_low >= total_high
        
        print(f"✅ High thresholds: {total_high} links, Low thresholds: {total_low} links")
        
    finally:
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    test_linking_schema_generator_basic()
    test_linking_schema_with_duplicates()
    test_linking_schema_serialization()
    test_linking_schema_confidence_thresholds()
    print("All tests passed!") 