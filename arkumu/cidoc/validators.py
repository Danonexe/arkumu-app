from rdflib import Graph as RDFGraph, RDFS, RDF, Namespace, OWL
from pathlib import Path
import logging
from django.core.exceptions import ValidationError
from datetime import datetime, date, time

logger = logging.getLogger(__name__)



class CIDOCSchemaValidator:
    _instance = None
    _class_cache = {}
    _property_cache = {}
    
    def __init__(self):
        self.graph = RDFGraph()
        
        # Define namespaces
        self.CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
        self.graph.bind('crm', self.CRM)
        
        # Load schema file
        schema_path = Path(__file__).parent / 'schema' / 'cidoc_crm.ttl'
        try:
            self.graph.parse(str(schema_path), format='turtle')
        except Exception as e:
            logger.error(f"Failed to load TTL schema: {e}")
            # Fallback to RDF/XML
            try:
                xml_path = Path(__file__).parent / 'schema' / 'cidoc_crm.xml'
                self.graph.parse(str(xml_path), format='xml')
            except Exception as e:
                logger.error(f"Failed to load XML schema: {e}")
                raise ValueError("Could not load CIDOC-CRM schema")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_class_uri(self, crm_class):
        """Convert class name to full URI"""
        return self.CRM[crm_class]

    def _get_property_uri(self, property_id):
        """Convert property ID to full URI"""
        return self.CRM[property_id]

    def _get_class_hierarchy(self, crm_class):
        """Get all superclasses with caching"""
        if crm_class not in self._class_cache:
            class_uri = self._get_class_uri(crm_class)
            self._class_cache[crm_class] = set(
                self.graph.transitive_objects(class_uri, RDFS.subClassOf)
            )
        return self._class_cache[crm_class]

    def _is_valid_property(self, property_id):
        """Check if property exists with caching"""
        if property_id not in self._property_cache:
            property_uri = self._get_property_uri(property_id)
            self._property_cache[property_id] = (
                property_uri, RDF.type, RDF.Property
            ) in self.graph
        return self._property_cache[property_id]

def validate_cidoc_entity(crm_class):
    """
    Validate that a CRM class exists in the schema.
    
    Args:
        crm_class (str): The CIDOC-CRM class identifier (e.g., 'E21_Person')
    
    Raises:
        ValidationError: If the class is invalid
    """
    validator = CIDOCSchemaValidator.get_instance()
    class_uri = validator._get_class_uri(crm_class)
    
    if (class_uri, RDF.type, RDFS.Class) not in validator.graph:
        raise ValidationError(f"Invalid CIDOC-CRM class: {crm_class}")

def validate_cidoc_relationship(property_id, domain_class, range_class):
    """
    Validate a CIDOC-CRM property with its domain and range.
    
    Args:
        property_id (str): The property identifier (e.g., 'P1_is_identified_by')
        domain_class (str): The domain class identifier
        range_class (str): The range class identifier
    
    Raises:
        ValidationError: If the property or domain/range are invalid
    """
    validator = CIDOCSchemaValidator.get_instance()
    
    property_uri = validator._get_property_uri(property_id)
    domain_uri = validator._get_class_uri(domain_class)
    range_uri = validator._get_class_uri(range_class)

    # Check if property exists
    if (property_uri, RDF.type, RDF.Property) not in validator.graph:
        raise ValidationError(f"Invalid CIDOC-CRM property: {property_id}")

    # Get declared domain and range
    declared_domain = validator.graph.value(property_uri, RDFS.domain)
    declared_range = validator.graph.value(property_uri, RDFS.range)

    if declared_domain is None or declared_range is None:
        raise ValidationError(f"Property {property_id} has no domain or range defined")

    # Get class hierarchies
    domain_superclasses = validator._get_class_hierarchy(domain_class)
    range_superclasses = validator._get_class_hierarchy(range_class)

    # Validate domain
    if (declared_domain not in domain_superclasses and 
        domain_uri != declared_domain):
        raise ValidationError(
            f"Invalid domain for {property_id}: "
            f"Expected {declared_domain}, got {domain_class}"
        )

    # Validate range
    if (declared_range not in range_superclasses and 
        range_uri != declared_range):
        raise ValidationError(
            f"Invalid range for {property_id}: "
            f"Expected {declared_range}, got {range_class}"
        )

def get_valid_properties(domain_class):
    """
    Get all valid properties for a given domain class.
    
    Args:
        domain_class (str): The CIDOC-CRM class identifier
    
    Returns:
        set: Set of valid property URIs
    """
    validator = CIDOCSchemaValidator.get_instance()
    domain_uri = validator._get_class_uri(domain_class)
    valid_properties = set()

    class_hierarchy = validator._get_class_hierarchy(domain_class)
    class_hierarchy.add(domain_uri)

    for prop in validator.graph.subjects(RDFS.domain):
        prop_domain = validator.graph.value(prop, RDFS.domain)
        if prop_domain in class_hierarchy:
            valid_properties.add(prop)

    return valid_properties

def validate_cidoc_property(property_id):
    """
    Validate that a property exists in the CIDOC-CRM schema.
    
    Args:
        property_id (str): The property identifier (e.g., 'P1_is_identified_by')
    
    Raises:
        ValidationError: If the property is invalid
    """
    validator = CIDOCSchemaValidator.get_instance()
    property_uri = validator._get_property_uri(property_id)
    
    if (property_uri, RDF.type, RDF.Property) not in validator.graph:
        raise ValidationError(f"Invalid CIDOC-CRM property: {property_id}")

def expected_python_type(xml_datatype):
    """
    Map XML Schema datatypes to Python types.
    
    Args:
        xml_datatype (URIRef): The XML Schema datatype URI
    
    Returns:
        type: The corresponding Python type
    """
    datatype = str(xml_datatype)
    
    XML_TO_PYTHON_TYPES = {
        'http://www.w3.org/2001/XMLSchema#string': str,
        'http://www.w3.org/2001/XMLSchema#integer': int,
        'http://www.w3.org/2001/XMLSchema#decimal': float,
        'http://www.w3.org/2001/XMLSchema#float': float,
        'http://www.w3.org/2001/XMLSchema#double': float,
        'http://www.w3.org/2001/XMLSchema#boolean': bool,
        'http://www.w3.org/2001/XMLSchema#date': date,
        'http://www.w3.org/2001/XMLSchema#dateTime': datetime,
        'http://www.w3.org/2001/XMLSchema#time': time,
        'http://www.w3.org/2001/XMLSchema#anyURI': str,
    }
    
    return XML_TO_PYTHON_TYPES.get(datatype, str)

def validate_property_type(property_id, value):
    """
    Validate that a property value matches expected type.
    
    Args:
        property_id (str): The property identifier
        value: The value to validate
        
    Raises:
        ValidationError: If the value type doesn't match the expected type
    """
    validator = CIDOCSchemaValidator.get_instance()
    property_uri = validator._get_property_uri(property_id)
    
    # Check for datatype properties vs object properties
    range_type = validator.graph.value(property_uri, RDFS.range)
    if str(range_type).startswith('http://www.w3.org/2001/XMLSchema#'):
        expected_type = expected_python_type(range_type)
        try:
            # Try to convert value to expected type
            expected_type(value)
        except (ValueError, TypeError):
            raise ValidationError(
                f"Invalid value type for {property_id}. "
                f"Expected {expected_type.__name__}, got {type(value).__name__}"
            )

def validate_property_cardinality(entity, property_id):
    """
    Validate property cardinality constraints.
    """
    validator = CIDOCSchemaValidator.get_instance()
    property_uri = validator._get_property_uri(property_id)
    
    # Check for functional properties (max 1)
    if (property_uri, RDF.type, OWL.FunctionalProperty) in validator.graph:
        count = entity.cidocentityproperty_set.filter(
            property__property_id=property_id
        ).count()
        if count > 1:
            raise ValidationError(
                f"Property {property_id} can have at most one value"
            )
