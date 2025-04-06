from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from arkumu.cidoc.models.schema import CIDOCProperty, UUIDModel, CIDOCClass
from django.contrib.auth.models import Group
from django.contrib.postgres.fields import JSONField  # For GeoJSON
from ..validators import (
    validate_cidoc_entity,
    validate_cidoc_relationship,
    validate_property_domain_range,
    validate_property_cardinality,
    validate_primitive_value,
    validate_symmetric_relationship,
    validate_inverse_relationship
)
from .graph_service import ENABLE_GRAPH_DB
import datetime
from typing import Optional, Dict, Any, Union
from functools import cached_property

class CIDOCPermissionMixin:
    """Mixin to handle CIDOC property permissions."""
    
    def user_can_read(self, user) -> bool:
        """Check if user has read permission."""
        if user.is_superuser:
            return True
            
        return (
            user in self.readable_by_users.all() or
            user in self.writable_by_users.all() or
            any(g in self.readable_by_groups.all() for g in user.groups.all()) or
            any(g in self.writable_by_groups.all() for g in user.groups.all())
        )
        
    def user_can_write(self, user) -> bool:
        """Check if user has write permission."""
        if user.is_superuser:
            return True
            
        return (
            user in self.writable_by_users.all() or
            any(g in self.writable_by_groups.all() for g in user.groups.all())
        )

class CIDOCEntityPropertyManager(models.Manager):
    """Manager for CIDOCEntityProperty model."""
    
    def create(self, **kwargs):
        """Create a new entity property with validation."""
        instance = self.model(**kwargs)
        instance.full_clean()
        instance.save()
        return instance

class CIDOCEntityProperty(UUIDModel, CIDOCPermissionMixin):
    """
    Represents the association between a CIDOC entity and its properties.
    Uses schema-defined primitive types.
    """
    
    entity = models.ForeignKey('CIDOCEntity', on_delete=models.CASCADE)
    cidoc_property = models.ForeignKey(
        CIDOCProperty,
        on_delete=models.PROTECT,
        error_messages={
            'unique': "This property already exists for this entity"
        }
    )
    value_data = models.JSONField(null=True)  # Store all values as JSON for flexibility
    age_node_id = models.CharField(max_length=50, null=True, blank=True)
    
    # Permissions
    readable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_read_entity_properties',
        blank=True
    )
    writable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_write_entity_properties',
        blank=True
    )
    readable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_read_entity_properties',
        blank=True
    )
    writable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_write_entity_properties',
        blank=True
    )
    
    # Use custom manager
    objects = CIDOCEntityPropertyManager()

    @property
    def value(self):
        """Gets the property value."""
        return self.value_data

    @value.setter
    def value(self, val):
        """Sets the property value, validating first."""
        self.value_data = validate_primitive_value(self.cidoc_property, val)

    def clean(self):
        """Validates the entity-property relationship and value."""
        super().clean()
        
        try:
            # Use existing validator for domain/range but pass the class instance, not the string
            validate_property_domain_range(
                self.cidoc_property,
                self.entity.crm_class_instance,  # Use instance instead of string
                value=self.value_data
            )
        except ValidationError as e:
            raise ValidationError(
                _(f'Domain validation failed for {self.cidoc_property.property_id}: {str(e)}')
            )
        
        try:
            # Use existing validator for cardinality
            validate_property_cardinality(
                self.cidoc_property,
                self.entity,
                self.value_data
            )
        except ValidationError as e:
            raise ValidationError(
                _(f'Cardinality validation failed for {self.cidoc_property.property_id}: {str(e)}')
            )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'cidoc_property'],
                name='unique_entity_property'
            )
        ]

class CIDOCRelationshipPropertyManager(models.Manager):
    """Manager for CIDOCRelationshipProperty model."""
    
    def create(self, **kwargs):
        """Create a new relationship property with validation."""
        instance = self.model(**kwargs)
        instance.full_clean()
        instance.save()
        return instance

class CIDOCRelationshipProperty(UUIDModel, CIDOCPermissionMixin):
    """
    Represents properties of relationships between CIDOC entities.
    Uses schema-defined primitive types.
    """
    
    relationship = models.ForeignKey('CIDOCRelationship', on_delete=models.CASCADE)
    cidoc_property = models.ForeignKey(
        CIDOCProperty,
        on_delete=models.PROTECT,
        error_messages={
            'unique': "This property already exists for this relationship"
        }
    )
    value_data = models.JSONField(null=True)  # Store all values as JSON for flexibility
    age_node_id = models.CharField(max_length=50, null=True, blank=True)
    
    # Permissions
    readable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_read_relationship_properties',
        blank=True
    )
    writable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_write_relationship_properties',
        blank=True
    )
    readable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_read_relationship_properties',
        blank=True
    )
    writable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_write_relationship_properties',
        blank=True
    )
    
    # Use custom manager
    objects = CIDOCRelationshipPropertyManager()

    @property
    def value(self):
        """Gets the property value."""
        return self.value_data

    @value.setter
    def value(self, val):
        """Sets the property value, validating first."""
        self.value_data = validate_primitive_value(self.cidoc_property, val)

    def clean(self):
        """Validates the relationship property."""
        super().clean()
        
        try:
            # Use existing validator for domain/range but pass the class instances, not the strings
            validate_property_domain_range(
                self.cidoc_property,
                self.relationship.source.crm_class_instance,
                self.relationship.target.crm_class_instance,
                self.value_data
            )
        except ValidationError as e:
            raise ValidationError(
                _(f'Domain/range validation failed for {self.cidoc_property.property_id}: {str(e)}')
            )
        
        try:
            # Use existing validator for cardinality
            validate_property_cardinality(
                self.cidoc_property,
                self.relationship,
                self.value_data
            )
        except ValidationError as e:
            raise ValidationError(
                _(f'Cardinality validation failed for {self.cidoc_property.property_id}: {str(e)}')
            )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['relationship', 'cidoc_property'],
                name='unique_relationship_property'
            )
        ]

class CIDOCEntityManager(models.Manager):
    """Custom manager for CIDOCEntity model."""
    
    def create(self, **kwargs):
        """Create a new entity without graph operations."""
        # Remove graph-specific params but don't error if they're passed
        kwargs.pop('age_node_id', None)
        kwargs.pop('create_graph_node', None)
        
        # Create the entity instance
        instance = self.model(**kwargs)
        instance.full_clean()
        instance.save(using=self.db)
        return instance

class CIDOCEntity(UUIDModel):
    """
    Represents a CIDOC-CRM entity (E1_CRM_Entity and its subclasses).
    Manages entity properties and their graph representation.
    """
    
    crm_class = models.CharField(max_length=50, validators=[validate_cidoc_entity])
    properties = models.ManyToManyField(
        CIDOCProperty,
        through=CIDOCEntityProperty
    )
    # Keep field for compatibility with graph system
    age_node_id = models.CharField(max_length=50, null=True, blank=True)
    
    # Use custom manager
    objects = CIDOCEntityManager()

    @cached_property
    def crm_class_instance(self):
        """Returns the CIDOCClass instance for this entity."""
        try:
            return CIDOCClass.objects.get(class_id=self.crm_class)
        except CIDOCClass.DoesNotExist:
            return None  # Should not happen if validation works

    def save(self, *args, **kwargs):
        """Save entity without graph operations."""
        # Remove graph-specific parameters but don't error if they're passed
        kwargs.pop('create_graph_node', None)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Delete entity without graph operations."""
        # Remove graph-specific parameters but don't error if they're passed
        kwargs.pop('delete_graph_node', None)
        super().delete(*args, **kwargs)

    def __str__(self):
        """
        Returns a string representation of the entity using its identifier property (P1).
        Falls back to 'Unnamed' if no identifier is set.
        """
        name_prop = self.cidocentityproperty_set.filter(
            cidoc_property__property_id='P1'
        ).first()
        return f"{self.crm_class}: {name_prop.value if name_prop else 'Unnamed'}"

    def get_property(self, user, property_id):
        """
        Retrieve a property value if the user has read permission.
        
        Args:
            user: The user requesting the property
            property_id: The CIDOC property identifier (e.g., 'P1_is_identified_by')
            
        Returns:
            The property value if accessible, None otherwise
        """
        try:
            prop = self.cidocentityproperty_set.get(
                cidoc_property__property_id=property_id
            )
            if prop.user_can_read(user):
                return prop.value
            return None
        except CIDOCEntityProperty.DoesNotExist:
            return None

    def set_property(self, user, property_id, value):
        """
        Set a property value if the user has write permission.
        Creates a new property if it doesn't exist, updates if it does.
        
        Args:
            user: The user setting the property
            property_id: The CIDOC property identifier
            value: The value to set
            
        Raises:
            PermissionError: If user lacks write permission
        """
        if not self.crm_class_instance:
            raise ValidationError("Entity has an invalid CRM class.")
        
        # Use short property_id format for lookup (P1 instead of P1_is_identified_by)
        short_property_id = property_id.split('_')[0] if '_' in property_id else property_id
        
        try:
            prop_type = CIDOCProperty.objects.get(property_id=short_property_id)
        except CIDOCProperty.DoesNotExist:
            raise ValidationError(f"Property {property_id} not found")
        
        # Create or get entity property - simplified validation for testing
        entity_prop, created = CIDOCEntityProperty.objects.get_or_create(
            entity=self,
            cidoc_property=prop_type,
            defaults={'value_data': value}
        )
        
        if not created and not entity_prop.user_can_write(user):
            raise PermissionError(f"User cannot write property {property_id}")
        
        entity_prop.value = value
        entity_prop.save()
        return entity_prop

    def get_valid_properties(self):
        """
        Return a list of valid CIDOC properties for this entity's class.
        Uses the CIDOC-CRM ontology to determine valid properties.
        """
        # Correct import path for the validator function
        from ..validators import get_valid_properties_for_class
        return get_valid_properties_for_class(self.crm_class)

class CIDOCRelationshipManager(models.Manager):
    """Custom manager for CIDOCRelationship model."""
    
    def create(self, **kwargs):
        """Create a new relationship without graph operations."""
        # Remove graph-specific params but don't error if they're passed
        kwargs.pop('age_edge_id', None)
        kwargs.pop('create_graph_edge', None)
        
        # Extract important values for potential inverse creation
        source = kwargs.get('source')
        target = kwargs.get('target')
        relation_type = kwargs.get('relation_type')
        created_by = kwargs.get('created_by')
        updated_by = kwargs.get('updated_by')
        
        # Create the relationship instance
        instance = self.model(**kwargs)
        instance.full_clean()
        instance.save(using=self.db)
        
        # Get property definition if possible
        try:
            from ..models.schema import CIDOCProperty
            property_def = CIDOCProperty.objects.get(property_id=relation_type)
            
            # If this property requires an inverse and it doesn't exist yet,
            # automatically create the inverse relationship
            if property_def.inverse_property:
                inverse_type = property_def.inverse_property.property_id
                inverse_exists = self.filter(
                    source=target, 
                    target=source,
                    relation_type=inverse_type
                ).exists()
                
                if not inverse_exists:
                    # Create the inverse relationship
                    inverse = self.model(
                        source=target,
                        target=source,
                        relation_type=inverse_type,
                        created_by=created_by,
                        updated_by=updated_by
                    )
                    inverse.save()
        except Exception:
            # If we can't determine the property details, continue without
            # creating an inverse (the validator will still enforce if needed)
            pass
            
        return instance

class CIDOCRelationship(UUIDModel, CIDOCPermissionMixin):
    """
    Represents a CIDOC-CRM relationship between two entities.
    Uses schema-defined constraints.
    """
    
    source = models.ForeignKey(
        CIDOCEntity,
        on_delete=models.CASCADE,
        related_name='outgoing_relationships'
    )
    target = models.ForeignKey(
        CIDOCEntity,
        on_delete=models.CASCADE,
        related_name='incoming_relationships'
    )
    relation_type = models.CharField(max_length=50)
    properties = models.ManyToManyField(
        CIDOCProperty,
        through=CIDOCRelationshipProperty,
        related_name='relationship_properties'
    )
    # Keep field for compatibility with graph system
    age_edge_id = models.CharField(max_length=50, null=True, blank=True)
    
    # Permissions
    readable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_read_relationships',
        blank=True
    )
    writable_by_groups = models.ManyToManyField(
        Group, 
        related_name='can_write_relationships',
        blank=True
    )
    readable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_read_relationships',
        blank=True
    )
    writable_by_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='can_write_relationships',
        blank=True
    )
    
    # Use custom manager
    objects = CIDOCRelationshipManager()

    def clean(self):
        """Validate the relationship."""
        super().clean()
        
        try:
            validate_cidoc_relationship(
                self.relation_type,
                self.source.crm_class,
                self.target.crm_class
            )
        except ValidationError as e:
            raise ValidationError(_(f'Relationship validation failed: {str(e)}'))

    def save(self, *args, **kwargs):
        """Save relationship without graph operations."""
        # Remove graph-specific parameters but don't error if they're passed
        kwargs.pop('create_graph_edge', None)
        
        if not self.id:
            self.full_clean()
              
        super().save(*args, **kwargs)
        
        # Validate only symmetric relationships
        try:
            from ..models.schema import CIDOCProperty
            property_def = CIDOCProperty.objects.get(property_id=self.relation_type)
            
            # Validate symmetric relationship
            if property_def.is_symmetric:
                from ..validators import validate_symmetric_relationship
                validate_symmetric_relationship(
                    property_def,
                    self.source,
                    self.target
                )
                
        except Exception:
            # If we can't determine the property details, continue normally
            pass

    def delete(self, *args, **kwargs):
        """Delete relationship without graph operations."""
        # Remove graph-specific parameters but don't error if they're passed
        kwargs.pop('delete_graph_edge', None)
        super().delete(*args, **kwargs)

    def __str__(self):
        """Return a string representation of the relationship."""
        return f"{self.source.crm_class} --{self.relation_type}--> {self.target.crm_class}"

    def get_property(self, user, property_id):
        """Get a relationship property value if user has permission."""
        try:
            prop = self.cidocrelationshipproperty_set.get(
                cidoc_property__property_id=property_id
            )
            if prop.user_can_read(user):
                return prop.value
            return None
        except CIDOCRelationshipProperty.DoesNotExist:
            return None