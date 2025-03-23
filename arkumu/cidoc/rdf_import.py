import rdflib
from django.db import transaction
from ..models.core import CIDOCClass, CIDOCProperty

@transaction.atomic
def import_cidoc_from_rdf(rdf_file_path, namespace="http://www.cidoc-crm.org/cidoc-crm/"):
    """
    Import CIDOC-CRM classes and properties from an RDF file.
    
    Args:
        rdf_file_path (str): Path to the RDF file
        namespace (str): CIDOC-CRM namespace
        
    Returns:
        tuple: (classes_count, properties_count) - Number of classes and properties imported
    """
    # Parse RDF
    g = rdflib.Graph()
    g.parse(rdf_file_path)
    
    # Set up namespaces
    RDFS = rdflib.namespace.RDFS
    RDF = rdflib.namespace.RDF
    CIDOC = rdflib.Namespace(namespace)
    
    # Track counts
    classes_count = 0
    properties_count = 0
    
    # First pass: Import all classes
    class_map = {}  # Maps URIs to CIDOCClass instances
    
    for class_uri in g.subjects(RDF.type, RDFS.Class):
        if str(class_uri).startswith(namespace):
            class_id = str(class_uri).split('/')[-1]
            label = g.value(class_uri, RDFS.label, None)
            comment = g.value(class_uri, RDFS.comment, None)
            
            # Create class
            cidoc_class, created = CIDOCClass.objects.get_or_create(
                class_id=class_id,
                defaults={
                    'label': str(label) if label else class_id,
                    'description': str(comment) if comment else ''
                }
            )
            
            class_map[class_uri] = cidoc_class
            if created:
                classes_count += 1
    
    # Second pass: Set up class hierarchy
    for class_uri, cidoc_class in class_map.items():
        for parent in g.objects(class_uri, RDFS.subClassOf):
            if parent in class_map:
                cidoc_class.parent_classes.add(class_map[parent])
    
    # Import properties
    for prop_uri in g.subjects(RDF.type, RDF.Property):
        if str(prop_uri).startswith(namespace):
            prop_id = str(prop_uri).split('/')[-1]
            label = g.value(prop_uri, RDFS.label, None)
            comment = g.value(prop_uri, RDFS.comment, None)
            domain = g.value(prop_uri, RDFS.domain, None)
            range_class = g.value(prop_uri, RDFS.range, None)
            
            # Get domain and range classes
            domain_class = None
            if domain in class_map:
                domain_class = class_map[domain]
            
            range_obj = None
            if range_class in class_map:
                range_obj = class_map[range_class]
            
            # Determine property type
            property_type = 'string'  # Default
            if range_class:
                if 'Dimension' in str(range_class):
                    property_type = 'numeric'
                elif 'Time' in str(range_class):
                    property_type = 'date'
                elif 'URI' in str(range_class):
                    property_type = 'uri'
                elif 'Boolean' in str(range_class):
                    property_type = 'boolean'
            
            # Check for symmetric properties
            is_symmetric = False
            is_transitive = False
            for _, pred, obj in g.triples((prop_uri, None, None)):
                if 'symmetric' in str(pred).lower():
                    is_symmetric = True
                if 'transitive' in str(pred).lower():
                    is_transitive = True
            
            # Create property
            cidoc_property, created = CIDOCProperty.objects.get_or_create(
                property_id=prop_id,
                defaults={
                    'label': str(label) if label else prop_id,
                    'description': str(comment) if comment else '',
                    'domain_class': domain_class,
                    'range_class': range_obj,
                    'property_type': property_type,
                    'is_symmetric': is_symmetric,
                    'is_transitive': is_transitive
                }
            )
            
            if created:
                properties_count += 1
    
    return (classes_count, properties_count)
