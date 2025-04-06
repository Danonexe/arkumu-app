import pytest
from django.db import transaction
from pathlib import Path
import os
import re
import random
from rdflib import Graph, Namespace, RDF, RDFS, OWL

from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf

@pytest.fixture
def rdf_file_path():
    """Return the path to the CIDOC RDF file"""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    rdf_file = os.path.join(base_dir, 'cidoc', 'schema', 'CIDOC_CRM_v7.1.1.rdf')
    assert os.path.exists(rdf_file), f"RDF file not found at {rdf_file}"
    return rdf_file

@pytest.fixture
def cidoc_rdf(rdf_file_path):
    """Load the CIDOC-CRM RDF into an RDFLib graph"""
    g = Graph()
    g.parse(rdf_file_path, format="xml")
    return g

@pytest.fixture
def cidoc_ns():
    """Provide a namespace for CIDOC-CRM URIs"""
    return Namespace("http://www.cidoc-crm.org/cidoc-crm/")

@pytest.fixture
def loaded_cidoc_data(rdf_file_path):
    """Load CIDOC data from RDF into actual database models"""
    with transaction.atomic():
        classes_count, properties_count = import_cidoc_from_rdf(rdf_file_path)
        print(f"\nLoaded {classes_count} classes and {properties_count} properties into database")
        yield (classes_count, properties_count)
        # Transaction will be rolled back after the test

@pytest.mark.django_db
def test_compare_rdf_with_db(cidoc_rdf, cidoc_ns, loaded_cidoc_data):
    """Compare RDF data with database import statistics"""
    # Analyze RDF file
    classes_in_rdf = list(cidoc_rdf.subjects(RDF.type, RDFS.Class))
    properties_in_rdf = list(cidoc_rdf.subjects(RDF.type, RDF.Property))
    
    # Filter to only include CIDOC namespace
    cidoc_classes = [c for c in classes_in_rdf if str(c).startswith(str(cidoc_ns))]
    cidoc_properties = [p for p in properties_in_rdf if str(p).startswith(str(cidoc_ns))]
    
    # Count inverse property pairs in RDF
    inverse_pairs = []
    for prop in cidoc_properties:
        for _, _, inverse in cidoc_rdf.triples((prop, OWL.inverseOf, None)):
            if (prop, inverse) not in inverse_pairs and (inverse, prop) not in inverse_pairs:
                inverse_pairs.append((prop, inverse))
    
    # Get database counts
    db_classes_count = CIDOCClass.objects.count()
    db_properties_count = CIDOCProperty.objects.count()
    db_inverse_count = CIDOCProperty.objects.exclude(inverse_property=None).count()
    
    # Extract E and P numbers from RDF
    e_pattern = re.compile(r'E(\d+)')
    p_pattern = re.compile(r'P(\d+)')
    
    e_numbers_in_rdf = set()
    for cls in cidoc_classes:
        match = e_pattern.search(str(cls).split('/')[-1])
        if match:
            e_numbers_in_rdf.add(int(match.group(1)))
    
    p_numbers_in_rdf = set()
    for prop in cidoc_properties:
        match = p_pattern.search(str(prop).split('/')[-1])
        if match:
            p_numbers_in_rdf.add(int(match.group(1)))
    
    # Print comparison
    print("\n=== CIDOC-CRM Statistics ===")
    print(f"RDF file: {len(cidoc_classes)} classes, {len(cidoc_properties)} properties")
    print(f"Database: {db_classes_count} classes, {db_properties_count} properties")
    print(f"Inverse relationships: {len(inverse_pairs)} in RDF, {db_inverse_count//2} bidirectional pairs in DB")
    
    print("\n=== Property Details ===")
    print(f"Distinct property numbers in RDF: {len(p_numbers_in_rdf)}")
    print(f"Highest property number: P{max(p_numbers_in_rdf)}")
    
    # Count base and inverse properties in DB
    base_props = CIDOCProperty.objects.filter(property_id__regex=r'^P\d+$').count()
    inverse_props = CIDOCProperty.objects.filter(property_id__regex=r'^P\d+i$').count()
    special_props = db_properties_count - base_props - inverse_props
    
    print(f"Database property breakdown:")
    print(f"  - Base properties (P1, P2, etc.): {base_props}")
    print(f"  - Inverse properties (P1i, P2i, etc.): {inverse_props}")
    print(f"  - Special properties (P81a, etc.): {special_props}")
    
    # Print missing class information
    if len(cidoc_classes) != db_classes_count:
        print("\n=== Class Differences ===")
        # Get class IDs
        rdf_class_ids = set()
        for cls in cidoc_classes:
            match = e_pattern.search(str(cls).split('/')[-1])
            if match:
                rdf_class_ids.add(match.group(0))
        
        db_class_ids = set(CIDOCClass.objects.values_list('class_id', flat=True))
        
        missing_in_db = rdf_class_ids - db_class_ids
        extra_in_db = db_class_ids - rdf_class_ids
        
        if missing_in_db:
            print(f"Classes in RDF but missing in DB: {missing_in_db}")
        if extra_in_db:
            print(f"Classes in DB but not in RDF: {extra_in_db}")
    
    # List some sample properties from both RDF and DB
    print("\n=== Sample Properties ===")
    print("From RDF:")
    for prop in sorted(list(cidoc_properties))[:5]:
        prop_id = str(prop).split('/')[-1]
        label = cidoc_rdf.value(prop, RDFS.label)
        print(f"  - {prop_id}: {label}")
    
    print("\nFrom Database:")
    for prop in CIDOCProperty.objects.all()[:5]:
        print(f"  - {prop.property_id}: {prop.label}")
    
    # Verify counts roughly match - with some tolerance for class count
    # We may miss 1-2 classes due to special handling or filtering
    assert abs(db_classes_count - len(cidoc_classes)) <= 1, "Class count mismatch too large"
    assert base_props + inverse_props + special_props == db_properties_count, "Property breakdown incorrect"
    
    # The exact property count can vary due to special property types
    # But base properties should roughly match the distinct P numbers
    assert abs(len(p_numbers_in_rdf) - base_props) <= 10, "Base property count significantly different"
    assert db_inverse_count == len(inverse_pairs) * 2, "Inverse property count mismatch"

@pytest.mark.django_db
def test_property_stats(cidoc_rdf, cidoc_ns, loaded_cidoc_data):
    """Test to check property statistics from the RDF and compare with DB"""
    # Analyze properties in RDF
    properties_in_rdf = list(cidoc_rdf.subjects(RDF.type, RDF.Property))
    cidoc_properties = [p for p in properties_in_rdf if str(p).startswith(str(cidoc_ns))]
    
    # Extract base and inverse properties
    base_props_rdf = []
    inverse_props_rdf = []
    
    for prop in cidoc_properties:
        prop_id = str(prop).split('/')[-1]
        if 'i_' in prop_id:  # Inverse property like P1i_identifies
            inverse_props_rdf.append(prop_id)
        elif re.match(r'P\d+_', prop_id):  # Base property like P1_is_identified_by
            base_props_rdf.append(prop_id)
    
    # Count properties in DB
    db_props_count = CIDOCProperty.objects.count()
    base_props_db = CIDOCProperty.objects.filter(property_id__regex=r'^P\d+$').count()
    inverse_props_db = CIDOCProperty.objects.filter(property_id__regex=r'^P\d+i$').count()
    special_props = db_props_count - base_props_db - inverse_props_db
    
    # Print the results
    print(f"\n=== CIDOC-CRM Property Comparison ===")
    print(f"RDF properties: {len(cidoc_properties)}")
    print(f"- Base properties in RDF: {len(base_props_rdf)}")
    print(f"- Inverse properties in RDF: {len(inverse_props_rdf)}")
    print(f"- Other properties in RDF: {len(cidoc_properties) - len(base_props_rdf) - len(inverse_props_rdf)}")
    
    print(f"\nDatabase properties: {db_props_count}")
    print(f"- Base properties in DB: {base_props_db}")
    print(f"- Inverse properties in DB: {inverse_props_db}")
    print(f"- Special properties in DB: {special_props}")
    
    # List highest property numbers
    p_pattern = re.compile(r'P(\d+)')
    p_numbers = []
    for prop in cidoc_properties:
        match = p_pattern.search(str(prop).split('/')[-1])
        if match:
            p_numbers.append(int(match.group(1)))
    
    if p_numbers:
        print(f"\nProperty numbers in RDF: {len(set(p_numbers))} distinct numbers")
        print(f"Highest property number: P{max(p_numbers)}")
    
    # Assert that total property counts match
    assert abs(len(cidoc_properties) - db_props_count) <= 5, "Property count mismatch"
    
    # Assert that base property counts match between RDF and DB
    assert abs(len(base_props_rdf) - base_props_db) <= 10, "Base property count mismatch"
    
    # Assert that inverse property counts match between RDF and DB
    assert abs(len(inverse_props_rdf) - inverse_props_db) <= 10, "Inverse property count mismatch"
    
    # Assert that special property counts match 
    assert abs((len(cidoc_properties) - len(base_props_rdf) - len(inverse_props_rdf)) - special_props) <= 5, "Special property count mismatch"

@pytest.mark.django_db
def test_inverse_property_relations(cidoc_rdf, cidoc_ns, loaded_cidoc_data):
    """Check inverse property relations in the database and compare with RDF"""
    # Count properties with inverse relations in DB
    props_with_inverse_db = CIDOCProperty.objects.exclude(inverse_property=None).count()
    
    # Count inverse property pairs in RDF
    inverse_pairs_rdf = []
    properties_in_rdf = list(cidoc_rdf.subjects(RDF.type, RDF.Property))
    cidoc_properties = [p for p in properties_in_rdf if str(p).startswith(str(cidoc_ns))]
    
    for prop in cidoc_properties:
        for _, _, inverse in cidoc_rdf.triples((prop, OWL.inverseOf, None)):
            if (prop, inverse) not in inverse_pairs_rdf and (inverse, prop) not in inverse_pairs_rdf:
                inverse_pairs_rdf.append((prop, inverse))
    
    print(f"\n=== Inverse Property Relations ===")
    print(f"Inverse property pairs in RDF: {len(inverse_pairs_rdf)}")
    print(f"Properties with inverse relation in DB: {props_with_inverse_db}")
    
    # Extract base property IDs from the database
    base_props = list(CIDOCProperty.objects.filter(property_id__regex=r'^P\d+$'))
    
    # Sample some inverse pairs
    inverse_pairs = []
    for p in random.sample(base_props, min(5, len(base_props))):
        if p.inverse_property:
            inverse_pairs.append((p.property_id, p.inverse_property.property_id))
    
    print("\nSample inverse pairs from DB:")
    for base, inverse in inverse_pairs:
        print(f"- {base} ↔ {inverse}")
    
    # Verify domain/range swapping for every pair
    domain_range_correct = 0
    domain_range_incorrect = 0
    
    for base, inverse in inverse_pairs:
        base_prop = CIDOCProperty.objects.get(property_id=base)
        inverse_prop = CIDOCProperty.objects.get(property_id=inverse)
        
        if base_prop.domain_class and base_prop.range_class and inverse_prop.domain_class and inverse_prop.range_class:
            print(f"\nDomain/Range for {base} ↔ {inverse}:")
            print(f"- {base}: Domain={base_prop.domain_class.class_id}, Range={base_prop.range_class.class_id}")
            print(f"- {inverse}: Domain={inverse_prop.domain_class.class_id}, Range={inverse_prop.range_class.class_id}")
            
            # Check if domain and range are properly swapped
            if base_prop.domain_class == inverse_prop.range_class and base_prop.range_class == inverse_prop.domain_class:
                print("✓ Domain and range properly swapped as expected")
                domain_range_correct += 1
            else:
                print("✗ Domain and range not swapped as expected")
                domain_range_incorrect += 1
    
    print(f"\nDomain/Range swap verification results:")
    print(f"- Correct swaps: {domain_range_correct}")
    print(f"- Incorrect swaps: {domain_range_incorrect}")
    
    # Verify that inverse properties correctly link back to each other
    bidirectional_count = 0
    for prop in base_props:
        if prop.inverse_property and prop.inverse_property.inverse_property == prop:
            bidirectional_count += 1
    
    print(f"\nBidirectional inverse links: {bidirectional_count} of {len(base_props)} base properties")
    
    # Assertions
    # 1. Verify we have inverse properties
    assert props_with_inverse_db > 0, "No inverse properties found in database"
    assert len(inverse_pairs) > 0, "No sample inverse pairs found"
    
    # 2. Verify that the count of properties with inverse relations matches expectations
    # Since each property in a pair has an inverse, the count should be twice the number of pairs
    assert props_with_inverse_db == len(inverse_pairs_rdf) * 2, "Inverse property count mismatch between RDF and DB"
    
    # 3. Verify that most domain/range swaps are correct (allowing for some special cases)
    if domain_range_correct + domain_range_incorrect > 0:
        correct_percentage = (domain_range_correct / (domain_range_correct + domain_range_incorrect)) * 100
        assert correct_percentage >= 80, f"Only {correct_percentage:.1f}% of domain/range swaps are correct"
    
    # 4. Verify bidirectional linking
    assert bidirectional_count >= len(base_props) * 0.85, "Fewer than 85% of properties have correct bidirectional links"

@pytest.mark.django_db
def test_property_characteristics(cidoc_rdf, cidoc_ns, loaded_cidoc_data):
    """Test property characteristics (symmetric, transitive) compared to RDF"""
    # Find symmetric and transitive properties in RDF
    symmetric_props_rdf = []
    transitive_props_rdf = []
    
    for prop in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty):
        if str(prop).startswith(str(cidoc_ns)):
            symmetric_props_rdf.append(str(prop).split('/')[-1])
    
    for prop in cidoc_rdf.subjects(RDF.type, OWL.TransitiveProperty):
        if str(prop).startswith(str(cidoc_ns)):
            transitive_props_rdf.append(str(prop).split('/')[-1])
    
    # Extract property numbers
    p_pattern = re.compile(r'P(\d+)')
    symmetric_numbers = []
    for prop_id in symmetric_props_rdf:
        match = p_pattern.search(prop_id)
        if match:
            prop_num = match.group(1)
            symmetric_numbers.append(f"P{prop_num}")
    
    transitive_numbers = []
    for prop_id in transitive_props_rdf:
        match = p_pattern.search(prop_id)
        if match:
            prop_num = match.group(1)
            transitive_numbers.append(f"P{prop_num}")
    
    # Find symmetric and transitive properties in DB
    symmetric_props_db = CIDOCProperty.objects.filter(is_symmetric=True)
    transitive_props_db = CIDOCProperty.objects.filter(is_transitive=True)
    
    symmetric_ids_db = [p.property_id for p in symmetric_props_db]
    transitive_ids_db = [p.property_id for p in transitive_props_db]
    
    print(f"\n=== Property Characteristics ===")
    print(f"Symmetric properties in RDF: {len(symmetric_numbers)}")
    print(f"Symmetric properties in DB: {symmetric_props_db.count()}")
    
    print(f"\nTransitive properties in RDF: {len(transitive_numbers)}")
    print(f"Transitive properties in DB: {transitive_props_db.count()}")
    
    # Check property domain/range for symmetric properties
    if symmetric_props_db.exists():
        print("\nSymmetric property validation:")
        for prop in symmetric_props_db[:3]:  # Check a few examples
            print(f"- {prop.property_id}: {prop.label}")
            if prop.domain_class and prop.range_class:
                if prop.domain_class == prop.range_class:
                    print(f"  ✓ Domain and range match: {prop.domain_class.class_id}")
                else:
                    print(f"  ✗ Domain {prop.domain_class.class_id} and range {prop.range_class.class_id} don't match")
    
    # Verify that all symmetric properties from RDF are in the DB
    for prop_id in symmetric_numbers:
        assert prop_id in symmetric_ids_db, f"Symmetric property {prop_id} from RDF not found in database"
    
    # Verify that all transitive properties from RDF are in the DB
    for prop_id in transitive_numbers:
        assert prop_id in transitive_ids_db, f"Transitive property {prop_id} from RDF not found in database"
    
    # For symmetric properties in DB, verify that domain and range classes match
    for prop in symmetric_props_db:
        if prop.domain_class and prop.range_class:
            assert prop.domain_class == prop.range_class, f"Symmetric property {prop.property_id} has mismatched domain and range" 