from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
import uuid
from validators import validate_cidoc_property
from age import Graph, Node, Edge

class UUIDModel(models.Model):
    """Abstract base class for tracking"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_created', null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_updated', null=True)

    class Meta:
        abstract = True

class CIDOCGraph(UUIDModel):
    """
    A wrapper class for managing CIDOC-CRM graph operations using the AGE graph database.
    Provides methods for creating entities and relationships in the graph structure.
    """
    
    def __init__(self):
        """Initialize a new CIDOC graph instance."""
        self.graph = Graph('cidoc_graph')

    def create_entity(self, crm_class, properties=None):
        """
        Create a new node in the graph representing a CIDOC-CRM entity.
        
        Args:
            crm_class (str): The CIDOC-CRM class identifier (e.g., 'E21_Person')
            properties (dict, optional): Additional properties for the node
            
        Returns:
            Node: The created graph node
        """
        node = Node(
            label=crm_class,
            properties=properties or {}
        )
        self.graph.create_node(node)
        return node

    def create_relationship(self, source_id, target_id, relation_type, properties=None):
        """
        Create a new edge in the graph representing a CIDOC-CRM relationship.
        
        Args:
            source_id (str): ID of the source node
            target_id (str): ID of the target node
            relation_type (str): The type of relationship (e.g., 'P2_has_type')
            properties (dict, optional): Additional properties for the edge
            
        Returns:
            Edge: The created graph edge
        """
        edge = Edge(
            start_id=source_id,
            end_id=target_id,
            label=relation_type,
            properties=properties or {}
        )
        self.graph.create_edge(edge)
        return edge

class CIDOCProperty(UUIDModel):
    """
    Represents a CIDOC-CRM property definition (e.g., P1, P2, etc.).
    Maps CIDOC properties to graph nodes for property-based queries.
    """
    
    property_id = models.CharField(
        max_length=50,
        validators=[validate_cidoc_property]
    )
    age_node_id = models.CharField(max_length=50, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Save the property and create corresponding graph node if it doesn't exist.
        Uses atomic transaction to ensure data consistency.
        """
        if not self.age_node_id:
            graph = CIDOCGraph()
            node = graph.create_entity(
                'CIDOCProperty',
                {'property_id': self.property_id}
            )
            self.age_node_id = node.id
        super().save(*args, **kwargs)
