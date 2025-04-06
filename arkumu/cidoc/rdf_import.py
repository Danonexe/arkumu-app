import rdflib
from django.db import transaction
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
import re

def extract_id(uri_or_str, pattern=r'(P\d+[i]?)'):
    """
    Extract ID from a URI or string based on the given pattern.
    
    Args:
        uri_or_str (str): URI or string containing the ID
        pattern (str): Regex pattern to extract the ID
        
    Returns:
        str: Extracted ID or original string if no match is found
    """
    # Get the last part of the URI
    name_part = str(uri_or_str).split('/')[-1]
    
    # Check for inverse property pattern (Pi)
    inverse_match = re.match(r'(P\d+)i_', name_part)
    if inverse_match:
        return f"{inverse_match.group(1)}i"
    
    # Standard property (P)
    match = re.match(r'(P\d+)_', name_part)
    if match:
        return match.group(1)
    
    # Fallback - just use the last part of the URI
    return name_part

def get_special_property_description(prop_id):
    """
    Generate a description for special properties based on their ID.
    
    Args:
        prop_id (str): Property ID like P81a_end_of_the_begin
        
    Returns:
        str: A generated description or empty string if not a special property
    """
    # Handle time qualifier properties
    special_descriptions = {
        'P81a_end_of_the_begin': 'The latest date that can be assigned to the beginning of an event or activity.',
        'P81b_begin_of_the_end': 'The earliest date that can be assigned to the end of an event or activity.',
        'P82a_begin_of_the_begin': 'The earliest date that can be assigned to the beginning of an event or activity.',
        'P82b_end_of_the_end': 'The latest date that can be assigned to the end of an event or activity.',
        'P90a_has_lower_value_limit': 'The lower limit of a dimension range.',
        'P90b_has_upper_value_limit': 'The upper limit of a dimension range.'
    }
    
    return special_descriptions.get(prop_id, '')

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
    OWL = rdflib.namespace.OWL
    CIDOC = rdflib.Namespace(namespace)
    
    # Track counts
    classes_count = 0
    properties_count = 0
    
    # First pass: Import all classes
    class_map = {}  # Maps URIs to CIDOCClass instances
    
    for class_uri in g.subjects(RDF.type, RDFS.Class):
        if str(class_uri).startswith(namespace):
            # Extract class ID from URI - handle different formats
            full_id = str(class_uri).split('/')[-1]
            # Normalize class ID - extract E1, E21, etc.
            # If the format is like E1_CRM_Entity, get just E1
            match = re.match(r'(E\d+)', full_id)
            if match:
                class_id = match.group(1)
            else:
                class_id = full_id
                
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
                print(f"Created class: {class_id}")
    
    # Second pass: Set up class hierarchy
    for class_uri, cidoc_class in class_map.items():
        for parent in g.objects(class_uri, RDFS.subClassOf):
            if parent in class_map:
                cidoc_class.parent_classes.add(class_map[parent])
    
    # Import properties and store mapping of URIs to property instances
    property_map = {}  # Maps URIs to CIDOCProperty instances
    
    # Store mappings from base property IDs to their descriptions
    # This will help us fill in descriptions for inverse properties
    property_descriptions = {}
    
    for prop_uri in g.subjects(RDF.type, RDF.Property):
        if str(prop_uri).startswith(namespace):
            # Extract property ID with proper handling of inverse properties
            full_id = str(prop_uri).split('/')[-1]
            prop_id = extract_id(full_id)
                
            label = g.value(prop_uri, RDFS.label, None)
            comment = g.value(prop_uri, RDFS.comment, None)
            domain = g.value(prop_uri, RDFS.domain, None)
            range_class = g.value(prop_uri, RDFS.range, None)
            
            # Save descriptions for base properties to help with inverse properties
            if comment and re.match(r'^P\d+$', prop_id):
                property_descriptions[prop_id] = str(comment)
            
            # Get domain and range classes
            domain_class = None
            if domain in class_map:
                domain_class = class_map[domain]
            
            range_obj = None
            if range_class in class_map:
                range_obj = class_map[range_class]
            
            # Check for symmetric properties
            is_symmetric = False
            is_transitive = False
            for _, pred, obj in g.triples((prop_uri, None, None)):
                if pred == RDF.type and obj == OWL.SymmetricProperty:
                    is_symmetric = True
                if pred == RDF.type and obj == OWL.TransitiveProperty:
                    is_transitive = True
            
            # For inverse properties (ending with "i"), use the description from the base property if available
            description = str(comment) if comment else ''
            
            # Check for special property descriptions
            if not description and '_' in prop_id:
                # This is a special property like P81a_end_of_the_begin
                description = get_special_property_description(prop_id)
                
                # If still no description, try to derive from the base property
                if not description:
                    base_match = re.match(r'(P\d+)', prop_id)
                    if base_match:
                        base_prop_id = base_match.group(1)
                        if base_prop_id in property_descriptions:
                            description = f"Specialized version of {base_prop_id}: {property_descriptions[base_prop_id]}"
            
            # For inverse properties
            if not description and prop_id.endswith('i'):
                base_prop_id = prop_id[:-1]  # Remove the 'i' to get the base property ID
                if base_prop_id in property_descriptions:
                    base_desc = property_descriptions[base_prop_id]
                    # Create an inverse description
                    description = f"Inverse of {base_prop_id}: {base_desc}"
                    if not label:
                        # Generate an inverse label too if needed
                        base_label = CIDOCProperty.objects.filter(property_id=base_prop_id).first()
                        if base_label and base_label.label:
                            label = f"inverse of ({base_label.label})"
            
            # Create property
            cidoc_property, created = CIDOCProperty.objects.get_or_create(
                property_id=prop_id,
                defaults={
                    'label': str(label) if label else prop_id,
                    'description': description,
                    'domain_class': domain_class,
                    'range_class': range_obj,
                    'is_symmetric': is_symmetric,
                    'is_transitive': is_transitive
                }
            )
            
            # Store in property map for later inverse linking
            property_map[prop_uri] = cidoc_property
            
            if created:
                properties_count += 1
                print(f"Created property: {prop_id}")
    
    # Third pass: Set up inverse properties
    inverse_count = 0
    # Collect all inverse pairs first to ensure we have a complete set
    inverse_pairs = []
    for prop_uri, cidoc_property in property_map.items():
        # Look for inverse property relationships
        for _, _, inverse_uri in g.triples((prop_uri, OWL.inverseOf, None)):
            if inverse_uri in property_map:
                inverse_prop = property_map[inverse_uri]
                # Only link if they're different properties
                if cidoc_property.id != inverse_prop.id:
                    inverse_pairs.append((cidoc_property, inverse_prop))
    
    # Now link all inverse properties bidirectionally
    for prop, inverse_prop in inverse_pairs:
        # Set the inverse relationship in both directions
        prop.inverse_property = inverse_prop
        prop.save()
        
        inverse_prop.inverse_property = prop
        inverse_prop.save()
        
        # Ensure inverse properties have descriptions
        if not inverse_prop.description and prop.description:
            inverse_prop.description = f"Inverse of {prop.property_id}: {prop.description}"
            inverse_prop.save()
        
        inverse_count += 1
        print(f"Linked inverse: {prop.property_id} -> {inverse_prop.property_id}")
    
    # Final pass: Check for any properties without descriptions and generate defaults
    for prop in CIDOCProperty.objects.filter(description=''):
        prop_id = prop.property_id
        
        # For special properties
        if '_' in prop_id:
            description = get_special_property_description(prop_id)
            if description:
                prop.description = description
                prop.save()
                continue
                
        # For inverse properties without descriptions
        if prop_id.endswith('i'):
            base_prop_id = prop_id[:-1]
            base_prop = CIDOCProperty.objects.filter(property_id=base_prop_id).first()
            if base_prop and base_prop.description:
                prop.description = f"Inverse of {base_prop_id}: {base_prop.description}"
                prop.save()
                continue
        
        # For all others, provide a default description
        if not prop.description:
            prop.description = f"CIDOC-CRM property {prop_id}"
            prop.save()
    
    # Count the actual number of bidirectional links established
    bidirectional_count = 0
    for prop in CIDOCProperty.objects.filter(property_id__regex=r'^P\d+$'):
        if prop.inverse_property and prop.inverse_property.inverse_property == prop:
            bidirectional_count += 1
    
    print(f"Verified {bidirectional_count} bidirectional inverse property relationships")
    print(f"Established {inverse_count} inverse property relationships")
    
    return (classes_count, properties_count)
