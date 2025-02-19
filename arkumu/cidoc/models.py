from django.db import models, transaction
from .validators import validate_cidoc_entity, validate_cidoc_relationship, validate_cidoc_property, validate_property_type, validate_property_cardinality
from django.contrib.auth.models import Group, User
from age import Graph, Node, Edge


class CIDOCGraph:
    def __init__(self):
        self.graph = Graph('cidoc_graph')

    def create_entity(self, crm_class, properties=None):
        node = Node(
            label=crm_class,
            properties=properties or {}
        )
        self.graph.create_node(node)
        return node

    def create_relationship(self, source_id, target_id, relation_type, properties=None):
        edge = Edge(
            start_id=source_id,
            end_id=target_id,
            label=relation_type,
            properties=properties or {}
        )
        self.graph.create_edge(edge)
        return edge

class CIDOCProperty(models.Model):
    property_id = models.CharField(
        max_length=50,
        validators=[validate_cidoc_property]
    )
    age_node_id = models.CharField(max_length=50, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.age_node_id:
            graph = CIDOCGraph()
            node = graph.create_entity(
                'CIDOCProperty',
                {'property_id': self.property_id}
            )
            self.age_node_id = node.id
        super().save(*args, **kwargs)

class CIDOCEntityProperty(models.Model):
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
        return (
            user.groups.filter(id__in=self.readable_by_groups.all()).exists() or
            self.readable_by_users.filter(id=user.id).exists()
        )

    def user_can_write(self, user):
        return (
            user.groups.filter(id__in=self.writable_by_groups.all()).exists() or
            self.writable_by_users.filter(id=user.id).exists()
        )

    def clean(self):
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

class CIDOCEntity(models.Model):
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
        name_prop = self.cidocentityproperty_set.filter(
            property__property_id='P1_is_identified_by'
        ).first()
        return f"{self.crm_class}: {name_prop.value if name_prop else 'Unnamed'}"

    def get_property(self, user, property_id):
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
        from .validators import get_valid_properties
        return get_valid_properties(self.crm_class)

class CIDOCRelationship(models.Model):
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
        return f"{self.source} -- {self.relation_type} --> {self.target}"

    def get_property(self, user, property_id):
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
        super().clean()
        validate_cidoc_relationship(
            self.relation_type,
            self.source.crm_class,
            self.target.crm_class
        )