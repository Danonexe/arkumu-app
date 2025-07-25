"""
Template utilities for efficient rendering of resource-based components.
This module provides performant template rendering using the triple-based data model.
"""

from django.core.cache import cache
from django.template.loader import render_to_string
from django.db.models import Prefetch, Q
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from arkumu.metadata.models import Resource, Triple, ResourceType


class ResourcePropertyCache:
    """Efficiently cache and retrieve resource properties from triples."""
    
    def __init__(self, timeout: int = 3600):
        self.timeout = timeout
        self.property_cache = {}
        
    def get_properties_for_resources(self, resources: List[Resource]) -> Dict[str, Dict]:
        """
        Batch fetch all properties for multiple resources.
        Returns a dict mapping resource IDs to their properties.
        """
        resource_ids = [r.id for r in resources]
        
        # Check cache first
        cache_keys = [f"props:{rid}" for rid in resource_ids]
        cached = cache.get_many(cache_keys)
        
        # Find uncached resources
        uncached_ids = []
        for rid in resource_ids:
            if f"props:{rid}" not in cached:
                uncached_ids.append(rid)
        
        if uncached_ids:
            # Fetch from database
            fresh_props = self._fetch_properties_from_db(uncached_ids)
            
            # Cache the results
            to_cache = {}
            for rid, props in fresh_props.items():
                cache_key = f"props:{rid}"
                to_cache[cache_key] = props
                cached[cache_key] = props
            
            if to_cache:
                cache.set_many(to_cache, self.timeout)
        
        # Return formatted results
        result = {}
        for rid in resource_ids:
            result[str(rid)] = cached.get(f"props:{rid}", {})
        
        return result
    
    def _fetch_properties_from_db(self, resource_ids: List[str]) -> Dict[str, Dict]:
        """Fetch properties from triples for given resources."""
        # Efficient query with select_related
        triples = Triple.objects.filter(
            subject_id__in=resource_ids
        ).select_related(
            'predicate', 'object'
        ).order_by('predicate__name')
        
        # Group by subject
        properties = defaultdict(lambda: defaultdict(list))
        
        for triple in triples:
            subject_id = str(triple.subject_id)
            pred_name = triple.predicate.name or triple.predicate.uri
            
            # Format object based on type
            if triple.object.resource_type == ResourceType.LITERAL:
                value = triple.object.value
            else:
                value = {
                    'uri': triple.object.uri,
                    'name': triple.object.name,
                    'id': str(triple.object.id)
                }
            
            properties[subject_id][pred_name].append(value)
        
        return dict(properties)


class ComponentRenderer:
    """Render components based on resource types and properties."""
    
    # Map resource classes to their display properties
    PROPERTY_MAPPINGS = {
        'http://arkumu.org/ontology#Project': {
            'title': ['dc:title', 'rdfs:label'],
            'year': ['dc:date', 'arkumu:year'],
            'institution': ['arkumu:institution', 'dc:publisher'],
            'contributors': ['dc:contributor', 'arkumu:hasContributor'],
            'categories': ['dc:subject', 'arkumu:category'],
            'description': ['dc:description', 'arkumu:abstract'],
        },
        'http://arkumu.org/ontology#Event': {
            'title': ['dc:title', 'rdfs:label'],
            'date_range': ['arkumu:startDate', 'arkumu:endDate'],
            'type': ['arkumu:eventType', 'rdf:type'],
            'participants': ['arkumu:hasParticipant', 'dc:contributor'],
        },
        'http://arkumu.org/ontology#Person': {
            'name': ['foaf:name', 'rdfs:label'],
            'role': ['arkumu:role', 'dc:type'],
            'affiliation': ['arkumu:affiliation', 'foaf:organization'],
        }
    }
    
    def __init__(self):
        self.property_cache = ResourcePropertyCache()
    
    def render_resource_cards(self, resources: List[Resource], user) -> List[str]:
        """
        Render multiple resource cards efficiently.
        Returns list of rendered HTML strings.
        """
        # Batch fetch all properties
        all_properties = self.property_cache.get_properties_for_resources(resources)
        
        # Render each card
        rendered_cards = []
        for resource in resources:
            props = all_properties.get(str(resource.id), {})
            card_html = self._render_single_card(resource, props, user)
            rendered_cards.append(card_html)
        
        return rendered_cards
    
    def _render_single_card(self, resource: Resource, properties: Dict, user) -> str:
        """Render a single resource card."""
        # Determine resource class
        resource_class = self._get_resource_class(resource, properties)
        
        # Map properties to display fields
        display_data = self._map_properties_to_display(resource_class, properties)
        
        # Add metadata
        display_data.update({
            'resource': resource,
            'resource_id': str(resource.id),
            'resource_uri': resource.uri,
            'can_edit': resource.can_user_edit(user),
            'organization': resource.organization,
        })
        
        # Cache the rendered card
        cache_key = f"card:{resource.id}:{user.organization.id}:{resource.updated_at}"
        cached_html = cache.get(cache_key)
        
        if cached_html is None:
            # Select template based on resource class
            template_name = self._get_template_for_class(resource_class)
            cached_html = render_to_string(template_name, display_data)
            cache.set(cache_key, cached_html, 3600)
        
        return cached_html
    
    def _get_resource_class(self, resource: Resource, properties: Dict) -> str:
        """Determine the class/type of a resource."""
        # Check rdf:type property
        rdf_types = properties.get('rdf:type', [])
        if rdf_types:
            for rdf_type in rdf_types:
                if isinstance(rdf_type, dict) and rdf_type.get('uri'):
                    return rdf_type['uri']
        
        # Default fallback
        return 'http://arkumu.org/ontology#Resource'
    
    def _map_properties_to_display(self, resource_class: str, properties: Dict) -> Dict:
        """Map RDF properties to display fields based on resource class."""
        mapping = self.PROPERTY_MAPPINGS.get(resource_class, {})
        display_data = {}
        
        for display_field, property_names in mapping.items():
            # Try each property name until we find a value
            for prop_name in property_names:
                if prop_name in properties:
                    values = properties[prop_name]
                    if values:
                        # Handle single vs multiple values
                        if display_field in ['title', 'name', 'year']:
                            display_data[display_field] = values[0]
                        else:
                            display_data[display_field] = values
                        break
        
        return display_data
    
    def _get_template_for_class(self, resource_class: str) -> str:
        """Get the appropriate template for a resource class."""
        class_to_template = {
            'http://arkumu.org/ontology#Project': 'components/cards/project_card.html',
            'http://arkumu.org/ontology#Event': 'components/cards/event_card.html',
            'http://arkumu.org/ontology#Person': 'components/cards/person_card.html',
        }
        
        return class_to_template.get(
            resource_class, 
            'components/cards/generic_resource_card.html'
        )


class FacetBuilder:
    """Build faceted navigation from triple data."""
    
    def __init__(self, user):
        self.user = user
        
    def get_facets_for_class(self, resource_class: str) -> List[Dict]:
        """Get available facets (properties) for a resource class."""
        cache_key = f"facets:{resource_class}:{self.user.organization.id}"
        facets = cache.get(cache_key)
        
        if facets is None:
            facets = self._build_facets_from_db(resource_class)
            cache.set(cache_key, facets, 600)  # 10 minute cache
        
        return facets
    
    def _build_facets_from_db(self, resource_class: str) -> List[Dict]:
        """Build facet data from triples."""
        # Get all resources of this class
        class_resources = Resource.objects.for_user(self.user).filter(
            subject_triples__predicate__uri='rdf:type',
            subject_triples__object__uri=resource_class
        ).distinct()
        
        # Get all predicates used with these resources
        predicates = Resource.objects.filter(
            resource_type=ResourceType.PROPERTY,
            predicate_triples__subject__in=class_resources
        ).distinct().annotate(
            usage_count=models.Count('predicate_triples')
        ).order_by('-usage_count')
        
        facets = []
        for predicate in predicates[:20]:  # Limit to top 20 properties
            # Get unique values for this predicate
            values = self._get_facet_values(predicate, class_resources)
            
            if values:
                facets.append({
                    'id': str(predicate.id),
                    'uri': predicate.uri,
                    'name': predicate.name or predicate.uri.split('#')[-1],
                    'values': values,
                    'count': len(values)
                })
        
        return facets
    
    def _get_facet_values(self, predicate: Resource, resources) -> List[Dict]:
        """Get unique values for a predicate across resources."""
        # Get all objects for this predicate
        values = Resource.objects.filter(
            object_triples__predicate=predicate,
            object_triples__subject__in=resources
        ).distinct()[:50]  # Limit to 50 values
        
        facet_values = []
        for value in values:
            if value.resource_type == ResourceType.LITERAL:
                display = value.value
            else:
                display = value.name or value.uri.split('#')[-1]
            
            facet_values.append({
                'id': str(value.id),
                'display': display,
                'count': value.object_triples.filter(
                    predicate=predicate,
                    subject__in=resources
                ).count()
            })
        
        return sorted(facet_values, key=lambda x: x['count'], reverse=True)


# Template tags for easy usage
from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def render_resource_cards(context, resources):
    """Template tag to render multiple resource cards."""
    user = context['request'].user
    renderer = ComponentRenderer()
    return renderer.render_resource_cards(resources, user)

@register.simple_tag(takes_context=True) 
def get_resource_facets(context, resource_class):
    """Template tag to get facets for a resource class."""
    user = context['request'].user
    builder = FacetBuilder(user)
    return builder.get_facets_for_class(resource_class)