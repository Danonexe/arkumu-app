import logging
from arkumu.metadata.models import Resource, ResourceType 
from arkumu.importer.services.importer.uri_utils import (
    RDF_BASE_URI, RDFS_BASE_URI, CIDOC_CRM_BASE_URI, OWL_BASE_URI
)

logger = logging.getLogger(__name__) # arkumu.importer.services.resource_manager

class ResourceManager:
    def __init__(self, institution_code):
        self.institution_code = institution_code
        # No separate logger passed, it will use the module logger or specific loggers can be called by methods.

    def get_or_create_resource(self, defaults=None, **kwargs):
        """
        Gets or creates a Resource instance, handling both URIs and literals appropriately.
        
        For IRI resources, this uses the unique URI constraint.
        For literal resources, this looks up existing literals with the same value, language, and datatype.
        
        When is_placeholder=True is passed in defaults, creates a placeholder resource.
        """
        if defaults is None:
            defaults = {}
            
        # Handle backwards compatibility with source_field
        if 'source_field' in kwargs:
            # Move source_field to name for lookups
            kwargs['name'] = kwargs.pop('source_field')
        
        if 'source_field' in defaults:
            # Move source_field to name in defaults
            defaults['name'] = defaults.pop('source_field')
        
        # Handle backwards compatibility with literal_value
        if 'literal_value' in kwargs:
            kwargs['value'] = kwargs.pop('literal_value')
        
        if 'literal_language' in kwargs:
            kwargs['language'] = kwargs.pop('literal_language')
            
        if 'literal_datatype' in kwargs:
            kwargs['datatype'] = kwargs.pop('literal_datatype')
        
        if 'literal_value' in defaults:
            defaults['value'] = defaults.pop('literal_value')
            
        if 'literal_language' in defaults:
            defaults['language'] = defaults.pop('literal_language')
            
        if 'literal_datatype' in defaults:
            defaults['datatype'] = defaults.pop('literal_datatype')

        try:
            # CASE 1: IRI resource with URI - check for placeholders first
            if 'uri' in kwargs:
                uri = kwargs['uri']
                try:
                    # Look for an existing placeholder resource with this URI
                    existing_placeholder = Resource.objects.filter(uri=uri, is_placeholder=True).first()
                    if existing_placeholder:
                        logger.info(f"Found placeholder resource for URI: {uri}, will update it")
                        
                        # Update the placeholder with the new attributes
                        for key, value in defaults.items():
                            if hasattr(existing_placeholder, key):
                                setattr(existing_placeholder, key, value)
                        
                        # Mark as no longer a placeholder unless explicitly keeping it as one
                        if not defaults.get('is_placeholder', False):
                            existing_placeholder.is_placeholder = False
                        
                        existing_placeholder.save()
                        
                        # If name contains PLACEHOLDER:, update it
                        if existing_placeholder.name and existing_placeholder.name.startswith("PLACEHOLDER:"):
                            if 'name' in defaults:
                                existing_placeholder.name = defaults['name'] + " (was placeholder)"
                            else:
                                existing_placeholder.name = existing_placeholder.name.replace("PLACEHOLDER:", "RESOLVED:")
                            existing_placeholder.save()
                            
                        return existing_placeholder
                except Exception as e:
                    logger.warning(f"Error checking for placeholder: {e}", exc_info=True)
            
            # CASE 2: Literal resource - look up by value, language, datatype
            if 'value' in kwargs and ('resource_type' in kwargs and kwargs['resource_type'] == ResourceType.LITERAL):
                value = kwargs['value']
                language = kwargs.get('language')
                datatype = kwargs.get('datatype')
                
                # Build lookup query
                lookup = {
                    'resource_type': ResourceType.LITERAL,
                    'value': value
                }
                
                # Add language and datatype to lookup if provided
                if language is not None:
                    lookup['language'] = language
                else:
                    lookup['language__isnull'] = True
                    
                if datatype is not None:
                    lookup['datatype'] = datatype
                else:
                    lookup['datatype__isnull'] = True
                
                # Add source and name for uniqueness if available
                if 'source' in kwargs:
                    lookup['source'] = kwargs['source']
                elif 'source' in defaults:
                    lookup['source'] = defaults['source']
                
                if 'name' in kwargs:
                    lookup['name'] = kwargs['name']
                elif 'name' in defaults:
                    lookup['name'] = defaults['name']
                
                try:
                    # Try to find an existing literal
                    existing_literal = Resource.objects.filter(**lookup).first()
                    if existing_literal:
                        logger.debug(f"Reusing existing literal: '{value}'")
                        return existing_literal
                except Exception as e:
                    logger.warning(f"Error looking up existing literal: {e}", exc_info=True)
            
            # CASE 3: Standard get_or_create for any resource type
            resource, created = Resource.objects.get_or_create(defaults=defaults, **kwargs)
            if created:
                if 'uri' in kwargs:
                    logger.debug(f"Created Resource with URI: {kwargs['uri']}")
                elif 'value' in kwargs:
                    # Truncate for logging if it's very long
                    log_val = str(kwargs['value'])
                    if len(log_val) > 50:
                        log_val = log_val[:47] + "..."
                    logger.debug(f"Created Literal Resource: {log_val}")
                else:
                    logger.debug(f"Created Resource (no URI/value in kwargs): {resource}")
            return resource
        except Exception as e:
            # Log with more context from kwargs and defaults
            logger.error(f"Error in get_or_create_resource: {str(e)}, kwargs={kwargs}, defaults={defaults}", exc_info=True)
            raise

    def is_placeholder(self, resource):
        """
        Check if a resource is a placeholder.
        
        Args:
            resource: Resource object to check
            
        Returns:
            bool: True if the resource is a placeholder
        """
        if hasattr(resource, 'is_placeholder') and resource.is_placeholder:
            return True
        
        # Fallback for database without is_placeholder field migrations
        if resource.name and resource.name.startswith("PLACEHOLDER:"):
            return True
            
        return False

    def get_all_placeholders(self):
        """
        Returns all placeholder resources in the database.
        
        Returns:
            QuerySet: All resources that are placeholders
        """
        # Try with the field first, fall back to name pattern
        try:
            placeholders = Resource.objects.filter(is_placeholder=True)
            if placeholders.exists():
                return placeholders
        except:
            # Fall back to filtering by name pattern
            pass
            
        return Resource.objects.filter(name__startswith="PLACEHOLDER:")

    def get_or_create_rdf_term(self, term_name, description):
        logger.debug(f"Getting or creating RDF term: {term_name}")
        uri = f"{RDF_BASE_URI}{term_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "RDF", # Standard terms source from RDF itself
                'name': f"rdf:{term_name}",
                'value': description 
            }
        )

    def get_or_create_rdfs_term(self, term_name, description):
        logger.debug(f"Getting or creating RDFS term: {term_name}")
        uri = f"{RDFS_BASE_URI}{term_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "RDFS",
                'name': f"rdfs:{term_name}",
                'value': description
            }
        )

    def get_or_create_owl_term(self, term_name, description):
        logger.debug(f"Getting or creating OWL term: {term_name}")
        uri = f"{OWL_BASE_URI}{term_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "OWL",
                'name': f"owl:{term_name}",
                'value': description
            }
        )

    def get_or_create_cidoc_class_resource(self, class_short_name):
        logger.debug(f"Getting or creating CIDOC class: {class_short_name}")
        uri = f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.CLASS,
                'source': "CIDOC-CRM",
                'name': f"cidoc:{class_short_name}",
                'value': f"CIDOC-CRM Class: {class_short_name}"
            }
        )

    def get_or_create_cidoc_property_resource(self, property_short_name):
        logger.debug(f"Getting or creating CIDOC property: {property_short_name}")
        uri = f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "CIDOC-CRM",
                'name': f"cidoc:{property_short_name}",
                'value': f"CIDOC-CRM Property: {property_short_name}"
            }
        )

