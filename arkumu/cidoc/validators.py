from django.core.cache import cache
from rdflib import Graph as RDFGraph, RDFS, RDF, Namespace, OWL
from pathlib import Path
import logging
from django.core.exceptions import ValidationError
from datetime import datetime, date, time

logger = logging.getLogger(__name__)



class CIDOCSchemaValidator:
    CACHE_KEY = 'cidoc_schema_validator'
    CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours
    _instance = None  # Class-level instance storage

    @classmethod
    def get_instance(cls):
        """Get or create cached validator instance using class-level singleton"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_schema_files(self):
        """Load and parse the CIDOC-CRM and CRMdig schema files."""
        schema_dir = Path(__file__).parent / 'schema'
        
        # Load CIDOC-CRM schema
        cidoc_file = schema_dir / 'CIDOC_CRM_v7.1.1.rdf'
        if not cidoc_file.exists():
            raise FileNotFoundError(f"CIDOC-CRM schema file not found at {cidoc_file}")
        
        # Load CRMdig schema
        crmdig_file = schema_dir / 'CRMdig_v3.2.1.rdfs'
        if not crmdig_file.exists():
            raise FileNotFoundError(f"CRMdig schema file not found at {crmdig_file}")
        
        try:
            # Parse CIDOC-CRM
            self.graph.parse(
                source=str(cidoc_file),
                format='xml',
                publicID=str(self.CRM)
            )
            
            # Parse CRMdig
            self.graph.parse(
                source=str(crmdig_file),
                format='xml',
                publicID=str(self.CRMDIG)
            )
            
            # Bind namespaces after loading
            self.graph.bind('crm', self.CRM)
            self.graph.bind('crmdig', self.CRMDIG)
            
        except Exception as e:
            logger.error(f"Failed to parse schema files: {e}")
            raise ValueError(f"Could not load CIDOC-CRM schemas: {str(e)}")

    def __init__(self):
        if not hasattr(self, 'graph'):  # Only initialize once
            self.graph = RDFGraph()
            
            # Define namespaces
            self.CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
            self.CRMDIG = Namespace("http://www.ics.forth.gr/isl/CRMdig/")
            
            # Initialize caches
            self._class_cache = {}
            self._property_cache = {}
            self._class_hierarchy = {}
            self._property_hierarchy = {}

            # Load schema files
            self._load_schema_files()
            
            # Pre-warm caches
            self._warm_caches()

    def _warm_caches(self):
        """Pre-warm the class and property caches"""
        # Cache all CIDOC-CRM classes
        for class_uri in self.graph.subjects(RDF.type, RDFS.Class):
            if str(class_uri).startswith((str(self.CRM), str(self.CRMDIG))):
                class_id = class_uri.split('/')[-1]
                self._class_cache[class_id] = set(
                    self.graph.transitive_objects(class_uri, RDFS.subClassOf)
                )

        # Cache all CIDOC-CRM properties
        for prop_uri in self.graph.subjects(RDF.type, RDF.Property):
            if str(prop_uri).startswith((str(self.CRM), str(self.CRMDIG))):
                prop_id = prop_uri.split('/')[-1]
                self._property_cache[prop_id] = True

    def _get_class_uri(self, class_id):
        """Convert class ID to full URI, handling both CRM and CRMdig classes"""
        if class_id.startswith('D'):
            return self.CRMDIG[class_id]
        return self.CRM[class_id]

    def _get_property_uri(self, property_id):
        """Convert property ID to full URI, handling both CRM and CRMdig properties"""
        if property_id.startswith('L'):
            return self.CRMDIG[property_id]
        return self.CRM[property_id]

    def _get_class_hierarchy(self, crm_class):
        """Get all superclasses with caching"""
        if crm_class not in self._class_cache:
            class_uri = self._get_class_uri(crm_class)
            self._class_cache[crm_class] = set(
                self.graph.transitive_objects(class_uri, RDFS.subClassiOf)
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

    @classmethod
    def clear_cache(cls):
        """Clear the cached validator instance"""
        cls._instance = None

    def _verify_classes_exist(self, domain_class, range_class):
        """Verify both domain and range classes exist in the schema."""
        try:
            domain_uri = self._get_class_uri(domain_class)
            range_uri = self._get_class_uri(range_class)
            
            if (domain_uri, RDF.type, RDFS.Class) not in self.graph:
                raise ValidationError(f"Domain class does not exist: {domain_class}")
            if (range_uri, RDF.type, RDFS.Class) not in self.graph:
                raise ValidationError(f"Range class does not exist: {range_class}")
            
            return domain_uri, range_uri
        except Exception as e:
            raise ValidationError(f"Invalid classes: {str(e)}")

    def _verify_digital_compatibility(self, property_id, domain_class, range_class):
        """Verify digital/non-digital property compatibility."""
        is_digital_property = property_id.startswith('L')
        is_digital_class = domain_class.startswith('D') or range_class.startswith('D')
        
        if is_digital_property and not is_digital_class:
            raise ValidationError(f"Digital property {property_id} cannot be used with non-digital classes")

    def _verify_property_constraints(self, property_uri, domain_uri, range_uri, property_id, domain_class, range_class):
        """Verify property domain and range constraints - simple version."""
        # Get declared domain and range directly
        declared_domain = self.graph.value(property_uri, RDFS.domain)
        declared_range = self.graph.value(property_uri, RDFS.range)
        
        # Basic validation - just check if domain/range match exactly
        if domain_uri != declared_domain:
            raise ValidationError(
                f"Invalid domain for {property_id}: {domain_class}"
            )
        
        if range_uri != declared_range:
            raise ValidationError(
                f"Invalid range for {property_id}: {range_class}"
            )

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
    
    # Verify property exists
    property_uri = validator._get_property_uri(property_id)
    if not validator._is_valid_property(property_id):
        raise ValidationError(f"Property does not exist: {property_id}")
    
    # Verify classes exist
    domain_uri, range_uri = validator._verify_classes_exist(domain_class, range_class)
    
    # Check digital/non-digital compatibility
    validator._verify_digital_compatibility(property_id, domain_class, range_class)
    
    # Verify property constraints
    validator._verify_property_constraints(
        property_uri, domain_uri, range_uri,
        property_id, domain_class, range_class
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
