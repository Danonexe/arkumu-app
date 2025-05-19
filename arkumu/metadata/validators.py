from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
import datetime

def validate_cidoc_class(entity_class, declared_class):
    """
    Validates that an entity's class is valid within CIDOC-CRM hierarchy.
    
    Args:
        entity_class: CIDOCClass instance or str class ID of the entity
        declared_class: str class_id (e.g., 'E22')
    """
    from .models.cidoc import CIDOCClass
    
    if not entity_class:
        raise ValidationError(_('Entity must have a CIDOC-CRM class'))
    
    # Convert entity_class to instance if it's a string
    if isinstance(entity_class, str):
        entity_class_id = entity_class.split('_')[0] if '_' in entity_class else entity_class
        try:
            entity_class = CIDOCClass.objects.get(class_id=entity_class_id)
        except CIDOCClass.DoesNotExist:
            raise ValidationError(_(f'Invalid entity class: {entity_class}'))
    
    # Also get short form of declared_class if needed
    declared_class_id = declared_class.split('_')[0] if '_' in declared_class else declared_class
        
    # Check direct match
    if entity_class.class_id == declared_class_id:
        return
        
    # Check parent classes
    valid_parents = entity_class.parent_classes.all()
    if not any(p.class_id == declared_class_id for p in valid_parents):
        raise ValidationError(
            _(f'Invalid CIDOC class. Entity of type {entity_class.class_id} '
              f'cannot be used as {declared_class_id}')
        )

def validate_property_domain_range(property_def, source_class, target_class=None, value=None):
    """
    Validates property domain/range constraints.
    
    Args:
        property_def: CIDOCProperty instance
        source_class: CIDOCClass instance or str class ID of the entity
        target_class: CIDOCClass instance or str class ID for relationship properties
        value: The property value for primitive properties
    """
    from .models.cidoc import CIDOCClass
    
    # Validate domain
    if not property_def.domain_class:
        return
    
    # Convert source_class to instance if it's a string
    if isinstance(source_class, str):
        source_class_id = source_class.split('_')[0] if '_' in source_class else source_class
        try:
            source_class = CIDOCClass.objects.get(class_id=source_class_id)
        except CIDOCClass.DoesNotExist:
            raise ValidationError(_(f'Invalid source class: {source_class}'))
        
    # Convert target_class to instance if it's a string
    if target_class and isinstance(target_class, str):
        target_class_id = target_class.split('_')[0] if '_' in target_class else target_class
        try:
            target_class = CIDOCClass.objects.get(class_id=target_class_id)
        except CIDOCClass.DoesNotExist:
            raise ValidationError(_(f'Invalid target class: {target_class}'))
    
    valid_domain = False
    domain_class = property_def.domain_class
    
    # Check direct match or parent classes
    if (source_class.class_id == domain_class.class_id or
            domain_class in source_class.parent_classes.all()):
        valid_domain = True
            
    if not valid_domain:
        raise ValidationError(
            _(f'Invalid property domain. {property_def.property_id} requires '
              f'domain class {domain_class.class_id}')
        )
    
    # Determine if this is a data property or an object property
    # Data properties have primitive range classes or are used to store values
    # Object properties link entities and require a target class
    is_data_property = (
        # Has a value provided (data properties have values)
        value is not None or
        # Has a primitive range class
        (property_def.range_class and getattr(property_def.range_class, 'is_primitive', False)) or
        # Range class is a string or literal type (check common naming patterns)
        (property_def.range_class and any(
            literal_type in property_def.range_class.class_id 
            for literal_type in ['String', 'Number', 'Time', 'Primitive', 'Literal']
        ))
    )
    
    # Object properties require a target class, data properties don't
    if is_data_property:
        return
        
    # For object properties (relationship properties), validate the target class
    if property_def.range_class:
        # If it's an object property but no target class is provided, that's an error
        if not target_class:
            raise ValidationError(_('Target class required for relationship property'))
            
        valid_range = False
        range_class = property_def.range_class
        
        if (target_class.class_id == range_class.class_id or
                range_class in target_class.parent_classes.all()):
            valid_range = True
                
        if not valid_range:
            raise ValidationError(
                _(f'Invalid property range. {property_def.property_id} requires '
                  f'range class {range_class.class_id}')
            )

def validate_property_cardinality(property_def, entity, new_value=None):
    """
    Validates property cardinality constraints.
    
    Args:
        property_def: CIDOCProperty instance
        entity: CIDOCEntity instance
        new_value: Optional new value being added
    """
    if property_def.is_functional:
        existing = entity.cidocentityproperty_set.filter(
            property=property_def
        ).exists()
        
        if existing and new_value:
            raise ValidationError(
                _(f'Property {property_def.property_id} can have at most one value')
            )

def validate_inverse_relationship(property_def, source_entity, target_entity):
    """
    Validates and ensures inverse relationship consistency.
    
    Args:
        property_def: CIDOCProperty instance
        source_entity: CIDOCEntity source instance
        target_entity: CIDOCEntity target instance
    """
    if property_def.inverse_property:
        # Check if inverse already exists
        inverse_exists = source_entity.incoming_relationships.filter(
            source=target_entity,
            relation_type=property_def.inverse_property.property_id
        ).exists()
        
        if not inverse_exists:
            raise ValidationError(
                _(f'Missing inverse relationship {property_def.inverse_property.property_id} '
                  f'for {property_def.property_id}')
            )

def validate_symmetric_relationship(property_def, source_entity, target_entity):
    """
    Validates symmetric relationship consistency.
    
    Args:
        property_def: CIDOCProperty instance
        source_entity: CIDOCEntity source instance
        target_entity: CIDOCEntity target instance
    """
    if property_def.is_symmetric:
        # Check if symmetric relationship exists
        symmetric_exists = source_entity.incoming_relationships.filter(
            source=target_entity,
            relation_type=property_def.property_id
        ).exists()
        
        if not symmetric_exists:
            raise ValidationError(
                _(f'Missing symmetric relationship for {property_def.property_id}')
            )

def validate_primitive_value(property_def, value):
    """
    Validates values for primitive property types.
    
    Args:
        property_def: CIDOCProperty instance
        value: The value to validate
        
    Returns:
        The validated value
        
    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None
        
    if not property_def.range_class or not property_def.range_class.is_primitive:
        return value
        
    # Add specific validation logic for different primitive types
    range_class_id = property_def.range_class.class_id
    
    if range_class_id == 'E60_Number':
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValidationError(_('Value must be a number'))
            
    elif range_class_id == 'E61_Time_Primitive':
        try:
            if isinstance(value, (datetime.date, datetime.datetime)):
                return value
            if isinstance(value, str):
                if 'T' in value:
                    return datetime.datetime.fromisoformat(value)
                return datetime.date.fromisoformat(value)
            raise ValidationError(_('Invalid date/time format'))
        except (TypeError, ValueError):
            raise ValidationError(_('Value must be a valid date/time in ISO format'))
            
    elif range_class_id == 'E95_Spacetime_Primitive':
        if not isinstance(value, dict):
            raise ValidationError(_('Spacetime primitive must be a valid GeoJSON object'))
        return value
        
    # For E62_String and other primitives, just return the string value
    return str(value)

def validate_cidoc_entity(class_id):
    """
    Validates that a class ID is a valid CIDOC-CRM entity class.
    
    Args:
        class_id: str class identifier (e.g., 'E22')
    """
    from .models.cidoc import CIDOCClass
    
    if not class_id:
        raise ValidationError(_('Entity must have a CIDOC-CRM class'))
    
    # Extract short class ID if needed (E21 from E21_Person)
    short_class_id = class_id.split('_')[0] if '_' in class_id else class_id
    
    try:
        # Always use the short ID format for lookups
        CIDOCClass.objects.get(class_id=short_class_id)
    except ObjectDoesNotExist:
        raise ValidationError(_(f'Invalid CIDOC-CRM class: {class_id}'))

def validate_cidoc_relationship(property_id, source_class, target_class):
    """
    Validates that a property is a valid CIDOC-CRM relationship between classes.
    
    Args:
        property_id: str property identifier (e.g., 'P1')
        source_class: str or CIDOCClass instance of source
        target_class: str or CIDOCClass instance of target
    """
    from .models.cidoc import CIDOCProperty, CIDOCClass
    
    if not property_id:
        raise ValidationError(_('Relationship must have a CIDOC-CRM property'))
    
    # Use short property ID format
    short_property_id = property_id.split('_')[0] if '_' in property_id else property_id
    
    try:
        property_def = CIDOCProperty.objects.get(property_id=short_property_id)
    except ObjectDoesNotExist:
        raise ValidationError(_(f'Invalid CIDOC-CRM property: {property_id}'))
    
    # Handle source_class as string or instance
    if isinstance(source_class, str):
        source_class_id = source_class.split('_')[0] if '_' in source_class else source_class
        try:
            source_class = CIDOCClass.objects.get(class_id=source_class_id)
        except ObjectDoesNotExist:
            # Use original error message format for test compatibility
            raise ValidationError(_(f'Invalid CIDOC-CRM class: {source_class}'))
    
    # Handle target_class as string or instance
    if isinstance(target_class, str):
        target_class_id = target_class.split('_')[0] if '_' in target_class else target_class
        try:
            target_class = CIDOCClass.objects.get(class_id=target_class_id)
        except ObjectDoesNotExist:
            # Use original error message format for test compatibility
            raise ValidationError(_(f'Invalid CIDOC-CRM class: {target_class}'))
    
    # Validate domain
    if property_def.domain_class:
        validate_cidoc_class(source_class, property_def.domain_class.class_id)
        
    # Validate range
    if property_def.range_class:
        validate_cidoc_class(target_class, property_def.range_class.class_id)

def get_valid_properties_for_class(class_id):
    """
    Returns a list of CIDOCProperty instances valid for a given class ID.
    Considers domain constraints and inheritance.
    
    Args:
        class_id: str class identifier (e.g., 'E22')
        
    Returns:
        List[CIDOCProperty]: List of valid properties
    """
    from .models.cidoc import CIDOCClass, CIDOCProperty
    
    # Always use short class ID format (E21 not E21_Person)
    short_class_id = class_id.split('_')[0] if '_' in class_id else class_id
    
    try:
        cidoc_class = CIDOCClass.objects.get(class_id=short_class_id)
        
        # Get all properties where this class is in the domain
        valid_properties = list(CIDOCProperty.objects.filter(domain_class=cidoc_class))
        
        # Get properties from parent classes recursively
        parent_classes = cidoc_class.parent_classes.all()
        for parent in parent_classes:
            parent_properties = get_valid_properties_for_class(parent.class_id)
            valid_properties.extend(parent_properties)
        
        # Remove duplicates by creating a dict with property_id as keys
        property_dict = {prop.property_id: prop for prop in valid_properties}
        return list(property_dict.values())
        
    except CIDOCClass.DoesNotExist:
        return []  # Return empty list if class not found 

def validate_value_for_range(value_data, range_class):
    """
    Validates that a JSON value_data field conforms to the CIDOC-CRM range class constraints.
    
    Args:
        value_data: Dict containing JSON data for a literal value
        range_class: CIDOCClass instance representing the range type
    
    Raises:
        ValidationError: If validation fails
    """
    if not value_data:
        return  # Allow empty values
        
    if not range_class:
        return  # No validation if no range class
    
    # For consistency, we expect value_data to have a 'value' key
    if not isinstance(value_data, dict) or 'value' not in value_data:
        raise ValidationError(_('Literal values must have a "value" field'))
        
    # Extract the actual value to validate
    value = value_data['value']
    
    # For primitive literals, validate based on the class type
    range_class_id = range_class.class_id.lower()
    
    # Number validation
    if 'number' in range_class_id or range_class_id == 'e60':
        try:
            float(value)  # Just check if convertible to float
        except (ValueError, TypeError):
            raise ValidationError(_('Value must be a number'))
            
    # Date/time validation
    elif 'time' in range_class_id or 'date' in range_class_id or range_class_id == 'e61':
        if not isinstance(value, str):
            raise ValidationError(_('Date/time values must be strings in ISO format'))
            
        try:
            # Try to parse it - we don't save the result, just verify it's valid
            if 'T' in value:
                datetime.datetime.fromisoformat(value)
            else:
                datetime.date.fromisoformat(value)
        except ValueError:
            raise ValidationError(_('Invalid date/time format'))
            
    # GeoJSON validation
    elif 'spacetime' in range_class_id or 'geo' in range_class_id or range_class_id == 'e95':
        if not isinstance(value, dict):
            raise ValidationError(_('Spacetime/Geo data must be a valid GeoJSON object'))
        
        # Basic check for GeoJSON structure
        if 'type' not in value:
            raise ValidationError(_('GeoJSON must have a "type" field'))
    
    # For string literals or other types, no special validation needed
    return 