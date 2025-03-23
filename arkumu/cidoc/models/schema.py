from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
import uuid
import age

class UUIDModel(models.Model):
    """Abstract base class for tracking"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_created', null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_updated', null=True)

    class Meta:
        abstract = True

class CIDOCClass(UUIDModel):
    """
    Represents a CIDOC-CRM class (E1, E2, etc.).
    """
    class_id = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField()
    parent_classes = models.ManyToManyField('self', symmetrical=False, related_name='child_classes', blank=True)
    is_primitive = models.BooleanField(
        default=False,
        help_text="If True, this class represents a primitive value type (E59, E60, etc.)"
    )
    
    class Meta:
        verbose_name = "CIDOC Class"
        verbose_name_plural = "CIDOC Classes"
    
    def __str__(self):
        return f"{self.class_id}: {self.label}"

class CIDOCProperty(UUIDModel):
    """
    Represents a CIDOC-CRM property definition (P1, P2, etc.).
    """
    property_id = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField()
    domain_class = models.ForeignKey(CIDOCClass, on_delete=models.SET_NULL, null=True, related_name='domain_properties')
    range_class = models.ForeignKey(CIDOCClass, on_delete=models.SET_NULL, null=True, related_name='range_properties')
    
    # Property characteristics from RDF
    is_functional = models.BooleanField(default=False, help_text="Property can have at most one value")
    is_symmetric = models.BooleanField(default=False, help_text="If A relates to B, then B relates to A")
    is_transitive = models.BooleanField(default=False, help_text="If A relates to B and B to C, then A relates to C")
    
    # Property hierarchy
    parent_properties = models.ManyToManyField('self', symmetrical=False, related_name='child_properties', blank=True)
    inverse_property = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='inverse_of',
        help_text="The inverse property (e.g., P1i for P1)"
    )
    
    class Meta:
        verbose_name = "CIDOC Property"
        verbose_name_plural = "CIDOC Properties"
    
    def __str__(self):
        return f"{self.property_id}: {self.label}" 

class CIDOCGraph(UUIDModel):
    """
    A wrapper class for managing CIDOC-CRM graph operations using the AGE graph database.
    Provides methods for creating entities and relationships in the graph structure.
    """
    
    def __init__(self, graph_name='cidoc_graph'):
        """Initialize a new CIDOC graph instance."""
        super().__init__()
        self.graph_name = graph_name
        self._age = None

    def _ensure_connection(self):
        """Ensure we have an active AGE connection"""
        if not self._age:
            self._age = age.connect(
                host=settings.DATABASES['default']['HOST'],
                port=settings.DATABASES['default']['PORT'],
                dbname=settings.DATABASES['default']['NAME'],
                user=settings.DATABASES['default']['USER'],
                password=settings.DATABASES['default']['PASSWORD'],
                graph=self.graph_name,
                load_from_plugins=True
            )

    def create_entity(self, crm_class, properties=None):
        """
        Create a new vertex in the graph representing a CIDOC-CRM entity.
        
        Args:
            crm_class (str): The CIDOC-CRM class identifier (e.g., 'E21_Person')
            properties (dict, optional): Additional properties for the vertex
            
        Returns:
            str: The ID of the created vertex
        """
        self._ensure_connection()
        properties = properties or {}
        properties['crm_class'] = crm_class
        
        cypher_query = """
        CREATE (n:$crm_class $props) RETURN id(n) as node_id
        """
        result = self._age.run_cypher(cypher_query, {'crm_class': crm_class, 'props': properties})
        return result[0]['node_id'] if result else None

    def create_relationship(self, source_id, target_id, relation_type, properties=None):
        """
        Create a new edge in the graph representing a CIDOC-CRM relationship.
        
        Args:
            source_id (str): ID of the source vertex
            target_id (str): ID of the target vertex
            relation_type (str): The type of relationship (e.g., 'P2_has_type')
            properties (dict, optional): Additional properties for the edge
            
        Returns:
            str: The ID of the created edge
        """
        self._ensure_connection()
        properties = properties or {}
        properties['relation_type'] = relation_type
        
        cypher_query = """
        MATCH (a), (b)
        WHERE id(a) = $source_id AND id(b) = $target_id
        CREATE (a)-[r:$relation_type $props]->(b)
        RETURN id(r) as edge_id
        """
        result = self._age.run_cypher(cypher_query, {
            'source_id': source_id,
            'target_id': target_id,
            'relation_type': relation_type,
            'props': properties
        })
        return result[0]['edge_id'] if result else None

    def update_node(self, node_id, properties):
        """
        Update properties of an existing node.
        
        Args:
            node_id (str): ID of the node to update
            properties (dict): New properties to set
            
        Returns:
            bool: True if update was successful
        """
        self._ensure_connection()
        cypher_query = """
        MATCH (n)
        WHERE id(n) = $node_id
        SET n += $props
        RETURN n
        """
        result = self._age.run_cypher(cypher_query, {'node_id': node_id, 'props': properties})
        return bool(result)

    def update_edge(self, edge_id, properties):
        """
        Update properties of an existing edge.
        
        Args:
            edge_id (str): ID of the edge to update
            properties (dict): New properties to set
            
        Returns:
            bool: True if update was successful
        """
        self._ensure_connection()
        cypher_query = """
        MATCH ()-[r]->()
        WHERE id(r) = $edge_id
        SET r += $props
        RETURN r
        """
        result = self._age.run_cypher(cypher_query, {'edge_id': edge_id, 'props': properties})
        return bool(result)

    def delete_node(self, node_id):
        """Delete a node and its relationships from the graph"""
        self._ensure_connection()
        cypher_query = """
        MATCH (n)
        WHERE id(n) = $node_id
        DETACH DELETE n
        """
        self._age.run_cypher(cypher_query, {'node_id': node_id})

    def delete_edge(self, edge_id):
        """Delete an edge from the graph"""
        self._ensure_connection()
        cypher_query = """
        MATCH ()-[r]->()
        WHERE id(r) = $edge_id
        DELETE r
        """
        self._age.run_cypher(cypher_query, {'edge_id': edge_id})

    def __del__(self):
        """Cleanup connection when object is destroyed"""
        if self._age:
            self._age.close()
