from django.conf import settings
from typing import Dict, Any, Optional
from arkumu.cidoc.models.graph import CIDOCGraph
# Default setting for graph integration - can be overridden in settings.py
ENABLE_GRAPH_DB = getattr(settings, 'ENABLE_GRAPH_DB', True)



class GraphService:
    """
    Service class for graph database operations.
    Decoupled from the models to make testing easier.
    """
    
    @classmethod
    def get_graph(cls):
        """Creates a new graph connection."""
        if not ENABLE_GRAPH_DB:
            # Return a mock graph or None when graph operations are disabled
            # to avoid connection errors
            return None
        
        return CIDOCGraph()
    
    @classmethod
    def create_entity_node(cls, entity_data: Dict[str, Any]) -> Optional[str]:
        """
        Creates a node for an entity and returns its ID.
        
        Args:
            entity_data: Dictionary containing entity data including crm_class
            
        Returns:
            Node ID or None if graph operations are disabled
        """
        if not ENABLE_GRAPH_DB:
            # Return None when graph operations are disabled for testing
            return None
            
        graph = cls.get_graph()
        if graph is None:
            # Return None when graph connection fails
            return None
        
        node_id = graph.create_entity(
            entity_data.get('crm_class'),
            entity_data
        )
        return node_id
        
    @classmethod
    def create_relationship_edge(cls, source_id: str, target_id: str, relation_type: str, properties: Dict[str, Any] = None) -> Optional[str]:
        """
        Creates an edge for a relationship and returns its ID.
        
        Args:
            source_id: ID of the source node
            target_id: ID of the target node
            relation_type: Type of the relationship
            properties: Additional properties for the edge
            
        Returns:
            Edge ID or None if graph operations are disabled
        """
        if not ENABLE_GRAPH_DB:
            # Return None when graph operations are disabled for testing
            return None
            
        graph = cls.get_graph()
        if graph is None:
            # Return None when graph connection fails
            return None
        
        if properties is None:
            properties = {}
        
        properties['relation_type'] = relation_type
        
        edge_id = graph.create_relationship(
            source_id,
            target_id,
            relation_type,
            properties
        )
        return edge_id
        
    @classmethod
    def update_node_properties(cls, node_id: str, properties: Dict[str, Any]) -> bool:
        """
        Updates properties of an existing node.
        
        Args:
            node_id: ID of the node to update
            properties: Dictionary of properties to update
        """
        if not ENABLE_GRAPH_DB:
            return True
            
        graph = cls.get_graph()
        if graph is None:
            return True
        
        return graph.update_node(node_id, properties)
        
    @classmethod
    def update_edge_properties(cls, edge_id: str, properties: Dict[str, Any]) -> bool:
        """
        Updates properties of an existing edge.
        
        Args:
            edge_id: ID of the edge to update
            properties: Dictionary of properties to update
        """
        if not ENABLE_GRAPH_DB:
            return True
            
        graph = cls.get_graph()
        if graph is None:
            return True
        
        return graph.update_edge(edge_id, properties)
        
    @classmethod
    def delete_node(cls, node_id: str) -> None:
        """
        Deletes a node and its associated edges.
        
        Args:
            node_id: ID of the node to delete
        """
        if not ENABLE_GRAPH_DB:
            return
            
        graph = cls.get_graph()
        if graph is None:
            return
        
        graph.delete_node(node_id)
        
    @classmethod
    def delete_edge(cls, edge_id: str) -> None:
        """
        Deletes an edge from the graph.
        
        Args:
            edge_id: ID of the edge to delete
        """
        if not ENABLE_GRAPH_DB:
            return
            
        graph = cls.get_graph()
        if graph is None:
            return
        
        graph.delete_edge(edge_id)
        
    @classmethod
    def find_node(cls, criteria: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find a node based on criteria.
        
        Args:
            criteria: Dictionary of properties to match
            
        Returns:
            Node data or None if not found
        """
        if not ENABLE_GRAPH_DB:
            return None
            
        graph = cls.get_graph()
        if graph is None:
            return None
        
        return graph.find_node(criteria)
        
    @classmethod
    def find_edges(cls, criteria: Dict[str, Any]) -> list:
        """
        Find edges based on criteria.
        
        Args:
            criteria: Dictionary of properties to match
            
        Returns:
            List of edge data
        """
        if not ENABLE_GRAPH_DB:
            return []
            
        graph = cls.get_graph()
        if graph is None:
            return []
        
        return graph.find_edges(criteria)

# Legacy compatibility for transition
GraphManager = GraphService 