from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from arkumu.cidoc.models.schema import CIDOCProperty, CIDOCGraph, UUIDModel
from django.contrib.auth.models import Group
from django.contrib.postgres.fields import JSONField  # For GeoJSON
from .validators import (
    validate_cidoc_entity,
    validate_cidoc_relationship,
    validate_property_domain_range,
    validate_property_cardinality,
    validate_primitive_value,
    validate_symmetric_relationship,
    validate_inverse_relationship
)
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

class GraphManager:
    """
    Dedicated manager for graph operations, separating graph concerns from model operations.
    Handles creation, updates, and deletion of nodes and edges in the graph database.
    """
    
    def __init__(self):
        self.graph = CIDOCGraph()
    
    def create_entity_node(self, crm_class: str, properties: Dict[str, Any]) -> str:
        """Creates a node for an entity and returns its ID."""
        return self.graph.create_entity(crm_class, properties)
        
    def create_relationship_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Dict[str, Any]
    ) -> str:
        """Creates an edge for a relationship and returns its ID."""
        return self.graph.create_relationship(
            source_id,
            target_id,
            relation_type,
            properties
        )
        
    def update_node_properties(self, node_id: str, properties: Dict[str, Any]) -> bool:
        """Updates properties of an existing node."""
        return self.graph.update_node(node_id, properties)
        
    def update_edge_properties(self, edge_id: str, properties: Dict[str, Any]) -> bool:
        """Updates properties of an existing edge."""
        return self.graph.update_edge(edge_id, properties)
        
    def delete_node(self, node_id: str) -> None:
        """Deletes a node and its associated edges."""
        self.graph.delete_node(node_id)
        
    def delete_edge(self, edge_id: str) -> None:
        """Deletes an edge from the graph."""
        self.graph.delete_edge(edge_id)

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
    age_node_id = models.CharField(max_length=50, null=True)
    
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
            # Use existing validator for domain/range
            validate_property_domain_range(
                self.cidoc_property,
                self.entity.crm_class,
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
    age_node_id = models.CharField(max_length=50, null=True)
    
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
            # Use existing validator for domain/range
            validate_property_domain_range(
                self.cidoc_property,
                self.relationship.source.crm_class,
                self.relationship.target.crm_class,
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
    age_node_id = models.CharField(max_length=50, null=True)
    
    # Graph manager instance
    _graph_manager = None
    
    @property
    def graph_manager(self) -> GraphManager:
        """Lazy initialization of graph manager."""
        if self._graph_manager is None:
            self._graph_manager = GraphManager()
        return self._graph_manager

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.age_node_id:
            # Use graph manager to create node
            self.age_node_id = self.graph_manager.create_entity_node(
                self.crm_class,
                {'crm_class': self.crm_class}
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Override delete to handle graph node deletion."""
        if self.age_node_id:
            self.graph_manager.delete_node(self.age_node_id)
        super().delete(*args, **kwargs)

    def __str__(self):
        """
        Returns a string representation of the entity using its identifier property (P1).
        Falls back to 'Unnamed' if no identifier is set.
        """
        name_prop = self.cidocentityproperty_set.filter(
            property__property_id='P1_is_identified_by'
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
                property__property_id=property_id
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
        validate_cidoc_relationship(
            property_id,
            self.crm_class,
            'E1_CRM_Entity'
        )
        
        prop_type = CIDOCProperty.objects.get(property_id=property_id)
        entity_prop, created = CIDOCEntityProperty.objects.get_or_create(
            entity=self,
            property=prop_type,
            defaults={'value': value}
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
        from .validators import get_valid_properties
        return get_valid_properties(self.crm_class)

class CIDOCRelationship(UUIDModel):
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
    age_edge_id = models.CharField(max_length=50, null=True)
    
    # Graph manager instance
    _graph_manager = None
    
    @property
    def graph_manager(self) -> GraphManager:
        """Lazy initialization of graph manager."""
        if self._graph_manager is None:
            self._graph_manager = GraphManager()
        return self._graph_manager

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.full_clean()
        
        if not self.age_edge_id and self.source.age_node_id and self.target.age_node_id:
            # Use graph manager to create edge
            self.age_edge_id = self.graph_manager.create_relationship_edge(
                self.source.age_node_id,
                self.target.age_node_id,
                self.relation_type,
                {'relation_type': self.relation_type}
            )
            
        super().save(*args, **kwargs)
        
        # Handle symmetric and inverse relationships
        try:
            property_def = CIDOCProperty.objects.get(property_id=self.relation_type)
            
            # Validate symmetric relationship
            if property_def.is_symmetric:
                validate_symmetric_relationship(
                    property_def,
                    self.source,
                    self.target
                )
                
            # Validate inverse relationship
            if property_def.inverse_property:
                validate_inverse_relationship(
                    property_def,
                    self.source,
                    self.target
                )
                
        except CIDOCProperty.DoesNotExist:
            pass

    def delete(self, *args, **kwargs):
        """Override delete to handle graph edge deletion."""
        if self.age_edge_id:
            self.graph_manager.delete_edge(self.age_edge_id)
        super().delete(*args, **kwargs)

    def get_property(self, user, property_id):
        """Get a relationship property value if user has permission."""
        try:
            prop = self.cidocrelationshipproperty_set.get(
                property__property_id=property_id
            )
            if prop.user_can_read(user):
                return prop.value
            return None
        except CIDOCRelationshipProperty.DoesNotExist:
            return None