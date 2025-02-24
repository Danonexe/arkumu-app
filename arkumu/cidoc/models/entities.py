from django.db import models
from django.db import transaction
from .core import CIDOCClass, CIDOCProperty, CIDOCGraph, UUIDModel
from django.contrib.auth.models import Group, User
from .validators import validate_cidoc_entity, validate_cidoc_relationship, validate_property_type, validate_property_cardinality
    
class CIDOCEntityProperty(UUIDModel):
    """
    Represents the association between a CIDOC entity and its properties,
    including the property value and access permissions.
    Acts as a through model for the many-to-many relationship.
    """
    
    entity = models.ForeignKey('CIDOCEntity', on_delete=models.CASCADE)
    property = models.ForeignKey(CIDOCProperty, on_delete=models.PROTECT)
    value = models.TextField()  # Store the literal value
    age_node_id = models.CharField(max_length=50, null=True)
    # Permissions for this specific entity-property combination
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
        User, 
        related_name='can_read_entity_properties',
        blank=True
    )
    writable_by_users = models.ManyToManyField(
        User, 
        related_name='can_write_entity_properties',
        blank=True
    )

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.age_node_id:
            graph = CIDOCGraph()
            node = graph.create_entity(
                'CIDOCEntityProperty',
                {
                    'value': self.value,
                    'property_id': self.property.property_id
                }
            )
            self.age_node_id = node.id
            
            # Create relationships to entity and property
            graph.create_relationship(
                self.age_node_id,
                self.entity.age_node_id,
                'HAS_ENTITY'
            )
            graph.create_relationship(
                self.age_node_id,
                self.property.age_node_id,
                'HAS_PROPERTY'
            )
        super().save(*args, **kwargs)

    def user_can_read(self, user):
        """
        Check if a user has read permission for this entity-property combination.
        Permission is granted if user belongs to allowed groups or is explicitly allowed.
        """
        return (
            user.groups.filter(id__in=self.readable_by_groups.all()).exists() or
            self.readable_by_users.filter(id=user.id).exists()
        )

    def user_can_write(self, user):
        """
        Check if a user has write permission for this entity-property combination.
        Permission is granted if user belongs to allowed groups or is explicitly allowed.
        """
        return (
            user.groups.filter(id__in=self.writable_by_groups.all()).exists() or
            self.writable_by_users.filter(id=user.id).exists()
        )

    def clean(self):
        """
        Validate the entity-property relationship:
        1. Ensures property is valid for the entity class
        2. Validates the property value type
        3. Checks property cardinality constraints
        """
        super().clean()
        # Validate property-entity relationship
        validate_cidoc_relationship(
            self.property.property_id,
            self.entity.crm_class,
            'E1_CRM_Entity'
        )
        # Validate property value type
        validate_property_type(self.property.property_id, self.value)
        # Validate cardinality
        validate_property_cardinality(self.entity, self.property.property_id)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entity', 'property'],
                name='unique_entity_property'
            )
        ]
        error_messages = {
            'unique_entity_property': (
                "This property already exists for this entity"
            )
        }

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

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.age_node_id:
            graph = CIDOCGraph()
            node = graph.create_entity(
                self.crm_class,
                {'crm_class': self.crm_class}
            )
            self.age_node_id = node.id
        super().save(*args, **kwargs)

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
    Handles symmetric relationships and property validation.
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
        through='CIDOCEntityProperty',
        related_name='relationship_properties'
    )
    age_edge_id = models.CharField(max_length=50, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        
        # Handle symmetric properties
        if self._is_symmetric_property(self.relation_type):
            CIDOCRelationship.objects.get_or_create(
                source=self.target,
                target=self.source,
                relation_type=self.relation_type
            )

    def __str__(self):
        """
        Returns a string representation of the relationship in the format:
        source -- relation_type --> target
        """
        return f"{self.source} -- {self.relation_type} --> {self.target}"

    def get_property(self, user, property_id):
        """
        Retrieve a relationship property value if the user has read permission.
        
        Args:
            user: The user requesting the property
            property_id: The CIDOC property identifier
            
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

    def clean(self):
        """
        Validate the relationship according to CIDOC-CRM rules.
        Ensures the relationship type is valid between the source and target classes.
        """
        super().clean()
        validate_cidoc_relationship(
            self.relation_type,
            self.source.crm_class,
            self.target.crm_class
        )