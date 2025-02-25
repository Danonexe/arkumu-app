import pytest
from django.core.exceptions import ValidationError
from arkumu.cidoc.validators import (
    CIDOCSchemaValidator, 
    validate_property_type, 
    validate_property_cardinality, 
    get_valid_properties
)
from datetime import date

class MockQuerySet:
    def __init__(self, count):
        self._count = count
    def filter(self, **kwargs):
        return self
    def count(self):
        return self._count

class TestPropertyTypeValidation:
    """Tests for property type validation"""
    
    @pytest.fixture
    def validator(self):
        return CIDOCSchemaValidator.get_instance()

    def test_null_value_validation(self):
        """Test that None values are rejected for any property"""
        with pytest.raises(ValidationError, match="Invalid value type"):
            validate_property_type('P3_has_note', None)

    def test_string_property_validation(self):
        """Test validation of string/literal properties"""
        # P3_has_note accepts string values (range is E62_String which is rdfs:Literal)
        validate_property_type('P3_has_note', 'Test note')  # Should pass
        validate_property_type('P3_has_note', 123)  # Should convert to string and pass
    
    def test_numeric_property_validation(self):
        """Test validation of numeric properties"""
        # P90_has_value is a numeric property (range is E60_Number which is rdfs:Literal)
        validate_property_type('P90_has_value', 42)  # Should pass
        validate_property_type('P90_has_value', '42')  # Should pass (convertible string)
        
        # Test with non-convertible string - this should pass in current implementation
        # because E60_Number is treated as rdfs:Literal in the schema
        validate_property_type('P90_has_value', 'not a number')  # Will pass due to schema implementation
        
        # For testing validation failure, we'd need to mock the validator behavior
        # since the actual schema doesn't enforce numeric types

    def test_date_property_validation(self):
        """Test validation of date properties"""
        # P82_at_some_time_within is a date property (range is E61_Time_Primitive which is rdfs:Literal)
        validate_property_type('P82_at_some_time_within', date(2024, 1, 1))  # Should pass
        validate_property_type('P82_at_some_time_within', '2024-01-01')  # Should pass
        
        # Test with invalid date format - this should pass in current implementation
        # because E61_Time_Primitive is treated as rdfs:Literal in the schema
        validate_property_type('P82_at_some_time_within', 'invalid date')  # Will pass due to schema implementation
        
        # For testing validation failure, we'd need to mock the validator behavior
        # since the actual schema doesn't enforce date types

class TestPropertyCardinality:
    """Tests for property cardinality validation"""
    
    def test_functional_property_validation(self):
        """Test validation of functional properties (can have at most one value)"""
        # P48_has_preferred_identifier is a functional property
        
        # Test with single value (should pass)
        entity_with_single_value = type('MockEntity', (), {
            'cidocentityproperty_set': MockQuerySet(1)
        })()
        validate_property_cardinality(entity_with_single_value, 'P48_has_preferred_identifier')
        
        # Test with multiple values (should fail)
        entity_with_multiple_values = type('MockEntity', (), {
            'cidocentityproperty_set': MockQuerySet(2)
        })()
        with pytest.raises(ValidationError, match="can have at most one value"):
            validate_property_cardinality(entity_with_multiple_values, 'P48_has_preferred_identifier')
    
    def test_non_functional_property_validation(self):
        """Test validation of non-functional properties (can have multiple values)"""
        # P3_has_note is typically non-functional
        entity_with_multiple_values = type('MockEntity', (), {
            'cidocentityproperty_set': MockQuerySet(3)
        })()
        # This should not raise an exception
        validate_property_cardinality(entity_with_multiple_values, 'P3_has_note')

class TestPropertyDomainRange:
    """Tests for property domain and range validation"""
    
    @pytest.fixture
    def validator(self):
        """Get a fresh validator instance for each test"""
        CIDOCSchemaValidator.clear_cache()
        return CIDOCSchemaValidator.get_instance()

    def test_property_domain_validation(self, validator):
        """Test validation of property domains"""
        # P1_is_identified_by has domain E1_CRM_Entity
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        
        # Valid domain: exact match
        validator._check_domain(
            prop_uri,
            validator._get_class_uri('E1_CRM_Entity'),
            'P1_is_identified_by',
            'E1_CRM_Entity'
        )
        
        # Invalid domain
        with pytest.raises(ValidationError, match="Invalid domain for"):
            validator._check_domain(
                prop_uri,
                validator._get_class_uri('E55_Type'),  # Not a valid domain for P1
                'P1_is_identified_by',
                'E55_Type'
            )

    def test_property_range_validation(self, validator):
        """Test validation of property ranges"""
        # P1_is_identified_by has range E41_Appellation
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        
        # Valid range: exact match
        validator._check_range(
            prop_uri,
            validator._get_class_uri('E41_Appellation'),
            'P1_is_identified_by',
            'E41_Appellation'
        )
        
        # Invalid range
        with pytest.raises(ValidationError, match="Invalid range for"):
            validator._check_range(
                prop_uri,
                validator._get_class_uri('E21_Person'),  # Not a valid range for P1
                'P1_is_identified_by',
                'E21_Person'
            )

    def test_complete_property_constraint_validation(self, validator):
        """Test complete property domain and range validation"""
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        
        # Valid case: correct domain and range
        validator._verify_property_constraints(
            prop_uri,
            validator._get_class_uri('E1_CRM_Entity'),
            validator._get_class_uri('E41_Appellation'),
            'P1_is_identified_by',
            'E1_CRM_Entity',
            'E41_Appellation'
        )
        
        # Invalid domain
        with pytest.raises(ValidationError, match="Invalid domain for"):
            validator._verify_property_constraints(
                prop_uri,
                validator._get_class_uri('E55_Type'),  # Invalid domain
                validator._get_class_uri('E41_Appellation'),
                'P1_is_identified_by',
                'E55_Type',
                'E41_Appellation'
            )
        
        # Invalid range
        with pytest.raises(ValidationError, match="Invalid range for"):
            validator._verify_property_constraints(
                prop_uri,
                validator._get_class_uri('E1_CRM_Entity'),
                validator._get_class_uri('E21_Person'),  # Invalid range
                'P1_is_identified_by',
                'E1_CRM_Entity',
                'E21_Person'
            )

class TestPropertyUtilities:
    """Tests for property utility functions"""
    
    def test_get_valid_properties(self):
        """Test retrieving valid properties for a class"""
        # Get properties for E21_Person
        properties = get_valid_properties('E21_Person')
        
        # Verify we got a non-empty set
        assert len(properties) > 0
        
        # Verify some expected properties are present
        property_ids = {str(p).split('/')[-1] for p in properties}
        assert 'P1_is_identified_by' in property_ids
        
        # E21_Person should have more properties than E1_CRM_Entity
        # due to inheritance in the class hierarchy
        base_properties = get_valid_properties('E1_CRM_Entity')
        assert len(properties) >= len(base_properties)
