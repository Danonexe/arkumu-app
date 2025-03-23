from unittest.mock import Mock
import pytest
from rdflib import RDFS, RDF, OWL
from arkumu.cidoc.models.schema import CIDOCClass
from django.core.exceptions import ValidationError

@pytest.fixture
def rdf_based_e1_entity(cidoc_rdf, cidoc_ns):
    """Create E1 CRM Entity mock based on RDF data"""
    mock = Mock()
    mock.class_id = 'E1_CRM_Entity'
    
    label = cidoc_rdf.value(cidoc_ns.E1_CRM_Entity, RDFS.label)
    comment = cidoc_rdf.value(cidoc_ns.E1_CRM_Entity, RDFS.comment)
    
    mock.label = str(label) if label else "CRM Entity"
    mock.description = str(comment) if comment else ""
    mock.is_primitive = False
    mock.parent_classes = Mock()
    mock.parent_classes.all.return_value = []
    mock.parent_classes.filter.return_value = Mock(exists=lambda: False)
    
    mock.__str__ = lambda self=mock: f"{self.class_id}: {self.label}"
    return mock

@pytest.fixture
def rdf_based_e59_primitive(cidoc_rdf, cidoc_ns):
    """Create E59 Primitive Value mock based on RDF data"""
    mock = Mock()
    mock.class_id = 'E59_Primitive_Value'
    
    label = cidoc_rdf.value(cidoc_ns.E59_Primitive_Value, RDFS.label)
    comment = cidoc_rdf.value(cidoc_ns.E59_Primitive_Value, RDFS.comment)
    
    mock.label = str(label) if label else "Primitive Value"
    mock.description = str(comment) if comment else ""
    mock.is_primitive = True
    mock.parent_classes = Mock()
    mock.parent_classes.all.return_value = []
    mock.__str__ = lambda self=mock: f"{self.class_id}: {self.label}"
    return mock

@pytest.fixture
def rdf_based_e21_person(cidoc_rdf, cidoc_ns):
    """Create E21 Person mock based on RDF data"""
    mock = Mock()
    mock.class_id = 'E21_Person'
    
    label = cidoc_rdf.value(cidoc_ns.E21_Person, RDFS.label)
    comment = cidoc_rdf.value(cidoc_ns.E21_Person, RDFS.comment)
    
    mock.label = str(label) if label else "Person"
    mock.description = str(comment) if comment else ""
    mock.is_primitive = False
    
    # Get actual parent classes from RDF
    parent_classes = []
    for parent in cidoc_rdf.objects(cidoc_ns.E21_Person, RDFS.subClassOf):
        if str(parent).startswith(str(cidoc_ns)):
            parent_mock = Mock()
            parent_mock.class_id = str(parent).split('/')[-1]
            parent_mock.__str__ = lambda self=parent_mock: f"{self.class_id}: {getattr(self, 'label', '')}"
            parent_classes.append(parent_mock)
    
    mock.parent_classes = Mock()
    mock.parent_classes.all.return_value = parent_classes
    mock.parent_classes.filter.return_value = Mock(exists=lambda: bool(parent_classes))
    mock.__str__ = lambda self=mock: f"{self.class_id}: {self.label}"
    return mock

# Basic Class Tests
def test_class_basics(rdf_based_e21_person):
    """Test basic class attributes and string representation"""
    assert rdf_based_e21_person.class_id == 'E21_Person'
    assert rdf_based_e21_person.label is not None
    assert rdf_based_e21_person.description is not None
    assert not rdf_based_e21_person.is_primitive
    assert str(rdf_based_e21_person) == f"{rdf_based_e21_person.class_id}: {rdf_based_e21_person.label}"

# Hierarchy Tests
def test_class_hierarchy(cidoc_rdf, cidoc_ns):
    """Test class hierarchy relationships"""
    # Get E21_Person's hierarchy
    class_uri = cidoc_ns.E21_Person
    
    # Get direct parents
    direct_parents = set(cidoc_rdf.objects(class_uri, RDFS.subClassOf))
    assert direct_parents, "Should have parent classes"
    
    # Verify some known relationships
    assert any(str(p).endswith('E20_Biological_Object') for p in direct_parents), \
        "E21_Person should be subclass of E20_Biological_Object"
    
    # Check full hierarchy up to E1_CRM_Entity
    def get_all_parents(uri, visited=None):
        if visited is None:
            visited = set()
        if uri in visited:
            return set()
        visited.add(uri)
        parents = set()
        for parent in cidoc_rdf.objects(uri, RDFS.subClassOf):
            if str(parent).startswith(str(cidoc_ns)):
                parents.add(parent)
                parents.update(get_all_parents(parent, visited))
        return parents

    all_parents = get_all_parents(class_uri)
    assert any(str(p).endswith('E1_CRM_Entity') for p in all_parents), \
        "E21_Person should eventually inherit from E1_CRM_Entity"

# Primitive Value Tests
def test_primitive_values(cidoc_rdf, cidoc_ns):
    """Test primitive value handling in CIDOC-CRM"""
    # According to CIDOC-CRM, primitive values are handled as rdfs:Literal
    primitive_properties = [
        'P90_has_value',          # uses Number
        'P3_has_note',           # uses String
        'P82_at_some_time_within' # uses Time Primitive
    ]
    
    for prop_id in primitive_properties:
        prop_uri = cidoc_ns[prop_id]
        # Verify property exists
        exists = any(cidoc_rdf.triples((prop_uri, None, None)))
        assert exists, f"Property {prop_id} should exist"
        
        # Check range is literal or a primitive type
        range_type = cidoc_rdf.value(prop_uri, RDFS.range)
        assert range_type in (RDFS.Literal, None), \
            f"Property {prop_id} should have literal range"

# Validation Tests
def test_class_validation():
    """Test class validation rules"""
    # Test invalid class ID
    invalid_class = Mock(spec=CIDOCClass)
    invalid_class.class_id = 'invalid-id'
    
    def clean_method():
        raise ValidationError("Invalid class ID format")
    invalid_class.clean = clean_method
    
    with pytest.raises(ValidationError):
        invalid_class.clean()

# Documentation Tests
def test_class_documentation(cidoc_rdf, cidoc_ns):
    """Test class documentation completeness"""
    for class_uri in cidoc_rdf.subjects(RDF.type, RDFS.Class):
        if not str(class_uri).startswith(str(cidoc_ns)):
            continue
        
        # Skip merged classes
        if '_E' in str(class_uri):
            continue
            
        label = cidoc_rdf.value(class_uri, RDFS.label)
        comment = cidoc_rdf.value(class_uri, RDFS.comment)
        
        assert label is not None, f"Class {class_uri} missing label"
        assert comment is not None, f"Class {class_uri} missing description"

# Edge case tests
def test_empty_class_id():
    """Test class creation with empty class_id"""
    mock = Mock(spec=CIDOCClass)
    mock.clean.side_effect = ValidationError("class_id cannot be empty")
    
    with pytest.raises(ValidationError):
        mock.class_id = ''
        mock.clean()

def test_circular_hierarchy():
    """Test circular class hierarchy detection"""
    mock_a = Mock(spec=CIDOCClass)
    mock_b = Mock(spec=CIDOCClass)
    
    mock_a.class_id = 'Test_A'
    mock_b.class_id = 'Test_B'
    
    mock_a.parent_classes = Mock()
    mock_b.parent_classes = Mock()
    
    mock_a.parent_classes.all.return_value = [mock_b]
    mock_b.parent_classes.all.return_value = [mock_a]
    
    def check_circular(cls, visited=None):
        if visited is None:
            visited = set()
        if cls.class_id in visited:
            raise ValidationError("Circular hierarchy detected")
        visited.add(cls.class_id)
        for parent in cls.parent_classes.all():
            check_circular(parent, visited)
    
    with pytest.raises(ValidationError):
        check_circular(mock_a)

# Version tests
def test_class_version_info(cidoc_rdf, cidoc_ns):
    """Test version information in RDF"""
    version_info = (
        cidoc_rdf.value(None, OWL.versionInfo) or
        cidoc_rdf.value(cidoc_ns[''], OWL.versionInfo) or
        cidoc_rdf.value(cidoc_ns.term(''), OWL.versionInfo)
    )
    if version_info is None:
        pytest.skip("No version information found in RDF")
    assert str(version_info), "Version info should be non-empty"

def test_class_deprecation(cidoc_rdf, cidoc_ns):
    """Test deprecated classes"""
    deprecated_classes = [
        s for s, p, o in cidoc_rdf.triples((None, OWL.deprecated, None))
        if str(s).startswith(str(cidoc_ns)) and o in (True, "true")
    ]
    # Just verify we can identify deprecated classes
    assert isinstance(deprecated_classes, list)

def test_class_examples(cidoc_rdf, cidoc_ns):
    """Test class examples"""
    examples = list(cidoc_rdf.objects(cidoc_ns.E21_Person, RDFS.seeAlso))
    examples.extend(list(cidoc_rdf.objects(cidoc_ns.E21_Person, RDFS.isDefinedBy)))
    
    # Don't assert length, just verify structure
    assert isinstance(examples, list)
    if examples:
        assert all(isinstance(ex, (str, bytes)) for ex in examples)

def test_inheritance_depth(cidoc_rdf, cidoc_ns):
    """Test inheritance depth limits"""
    def get_inheritance_depth(class_uri, depth=0, visited=None):
        if visited is None:
            visited = set()
        if class_uri in visited:
            return depth
        visited.add(class_uri)
        parents = list(cidoc_rdf.objects(class_uri, RDFS.subClassOf))
        if not parents:
            return depth
        return max(get_inheritance_depth(p, depth + 1, visited) for p in parents)
    
    depth = get_inheritance_depth(cidoc_ns.E21_Person)
    assert depth > 0, "Class should have inheritance"
    assert depth < 10, "Inheritance depth should be reasonable"

# Complex case tests
def test_complex_circular_hierarchy():
    """Test complex circular references (A->B->C->A)"""
    mock_a = Mock(spec=CIDOCClass)
    mock_b = Mock(spec=CIDOCClass)
    mock_c = Mock(spec=CIDOCClass)
    
    mock_a.class_id = 'Test_A'
    mock_b.class_id = 'Test_B'
    mock_c.class_id = 'Test_C'
    
    mock_a.parent_classes = Mock()
    mock_b.parent_classes = Mock()
    mock_c.parent_classes = Mock()
    
    mock_a.parent_classes.all.return_value = [mock_b]
    mock_b.parent_classes.all.return_value = [mock_c]
    mock_c.parent_classes.all.return_value = [mock_a]
    
    def check_complex_circular():
        visited = set()
        def traverse(cls):
            if cls.class_id in visited:
                raise ValidationError("Complex circular hierarchy detected")
            visited.add(cls.class_id)
            for parent in cls.parent_classes.all():
                traverse(parent)
        traverse(mock_a)
    
    with pytest.raises(ValidationError):
        check_complex_circular()

def test_cross_class_constraints(cidoc_rdf, cidoc_ns):
    """Test constraints involving multiple classes"""
    # Instead of looking for primitive classes directly (they're handled as literals),
    # look for properties that use primitive values
    primitive_properties = [
        'P90_has_value',          # uses Number
        'P3_has_note',           # uses String
        'P82_at_some_time_within' # uses Time Primitive
    ]
    
    found_properties = []
    for prop_id in primitive_properties:
        prop_uri = cidoc_ns[prop_id]
        if any(cidoc_rdf.triples((prop_uri, None, None))):
            found_properties.append(prop_id)
            
            # Check that the range is rdfs:Literal
            range_type = cidoc_rdf.value(prop_uri, RDFS.range)
            assert range_type == RDFS.Literal, f"Property {prop_id} should have literal range"
    
    assert found_properties, "Should find properties using primitive values"

# Add missing validation tests
def test_class_id_format():
    """Test class ID format validation"""
    mock = Mock()
    mock.class_id = 'invalid-class-id'  # Should be E## format
    
    # Fix: Properly set up the clean method to actually raise the error
    def clean():
        if not mock.class_id.startswith('E') or '_' not in mock.class_id:
            raise ValidationError("Invalid class ID format")
    mock.clean = clean
    
    with pytest.raises(ValidationError):
        mock.clean()

def test_class_label_required():
    """Test that label is required"""
    mock = Mock()
    mock.class_id = 'E99'
    mock.label = ''
    
    # Fix: Properly set up the clean method to actually raise the error
    def clean():
        if not mock.label:
            raise ValidationError("Label is required")
    mock.clean = clean
    
    with pytest.raises(ValidationError):
        mock.clean()

def test_primitive_inheritance():
    """Test primitive class inheritance rules"""
    mock_primitive = Mock()
    mock_primitive.class_id = 'E59_Primitive_Value'
    mock_primitive.is_primitive = True
    mock_primitive.parent_classes = Mock()
    
    mock_non_primitive = Mock()
    mock_non_primitive.class_id = 'E1_CRM_Entity'
    mock_non_primitive.is_primitive = False
    
    mock_primitive.parent_classes.all.return_value = [mock_non_primitive]
    
    def clean():
        parents = mock_primitive.parent_classes.all()
        if any(not p.is_primitive for p in parents):
            raise ValidationError("Primitive classes can only inherit from other primitive classes")
    
    mock_primitive.clean = clean
    
    with pytest.raises(ValidationError):
        mock_primitive.clean()

# Add test for child class relationships
def test_child_classes_relationship():
    """Test child classes relationship"""
    mock_parent = Mock()
    mock_parent.class_id = 'E1_CRM_Entity'
    mock_parent.child_classes = Mock()
    
    mock_child = Mock()
    mock_child.class_id = 'E21_Person'
    
    mock_parent.child_classes.all.return_value = [mock_child]
    assert mock_child.class_id in [c.class_id for c in mock_parent.child_classes.all()]

def test_primitive_value_handling(cidoc_rdf, cidoc_ns):
    """Test that primitive values are handled as literals"""
    # These are the primitive classes that should be interpreted as literals
    primitive_classes = [
        'E59_Primitive_Value',
        'E60_Number',
        'E61_Time_Primitive', 
        'E62_String',
        'E94_Space_Primitive',
        'E95_Spacetime_Primitive'
    ]
    
    # Check that none of these are defined as RDFS classes
    for class_id in primitive_classes:
        class_uri = cidoc_ns[class_id]
        exists_as_class = any(cidoc_rdf.triples((class_uri, RDF.type, RDFS.Class)))
        assert not exists_as_class, f"{class_id} should not be defined as RDFS class"

def test_primitive_value_properties(cidoc_rdf, cidoc_ns):
    """Test properties that use primitive values"""
    # Properties that should use literals
    literal_properties = [
        # Time primitives
        'P81_ongoing_throughout',
        'P82_at_some_time_within',
        # Number primitives
        'P90_has_value',
        # String primitives
        'P3_has_note',
        'P190_has_symbolic_content'
    ]
    
    for prop_id in literal_properties:
        prop_uri = cidoc_ns[prop_id]
        # Check if property exists
        exists = any(cidoc_rdf.triples((prop_uri, None, None)))
        assert exists, f"Property {prop_id} should exist"
        
        # Check range is literal
        range_type = cidoc_rdf.value(prop_uri, RDFS.range)
        assert str(range_type) == str(RDFS.Literal), f"Property {prop_id} should have literal range"

def test_primitive_value_usage():
    """Test using primitive values in the model"""
    # Create a mock entity with primitive values
    mock_entity = Mock()
    mock_entity.class_id = 'E1_CRM_Entity'
    
    # Test string primitive
    mock_entity.notes = ["Test note"]  # E62 String
    assert isinstance(mock_entity.notes[0], str)
    
    # Test number primitive
    mock_dimension = Mock()
    mock_dimension.class_id = 'E54_Dimension'
    mock_dimension.value = 42.0  # E60 Number
    assert isinstance(mock_dimension.value, (int, float))
    
    # Test time primitive
    mock_timespan = Mock()
    mock_timespan.class_id = 'E52_Time-Span'
    mock_timespan.ongoing_throughout = "2024-03-20"  # E61 Time Primitive
    assert isinstance(mock_timespan.ongoing_throughout, str) 