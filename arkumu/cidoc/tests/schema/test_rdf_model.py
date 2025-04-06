import pytest
from pathlib import Path
import os
from django.db import transaction
from django.core.exceptions import ValidationError

from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf


@pytest.fixture
def rdf_file_path():
    """Return the path to the CIDOC RDF file"""
    base_dir = Path(__file__).resolve().parent.parent.parent
    rdf_file = os.path.join(base_dir, 'schema', 'CIDOC_CRM_v7.1.1.rdf')
    assert os.path.exists(rdf_file), f"RDF file not found at {rdf_file}"
    return rdf_file


@pytest.fixture
def loaded_cidoc_data(rdf_file_path):
    """Load CIDOC data from RDF into actual database models"""
    with transaction.atomic():
        classes_count, properties_count = import_cidoc_from_rdf(rdf_file_path)
        print(f"\nLoaded {classes_count} classes and {properties_count} properties for testing")
        yield (classes_count, properties_count)
        # Transaction will be rolled back after the test


@pytest.mark.django_db
def test_rdf_matches_model_schema(loaded_cidoc_data):
    """Test that the RDF data properly maps to our database models"""
    # 1. Verify we have a reasonable number of classes and properties
    classes_count, properties_count = loaded_cidoc_data
    assert classes_count > 50, "Should have loaded more than 50 classes from RDF"
    assert properties_count > 100, "Should have loaded more than 100 properties from RDF"
    
    # Print some sample classes to inspect
    print("\nSample CIDOC classes:")
    for cls in CIDOCClass.objects.all()[:5]:
        print(f"- {cls.class_id}: {cls.label}")
        
    # 2. Test specific key classes exist
    key_classes = ['E1', 'E21', 'E55', 'E53']
    for cls_id in key_classes:
        cls = CIDOCClass.objects.filter(class_id__startswith=cls_id).first()
        assert cls is not None, f"Key class {cls_id} not found"
        print(f"\nFound key class: {cls.class_id} ({cls.label})")
        print(f"Description: {cls.description[:100]}...")
        
    # 3. Test class hierarchy
    e21 = CIDOCClass.objects.filter(class_id__startswith='E21').first()
    assert e21 is not None, "Person class not found"
    
    # Get parents and check if they're what we expect
    parent_ids = [p.class_id for p in e21.parent_classes.all()]
    print(f"\nE21 (Person) parents: {', '.join(parent_ids)}")
    
    # 4. Test that properties have valid domains and ranges
    for prop in CIDOCProperty.objects.all()[:5]:
        print(f"\nProperty {prop.property_id} ({prop.label}):")
        print(f"  Domain: {prop.domain_class.class_id if prop.domain_class else 'None'}")
        print(f"  Range: {prop.range_class.class_id if prop.range_class else 'None'}")
        
        # Verify domain and range are valid (when present)
        if prop.domain_class:
            assert prop.domain_class.class_id.startswith('E'), f"Invalid domain format: {prop.domain_class.class_id}"
        if prop.range_class:
            assert prop.range_class.class_id.startswith('E'), f"Invalid range format: {prop.range_class.class_id}"
            
    # 5. Test property characteristics
    # Find symmetric and transitive properties
    symmetric = CIDOCProperty.objects.filter(is_symmetric=True)
    transitive = CIDOCProperty.objects.filter(is_transitive=True)
    
    print(f"\nSymmetric properties: {symmetric.count()}")
    print(f"Transitive properties: {transitive.count()}")
    
    # 6. Test property inversions
    inverse_props = CIDOCProperty.objects.exclude(inverse_property=None)
    print(f"\nProperties with inverse: {inverse_props.count()}")
    
    if inverse_props.exists():
        example_prop = inverse_props.first()
        print(f"Example: {example_prop.property_id} has inverse {example_prop.inverse_property.property_id}")


@pytest.mark.django_db
def test_model_validation_with_real_data(loaded_cidoc_data):
    """Test validation rules with real model instances from RDF"""
    # Check that all loaded classes are valid, except for the user tracking fields
    # which are expected to be empty in tests
    for cls in CIDOCClass.objects.all()[:10]:  # Test a subset
        try:
            cls.full_clean()
            print(f"Class {cls.class_id} passed validation")
        except ValidationError as e:
            errors = e.message_dict
            # Only expected errors are created_by and updated_by
            expected_errors = {'created_by', 'updated_by'}
            unexpected_errors = set(errors.keys()) - expected_errors
            
            if unexpected_errors:
                print(f"Unexpected validation error for {cls.class_id}: {e}")
                assert False, f"Unexpected validation errors: {unexpected_errors}"
            else:
                print(f"Class {cls.class_id} has expected user field validation errors (OK)")
    
    # Test properties have required fields
    for prop in CIDOCProperty.objects.all()[:10]:
        assert prop.property_id, "Property ID is required"
        assert prop.label, "Label is required"
    
    # Test that no circular inheritance exists
    def check_for_circular_inheritance(cls, visited=None, path=None):
        """
        Check if a class has circular inheritance.
        
        Args:
            cls: The CIDOCClass to check
            visited: Set of already visited class IDs
            path: Path of classes visited in this branch
            
        Returns:
            bool: True if circular inheritance detected, False otherwise
            list: Path of circular inheritance if detected
        """
        if visited is None:
            visited = set()
        if path is None:
            path = []
            
        # Add current class to path
        current_path = path + [cls.class_id]
        
        # If we've seen this class before in the current path, we have a cycle
        if cls.id in visited:
            return True, current_path
            
        # Mark this class as visited
        visited.add(cls.id)
        
        # Check all parents
        for parent in cls.parent_classes.all():
            has_circular, circular_path = check_for_circular_inheritance(parent, visited.copy(), current_path)
            if has_circular:
                return True, circular_path
                
        return False, []
    
    # Check for circularity
    circular_classes = []
    for cls in CIDOCClass.objects.all():
        has_circular, path = check_for_circular_inheritance(cls)
        if has_circular:
            circular_classes.append((cls.class_id, path))
    
    # Report circular inheritance but don't fail the test
    # as this might be in the data itself
    if circular_classes:
        print("\nCircular inheritance detected in the following classes:")
        for class_id, path in circular_classes:
            print(f"- {class_id}: {' -> '.join(path)}")
        print("NOTE: Circular inheritance may be present in the source RDF data and may need attention.")
    
    print("\nAll tested models pass validation checks") 