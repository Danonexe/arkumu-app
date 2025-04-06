from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from django.db import models
import datetime

def validate_cidoc_class(entity_class, declared_class):
    """
    Validates that an entity's class is valid within CIDOC-CRM hierarchy.
    
    Args:
        entity_class: CIDOCClass instance of the entity
        declared_class: str class_id (e.g., 'E22_Human-Made_Object')
    """
    if not entity_class:
        raise ValidationError(_('Entity must have a CIDOC-CRM class'))
        
    # Check direct match
    if entity_class.class_id != declared_class:
        # Check parent classes
        valid_parents = entity_class.parent_classes.all()
        if not any(p.class_id == declared_class for p in valid_parents):
            raise ValidationError(
                _(f'Invalid CIDOC class. Entity of type {entity_class.class_id} '
                  f'cannot be used as {declared_class}')
            )

def validate_property_domain_range(property_def, source_class, target_class=None, value=None):
    """
    Validates property domain/range constraints.
    
    Args:
        property_def: CIDOCProperty instance
        source_class: CIDOCClass instance of the entity
        target_class: CIDOCClass instance for relationship properties
        value: The property value for primitive properties
    """
    # Validate domain
    if not property_def.domain_class:
        return
        
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
    
    # For relationship properties with a range class, validate target class
    if property_def.range_class and target_class:
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
    # If property has a range class but target_class is None, it's missing
    elif property_def.range_class and not target_class:
        raise ValidationError(_('Target class required for relationship property'))

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
        class_id: str class identifier (e.g., 'E22_Human-Made_Object')
    """
    from .schema import CIDOCClass
    
    if not class_id:
        raise ValidationError(_('Entity must have a CIDOC-CRM class'))
        
    try:
        CIDOCClass.objects.get(class_id=class_id)
    except ObjectDoesNotExist:
        raise ValidationError(_(f'Invalid CIDOC-CRM class: {class_id}'))

def validate_cidoc_relationship(property_id, source_class, target_class):
    """
    Validates that a property is a valid CIDOC-CRM relationship between classes.
    
    Args:
        property_id: str property identifier (e.g., 'P1_is_identified_by')
        source_class: str source class identifier
        target_class: str target class identifier
    """
    from .schema import CIDOCProperty, CIDOCClass
    
    if not property_id:
        raise ValidationError(_('Relationship must have a CIDOC-CRM property'))
        
    try:
        property_def = CIDOCProperty.objects.get(property_id=property_id)
    except ObjectDoesNotExist:
        raise ValidationError(_(f'Invalid CIDOC-CRM property: {property_id}'))
        
    try:
        # Validate domain
        if property_def.domain_class:
            validate_cidoc_class(
                CIDOCClass.objects.get(class_id=source_class),
                property_def.domain_class.class_id
            )
            
        # Validate range
        if property_def.range_class:
            validate_cidoc_class(
                CIDOCClass.objects.get(class_id=target_class),
                property_def.range_class.class_id
            )
            
    except ObjectDoesNotExist:
        raise ValidationError(_(f'Invalid CIDOC-CRM class in relationship')) 