
from django.conf import settings
from arkumu.cidoc.models.cidoc import UUIDModel
import age


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
