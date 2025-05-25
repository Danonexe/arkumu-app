#!/usr/bin/env python

import os
import json
import logging
import pytest

from arkumu.importer.services.importer.relationship_analyzer import analyze_csv_relationships

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.DEBUG)
    yield


def test_analyze_csv_relationships_with_real_data():
    """
    Test relationship analysis using real CSV files.
    
    This test can be run in two ways:
    
    1. Using environment variables:
       CSV_DIR=/path/to/csv/dir pytest arkumu/importer/tests/services/analyzer_real_data/test_analyzer_with_real_data.py::test_analyze_csv_relationships_with_real_data -v
    
    2. Using command line arguments:
       pytest arkumu/importer/tests/services/analyzer_real_data/test_analyzer_with_real_data.py::test_analyze_csv_relationships_with_real_data -v --csv-dir=/path/to/csv/dir
    
    Example with KHM data using Docker volume mounting:
       docker compose -f docker-compose.local.yml run --rm \
           -v ../arkumu-metadata:/external_data \
           -e CSV_DIR=/external_data/khm/khm-projektarchiv \
           django pytest arkumu/importer/tests/services/analyzer_real_data/test_analyzer_with_real_data.py::test_analyze_csv_relationships_with_real_data -v -s
    
    Alternative with custom delimiter:
       docker compose -f docker-compose.local.yml run --rm \
           -v ../arkumu-metadata:/external_data \
           -e CSV_DIR=/external_data/khm/khm-projektarchiv \
           -e CSV_DELIMITER=';' \
           django pytest arkumu/importer/tests/services/analyzer_real_data/test_analyzer_with_real_data.py::test_analyze_csv_relationships_with_real_data -v -s
    """
    # First check environment variables
    csv_dir = os.environ.get('CSV_DIR')
    delimiter = os.environ.get('CSV_DELIMITER', ';')
    
    # If not found, check command line arguments
    if not csv_dir:
        import sys
        
        for i, arg in enumerate(sys.argv):
            if arg.startswith('--csv-dir='):
                csv_dir = arg.split('=', 1)[1]
            elif arg == '--csv-dir' and i+1 < len(sys.argv):
                csv_dir = sys.argv[i+1]
            elif arg.startswith('--delimiter='):
                delimiter = arg.split('=', 1)[1]
            elif arg == '--delimiter' and i+1 < len(sys.argv):
                delimiter = sys.argv[i+1]
    
    if not csv_dir:
        pytest.skip("CSV directory not provided. Use CSV_DIR environment variable or --csv-dir option.")
    
    # Check if CSV directory exists
    if not os.path.isdir(csv_dir):
        pytest.skip(f"CSV directory not found: {csv_dir}")
    
    # List CSV files in directory
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
    if not csv_files:
        pytest.skip(f"No CSV files found in directory: {csv_dir}")
    
    print(f"\n🔍 RELATIONSHIP ANALYSIS")
    print(f"📁 Directory: {csv_dir}")
    print(f"📄 Found {len(csv_files)} CSV files:")
    for csv_file in sorted(csv_files):
        print(f"   • {csv_file}")
    print(f"🔧 Delimiter: '{delimiter}'")
    
    # Run the relationship analysis
    print(f"\n🚀 Starting relationship analysis...")
    
    try:
        analysis = analyze_csv_relationships(
            csv_directory=csv_dir,
            delimiter=delimiter,
            print_report=True
        )
        
        # Extract key statistics
        summary = analysis['summary']
        relationships = analysis['relationships']
        intersections = analysis['intersections']
        
        print(f"\n📊 ANALYSIS RESULTS:")
        print(f"   • Files analyzed: {summary['files_analyzed']}")
        print(f"   • Relationships found: {summary['total_relationships']}")
        print(f"   • High-confidence relationships: {summary['high_confidence_relationships']}")
        
        # Show relationship type breakdown
        if summary['relationship_types']:
            print(f"\n🔗 RELATIONSHIP TYPES:")
            for rel_type, count in summary['relationship_types'].items():
                print(f"   • {rel_type.replace('_', '-')}: {count}")
        
        # Show potential foreign key relationships (most important)
        foreign_key_rels = [rel for rel in relationships if rel['type'] == 'many_to_one' and rel['confidence'] > 0.8]
        if foreign_key_rels:
            print(f"\n🔑 KEY FOREIGN KEY RELATIONSHIPS ({len(foreign_key_rels)} found):")
            for i, rel in enumerate(foreign_key_rels[:5], 1):
                print(f"   {i}. {rel['file1']}.{rel['column1']} → {rel['file2']}.{rel['column2']}")
                print(f"      Confidence: {rel['confidence']:.2f}, Shared: {rel['shared_count']} values")
        
        # Show potential duplicates
        duplicate_rels = [rel for rel in relationships if rel['type'] == 'one_to_one']
        if duplicate_rels:
            print(f"\n🔄 POTENTIAL DUPLICATES ({len(duplicate_rels)} found):")
            for i, rel in enumerate(duplicate_rels[:3], 1):
                print(f"   {i}. {rel['file1']}.{rel['column1']} ↔ {rel['file2']}.{rel['column2']}")
        
        # Show sample of other relationships
        other_rels = [rel for rel in relationships if rel['type'] not in ['many_to_one', 'one_to_one']]
        if other_rels:
            print(f"\n📊 OTHER RELATIONSHIPS (showing {min(3, len(other_rels))} of {len(other_rels)}):")
            for i, rel in enumerate(other_rels[:3], 1):
                print(f"   {i}. {rel['type']}: {rel['file1']}.{rel['column1']} ↔ {rel['file2']}.{rel['column2']}")
        
        # Basic assertions
        assert analysis is not None, "Analysis should not be None"
        assert 'summary' in analysis, "Analysis should contain summary"
        assert 'relationships' in analysis, "Analysis should contain relationships"
        assert 'intersections' in analysis, "Analysis should contain intersections"
        assert summary['files_analyzed'] > 0, "Should analyze at least one file"
        assert summary['total_columns'] > 0, "Should find at least one column"
        
        print(f"\n✅ SUCCESS: Relationship analysis completed!")
        print(f"📈 Found {summary['total_relationships']} relationships across {summary['files_analyzed']} files")
        
        # Store analysis for assertions
        assert analysis is not None
        
    except Exception as e:
        print(f"\n❌ ERROR during analysis: {e}")
        raise


def test_analyze_csv_relationships_with_sample_data():
    """
    Test relationship analysis with built-in sample data.
    This test always runs and doesn't require external files.
    """
    import tempfile
    import shutil
    
    # Create temporary directory with sample CSV files
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create sample data similar to KHM structure
        projects_data = """Projekt_ID;Originaltitel;Kategorie;Unterkategorie;Jahr
200;Die Einzige;Installation;Installation;2020
302;NDSL;Installation;Installation;2021
528;Hähnchen Ewald;Film / TV / Video;Dokumentarfilm;2019
601;Digital Archive;Software;Web Application;2022"""
        
        with open(os.path.join(test_dir, "00_Projekte.csv"), 'w') as f:
            f.write(projects_data)
        
        # Create relationship table (projects to people)
        proj_persons_data = """AS_ID;AS_Pers_ID;AS_Proj_ID;AS_Taetigkeit;Jahr
119;417;200;AutorIn;2020
127;135;302;AutorIn;2021
570;61;528;AutorIn;2019
580;417;601;AutorIn;2022
590;135;601;KuratorIn;2022"""
        
        with open(os.path.join(test_dir, "02_Kreuz_Projekte_Personen.csv"), 'w') as f:
            f.write(proj_persons_data)
        
        # Create persons table
        persons_data = """PE_ID;Vorname;Nachname;Email;Institution
417;Anna;Wiese;anna@example.com;KHM
135;Max;Mueller;max@example.com;KHM
61;Lisa;Schmidt;lisa@example.com;External
200;John;Doe;john@example.com;KHM"""
        
        with open(os.path.join(test_dir, "03_Personen_Akteurinnen.csv"), 'w') as f:
            f.write(persons_data)
        
        print(f"\n🧪 TESTING WITH SAMPLE DATA")
        print(f"📁 Temporary directory: {test_dir}")
        
        # Analyze relationships
        analysis = analyze_csv_relationships(test_dir, delimiter=';', print_report=True)
        
        # Verify we found the expected relationships
        relationships = analysis['relationships']
        summary = analysis['summary']
        
        # Should find AS_Proj_ID -> Projekt_ID relationship
        proj_id_relationships = [
            rel for rel in relationships 
            if (('AS_Proj_ID' in rel['column1'] and 'Projekt_ID' in rel['column2']) or
                ('AS_Proj_ID' in rel['column2'] and 'Projekt_ID' in rel['column1']))
            and rel['type'] == 'many_to_one'
        ]
        
        # Should find AS_Pers_ID -> PE_ID relationship  
        pers_id_relationships = [
            rel for rel in relationships 
            if (('AS_Pers_ID' in rel['column1'] and 'PE_ID' in rel['column2']) or
                ('AS_Pers_ID' in rel['column2'] and 'PE_ID' in rel['column1']))
            and rel['type'] == 'many_to_one'
        ]
        
        print(f"\n🔍 VERIFICATION:")
        print(f"   • Project ID relationships found: {len(proj_id_relationships)}")
        print(f"   • Person ID relationships found: {len(pers_id_relationships)}")
        
        # Basic assertions
        assert summary['files_analyzed'] == 3
        assert summary['total_relationships'] > 0
        assert len(proj_id_relationships) >= 1, "Should find project ID relationship"
        assert len(pers_id_relationships) >= 1, "Should find person ID relationship"
        
        print(f"\n✅ SUCCESS: Sample data analysis completed!")
        
    finally:
        shutil.rmtree(test_dir)


def test_generate_linking_schema_from_real_data():
    """
    Test generating a linking schema from real CSV relationship analysis.
    
    This test can be run using Docker volume mounting:
       docker compose -f docker-compose.local.yml run --rm \
           -v ../arkumu-metadata:/external_data \
           -e CSV_DIR=/external_data/khm/khm-projektarchiv \
           django pytest arkumu/importer/tests/services/analyzer_real_data/test_analyzer_with_real_data.py::test_generate_linking_schema_from_real_data -v -s
    """
    from arkumu.importer.services.importer.linking_schema_generator import generate_linking_schema_from_analysis
    
    # Get CSV directory from environment
    csv_dir = os.environ.get('CSV_DIR')
    delimiter = os.environ.get('CSV_DELIMITER', ';')
    
    if not csv_dir:
        pytest.skip("CSV directory not provided. Use CSV_DIR environment variable.")
    
    if not os.path.isdir(csv_dir):
        pytest.skip(f"CSV directory not found: {csv_dir}")
    
    # List CSV files in directory
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
    if not csv_files:
        pytest.skip(f"No CSV files found in directory: {csv_dir}")
    
    print(f"\n🔗 LINKING SCHEMA GENERATION")
    print(f"📁 Directory: {csv_dir}")
    print(f"📄 Found {len(csv_files)} CSV files")
    print(f"🔧 Delimiter: '{delimiter}'")
    
    try:
        # First, run relationship analysis
        print(f"\n🔍 Step 1: Running relationship analysis...")
        analysis = analyze_csv_relationships(
            csv_directory=csv_dir,
            delimiter=delimiter,
            print_report=False  # Don't print the full report here
        )
        
        # Generate linking schema
        print(f"\n🔗 Step 2: Generating linking schema...")
        schema = generate_linking_schema_from_analysis(
            analysis_results=analysis,
            confidence_thresholds={
                "foreign_key": 0.8,
                "duplicate": 0.9,
                "related": 0.5,
                "hierarchical": 0.7
            }
        )
        
        # Print schema summary
        stats = schema.statistics
        print(f"\n📊 LINKING SCHEMA GENERATED:")
        print(f"   • Total links: {stats['total_links']}")
        print(f"   • Foreign keys: {stats['foreign_keys_count']}")
        print(f"   • Duplicates: {stats['duplicates_count']}")
        print(f"   • Related entities: {stats['related_entities_count']}")
        print(f"   • Hierarchical links: {stats['hierarchical_links_count']}")
        print(f"   • Average confidence: {stats['average_confidence']}")
        print(f"   • High confidence links: {stats['high_confidence_links']}")
        print(f"   • Files involved: {stats['files_involved']}")
        
        # Show confidence distribution
        conf_dist = stats['confidence_distribution']
        print(f"\n📈 CONFIDENCE DISTRIBUTION:")
        print(f"   • Very high (>0.9): {conf_dist['very_high']}")
        print(f"   • High (0.8-0.9): {conf_dist['high']}")
        print(f"   • Medium (0.6-0.8): {conf_dist['medium']}")
        print(f"   • Low (≤0.6): {conf_dist['low']}")
        
        # Show top foreign key relationships
        if schema.foreign_keys:
            print(f"\n🔑 TOP FOREIGN KEY RELATIONSHIPS ({min(5, len(schema.foreign_keys))} of {len(schema.foreign_keys)}):")
            for i, fk in enumerate(schema.foreign_keys[:5], 1):
                print(f"   {i}. {fk.source.file}.{fk.source.column} → {fk.target.file}.{fk.target.column}")
                print(f"      Confidence: {fk.confidence:.3f}, Shared: {fk.shared_count} values")
        
        # Show duplicate groups
        if schema.duplicates:
            print(f"\n🔄 DUPLICATE GROUPS ({len(schema.duplicates)} found):")
            for i, dup in enumerate(schema.duplicates[:3], 1):
                columns_str = ", ".join([f"{col.file}.{col.column}" for col in dup.columns])
                print(f"   {i}. {columns_str}")
                print(f"      Strategy: {dup.merge_strategy.value}, Confidence: {dup.confidence:.3f}")
        
        # Show related entities
        if schema.related_entities:
            print(f"\n📊 RELATED ENTITIES ({min(3, len(schema.related_entities))} of {len(schema.related_entities)}):")
            for i, rel in enumerate(schema.related_entities[:3], 1):
                print(f"   {i}. {rel.source.file}.{rel.source.column} ↔ {rel.target.file}.{rel.target.column}")
                print(f"      Confidence: {rel.confidence:.3f}")
        
        # Basic assertions
        assert schema is not None
        assert stats['total_links'] >= 0
        assert stats['files_involved'] > 0
        assert len(schema.foreign_keys) >= 0
        
        print(f"\n✅ SUCCESS: Linking schema generated!")
        print(f"📋 Schema contains {stats['total_links']} total linking rules")
        
        # Optionally save schema to file for inspection
        output_file = os.path.join(csv_dir, "generated_linking_schema.json")
        schema.save_to_file(output_file)
        print(f"💾 Schema saved to: {output_file}")
        
        return schema
        
    except Exception as e:
        print(f"\n❌ ERROR during schema generation: {e}")
        raise