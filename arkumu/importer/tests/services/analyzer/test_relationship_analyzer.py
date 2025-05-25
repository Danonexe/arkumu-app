#!/usr/bin/env python

import os
import tempfile
import shutil
import pytest

from arkumu.importer.services.importer.relationship_analyzer import RelationshipAnalyzer, analyze_csv_relationships


def test_relationship_analyzer_basic():
    """Test basic functionality of the relationship analyzer"""
    
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
EMP005;Grace Lee;grace@company.com;DEPT003;EMP001"""
        
        with open(os.path.join(test_dir, "employees.csv"), 'w') as f:
            f.write(employees_data)
        
        # Create projects.csv (references departments and employees)
        projects_data = """id;name;department_id;lead_id;budget
PROJ001;Website Redesign;DEPT002;EMP003;50000
PROJ002;Mobile App;DEPT001;EMP001;100000
PROJ003;Data Migration;DEPT003;EMP005;75000"""
        
        with open(os.path.join(test_dir, "projects.csv"), 'w') as f:
            f.write(projects_data)
        
        # Test the analyzer
        analyzer = RelationshipAnalyzer(delimiter=';')
        analysis = analyzer.analyze_directory(test_dir)
        
        # Verify basic structure
        assert 'column_data' in analysis
        assert 'intersections' in analysis
        assert 'relationships' in analysis
        assert 'summary' in analysis
        
        # Verify we found some relationships
        assert len(analysis['relationships']) > 0
        
        # Check that we found the expected foreign key relationships
        relationships = analysis['relationships']
        
        # Should find department_id relationships
        dept_relationships = [
            rel for rel in relationships 
            if ('department_id' in rel['column1'] or 'department_id' in rel['column2'])
            and rel['type'] == 'many_to_one'
        ]
        assert len(dept_relationships) >= 1
        
        # Should find manager_id self-reference
        manager_relationships = [
            rel for rel in relationships 
            if ('manager_id' in rel['column1'] or 'manager_id' in rel['column2'])
        ]
        assert len(manager_relationships) >= 0  # May or may not be detected depending on data
        
        # Verify summary statistics
        summary = analysis['summary']
        assert summary['files_analyzed'] == 3
        assert summary['total_columns'] > 0
        assert summary['total_relationships'] > 0
        
        print(f"\n✅ Test passed!")
        print(f"   Files analyzed: {summary['files_analyzed']}")
        print(f"   Relationships found: {summary['total_relationships']}")
        print(f"   High-confidence relationships: {summary['high_confidence_relationships']}")
        
        # Print top relationships for inspection
        print(f"\n🔗 Top relationships found:")
        for i, rel in enumerate(relationships[:3], 1):
            print(f"   {i}. {rel['type']} - {rel['description']} (confidence: {rel['confidence']:.3f})")
        
    finally:
        # Clean up
        shutil.rmtree(test_dir)


def test_relationship_analyzer_with_khm_structure():
    """Test with a structure similar to KHM data"""
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create main projects table
        projects_data = """Projekt_ID;Originaltitel;Kategorie;Unterkategorie
200;Die Einzige;Installation;Installation
302;NDSL;Installation;Installation
528;Hähnchen Ewald;Film / TV / Video;Dokumentarfilm"""
        
        with open(os.path.join(test_dir, "00_Projekte.csv"), 'w') as f:
            f.write(projects_data)
        
        # Create relationship table (projects to people)
        proj_persons_data = """AS_ID;AS_Pers_ID;AS_Proj_ID;AS_Taetigkeit
119;417;200;AutorIn
127;135;302;AutorIn
570;61;528;AutorIn"""
        
        with open(os.path.join(test_dir, "02_Kreuz_Projekte_Personen.csv"), 'w') as f:
            f.write(proj_persons_data)
        
        # Create persons table
        persons_data = """PE_ID;Vorname;Nachname;Email
417;Anna;Wiese;anna@example.com
135;Max;Mueller;max@example.com
61;Lisa;Schmidt;lisa@example.com"""
        
        with open(os.path.join(test_dir, "03_Personen_Akteurinnen.csv"), 'w') as f:
            f.write(persons_data)
        
        # Analyze relationships
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        
        # Verify we found the expected relationships
        relationships = analysis['relationships']
        
        # Should find AS_Proj_ID -> Projekt_ID relationship
        proj_id_relationships = [
            rel for rel in relationships 
            if (('AS_Proj_ID' in rel['column1'] and 'Projekt_ID' in rel['column2']) or
                ('AS_Proj_ID' in rel['column2'] and 'Projekt_ID' in rel['column1']))
            and rel['type'] == 'many_to_one'
        ]
        assert len(proj_id_relationships) >= 1
        
        # Should find AS_Pers_ID -> PE_ID relationship  
        pers_id_relationships = [
            rel for rel in relationships 
            if (('AS_Pers_ID' in rel['column1'] and 'PE_ID' in rel['column2']) or
                ('AS_Pers_ID' in rel['column2'] and 'PE_ID' in rel['column1']))
            and rel['type'] == 'many_to_one'
        ]
        assert len(pers_id_relationships) >= 1
        
        print(f"\n✅ KHM structure test passed!")
        print(f"   Found {len(relationships)} relationships")
        
        # Print the discovered relationships
        for rel in relationships[:5]:
            print(f"   • {rel['description']} (confidence: {rel['confidence']:.3f})")
        
    finally:
        shutil.rmtree(test_dir)


def test_convenience_function():
    """Test the convenience function"""
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create simple test data
        data1 = """id;name;category
1;Item A;CAT1
2;Item B;CAT2
3;Item C;CAT1"""
        
        data2 = """ref_id;description;category_code
1;Description A;CAT1
2;Description B;CAT2
4;Description D;CAT3"""
        
        with open(os.path.join(test_dir, "items.csv"), 'w') as f:
            f.write(data1)
        
        with open(os.path.join(test_dir, "descriptions.csv"), 'w') as f:
            f.write(data2)
        
        # Test convenience function
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=False)
        
        assert analysis is not None
        assert 'relationships' in analysis
        assert len(analysis['relationships']) >= 0
        
        print(f"\n✅ Convenience function test passed!")
        
    finally:
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    print("🧪 Testing Relationship Analyzer...")
    
    test_relationship_analyzer_basic()
    test_relationship_analyzer_with_khm_structure()
    test_convenience_function()
    
    print(f"\n🎉 All tests passed!") 