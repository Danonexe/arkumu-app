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

    def get_or_create_resource(self, defaults, **kwargs):
        """Gets or creates a Resource instance."""
        # Add institution_code to defaults if not present, to ensure source is often set
        # However, defaults can be specific, so be careful not to override intended source.
        # For now, assuming callers will set 'source' in defaults as needed.
        # if 'source' not in defaults and self.institution_code:
        #     defaults['source'] = self.institution_code

        try:
            resource, created = Resource.objects.get_or_create(defaults=defaults, **kwargs)
            if created:
                if 'uri' in kwargs:
                    logger.debug(f"Created Resource with URI: {kwargs['uri']}")
                elif 'literal_value' in kwargs:
                    # Truncate for logging if it's very long
                    log_val = str(kwargs['literal_value'])
                    if len(log_val) > 50:
                        log_val = log_val[:47] + "..."
                    logger.debug(f"Created Literal Resource: {log_val}")
                else:
                    logger.debug(f"Created Resource (no URI/literal in kwargs): {resource}")
            return resource
        except Exception as e:
            # Log with more context from kwargs and defaults
            logger.error(f"Error in get_or_create_resource: {str(e)}, kwargs={kwargs}, defaults={defaults}", exc_info=True)
            raise

    def get_or_create_rdf_term(self, term_name, description):
        logger.debug(f"Getting or creating RDF term: {term_name}")
        uri = f"{RDF_BASE_URI}{term_name}"
        return self.get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "RDF", # Standard terms source from RDF itself
                'source_field': f"rdf:{term_name}",
                'literal_value': description 
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
                'source_field': f"rdfs:{term_name}",
                'literal_value': description
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
                'source_field': f"owl:{term_name}",
                'literal_value': description
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
                'source_field': f"cidoc:{class_short_name}",
                'literal_value': f"CIDOC-CRM Class: {class_short_name}"
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
                'source_field': f"cidoc:{property_short_name}",
                'literal_value': f"CIDOC-CRM Property: {property_short_name}"
            }
        )

