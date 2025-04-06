"""
Signal handlers for CIDOC models.

This module contains signal handlers that decouple graph database operations
from the model definitions, allowing for clean separation of concerns.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models.entities import CIDOCEntity, CIDOCRelationship
from .models.graph_service import GraphService, ENABLE_GRAPH_DB


@receiver(post_save, sender=CIDOCEntity)
def handle_entity_save(sender, instance, created, **kwargs):
    """
    Handle entity creation and updates in the graph database.
    
    This signal handler is triggered after an entity is saved to the SQL database,
    and it creates or updates the corresponding node in the graph database if 
    graph functionality is enabled.
    """
    if not ENABLE_GRAPH_DB:
        return
        
    entity_data = {
        'crm_class': instance.crm_class,
        'uuid': str(instance.id)
    }
    
    if created or not instance.age_node_id:
        # Create new node and update the entity with the node ID
        node_id = GraphService.create_entity_node(entity_data)
        if node_id and node_id != instance.age_node_id:
            # Avoid infinite recursion by disconnecting signal temporarily
            post_save.disconnect(handle_entity_save, sender=CIDOCEntity)
            instance.age_node_id = node_id
            instance.save(update_fields=['age_node_id'])
            post_save.connect(handle_entity_save, sender=CIDOCEntity)
    else:
        # Update existing node
        GraphService.update_node_properties(instance.age_node_id, entity_data)


@receiver(post_delete, sender=CIDOCEntity)
def handle_entity_delete(sender, instance, **kwargs):
    """
    Handle entity deletion in the graph database.
    
    This signal handler is triggered after an entity is deleted from the SQL database,
    and it deletes the corresponding node in the graph database if graph functionality
    is enabled.
    """
    if not ENABLE_GRAPH_DB or not instance.age_node_id:
        return
        
    GraphService.delete_node(instance.age_node_id)


@receiver(post_save, sender=CIDOCRelationship)
def handle_relationship_save(sender, instance, created, **kwargs):
    """
    Handle relationship creation and updates in the graph database.
    
    This signal handler is triggered after a relationship is saved to the SQL database,
    and it creates or updates the corresponding edge in the graph database if 
    graph functionality is enabled.
    """
    if not ENABLE_GRAPH_DB:
        return
        
    if not instance.source.age_node_id or not instance.target.age_node_id:
        return
        
    properties = {
        'relation_type': instance.relation_type,
        'uuid': str(instance.id)
    }
    
    if created or not instance.age_edge_id:
        # Create new edge and update the relationship with the edge ID
        edge_id = GraphService.create_relationship_edge(
            instance.source.age_node_id,
            instance.target.age_node_id,
            instance.relation_type,
            properties
        )
        
        if edge_id and edge_id != instance.age_edge_id:
            # Avoid infinite recursion by disconnecting signal temporarily
            post_save.disconnect(handle_relationship_save, sender=CIDOCRelationship)
            instance.age_edge_id = edge_id
            instance.save(update_fields=['age_edge_id'])
            post_save.connect(handle_relationship_save, sender=CIDOCRelationship)
    else:
        # Update existing edge
        GraphService.update_edge_properties(instance.age_edge_id, properties)


@receiver(post_delete, sender=CIDOCRelationship)
def handle_relationship_delete(sender, instance, **kwargs):
    """
    Handle relationship deletion in the graph database.
    
    This signal handler is triggered after a relationship is deleted from the SQL database,
    and it deletes the corresponding edge in the graph database if graph functionality
    is enabled.
    """
    if not ENABLE_GRAPH_DB or not instance.age_edge_id:
        return
        
    GraphService.delete_edge(instance.age_edge_id) 