import json
import logging
from django.db import transaction
from datetime import datetime
from arkumu.cidoc.models import Resource, ResourceType, Triple
import re

# Base URIs - adjust as needed
RDF_BASE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_BASE_URI = "http://www.w3.org/2000/01/rdf-schema#"
CIDOC_CRM_BASE_URI = "http://cidoc-crm.org/cidoc-crm/"
XSD_BASE_URI = "http://www.w3.org/2001/XMLSchema#"
# Example: You'll need a base URI for your institution's minted resources
DEFAULT_INSTITUTION_BASE_URI = "http://arkumu.nrw/data/"

# Setup logger
logger = logging.getLogger(__name__)


class JSONMappingImporter:
    def __init__(self, mapping_file_path, institution_base_uri=None, related_sources=None):
        logger.info(f"Initializing JSONMappingImporter with mapping file: {mapping_file_path}")
        try:
            with open(mapping_file_path, 'r') as f:
                self.mapping_config = json.load(f)
            
            self.institution_code = self.mapping_config.get("institution")
            if not self.institution_code:
                logger.error("Missing 'institution' code in mapping JSON")
                raise ValueError("Mapping JSON must contain an 'institution' code.")

            self.institution_base_uri = institution_base_uri or DEFAULT_INSTITUTION_BASE_URI
            if not self.institution_base_uri.endswith('/'):
                self.institution_base_uri += '/'
            
            self.default_domain_class = self.mapping_config.get("domain") # Read top-level domain
            if self.default_domain_class:
                logger.info(f"Default domain class from mapping: {self.default_domain_class}")
            
            self.source_format = self.mapping_config.get("source_format", "N/A")
            self.mappings = self.mapping_config.get("mappings", [])
            logger.debug(f"Loaded {len(self.mappings)} mapping rules")
            
            self.expected_source_columns = self._extract_expected_source_columns()
            logger.debug(f"Extracted {len(self.expected_source_columns)} expected source columns")
            
            # Dictionary of related sources (filename -> data) for cross-file lookups
            self.related_sources = related_sources or {}
            logger.debug(f"Initialized with {len(self.related_sources)} related sources")

            # Pre-cache common resources
            logger.debug("Pre-caching common RDF resources")
            self.rdf_type_resource = self._get_or_create_rdf_term("type", "RDF type property")
            self.rdfs_label_resource = self._get_or_create_rdfs_term("label", "RDFS label property")
            logger.info(f"JSONMappingImporter initialized successfully for institution: {self.institution_code}")
        except Exception as e:
            logger.exception(f"Failed to initialize JSONMappingImporter: {str(e)}")
            raise

    def _slugify_uri_part(self, value_str):
        if not isinstance(value_str, str):
            value_str = str(value_str)
        
        # Basic transliteration for common German umlauts / common characters
        # For more comprehensive solution, consider a library like unidecode
        replacements = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss',
            ' ': '-', '/': '-', '\\': '-', '?': '', '#': '', '&': 'and', '+': 'plus',
            '(': '', ')': '', '[': '', ']': '', '{': '', '}': '', '\'': '', '\"': '',
            '`': '', ':': '-', ';': '-', ',': '-', '.': '-', '=': '' 
        }
        for old, new in replacements.items():
            value_str = value_str.replace(old, new)
            
        value_str = value_str.lower()
        
        # Keep only alphanumeric characters and hyphens.
        value_str = re.sub(r'[^a-z0-9-]', '', value_str)
        
        # Replace multiple hyphens with a single hyphen
        value_str = re.sub(r'-+', '-', value_str)
        
        # Remove leading/trailing hyphens
        value_str = value_str.strip('-')
        
        # Max length for a segment (can be applied here or at point of use if specific lengths needed)
        # value_str = value_str[:50] 
        
        if not value_str: # Handle cases where slugification results in empty string
            # Fallback to a simple hash if it's critical to have some unique part
            # For now, returning a default placeholder. Consider implications.
            # import hashlib
            # return hashlib.md5(original_value_before_slugify.encode()).hexdigest()[:8] 
            return "n-a" # Or raise an error
            
        return value_str

    def _extract_expected_source_columns(self):
        """Extracts all unique source_column names from the mapping rules, including nested ones."""
        logger.debug("Extracting expected source columns from mapping rules")
        expected_columns = set()
        for rule in self.mappings:
            if rule.get('source_column'):
                expected_columns.add(rule['source_column'])
            
            # Also check within object_properties if they exist
            object_props = rule.get('object_properties', [])
            for sub_rule in object_props:
                if sub_rule.get('source_column'):
                    expected_columns.add(sub_rule['source_column'])
                # Recursion could be added here if sub-rules can have their own object_properties
                # For now, assuming only one level of nesting for source_column extraction.

        logger.debug(f"Found {len(expected_columns)} expected columns: {expected_columns}")
        return expected_columns

    def validate_source_headers(self, actual_source_headers):
        """
        Validates a list of actual source headers against expected headers from the mapping.
        Args:
            actual_source_headers (list or set): The headers found in the source data (e.g., CSV headers).
        Returns:
            dict: A dictionary with 'missing_critical_headers' and 'extra_headers'.
                  Raises ValueError if critical headers are missing.
        """
        logger.info(f"Validating {len(actual_source_headers)} source headers against {len(self.expected_source_columns)} expected columns")
        actual_headers_set = set(actual_source_headers)
        missing_critical = self.expected_source_columns - actual_headers_set
        extra_headers = actual_headers_set - self.expected_source_columns

        if missing_critical:
            missing_list = sorted(list(missing_critical))
            logger.error(f"Critical columns missing: {', '.join(missing_list)}")
            raise ValueError(
                f"Critical columns from mapping are missing in the source data headers: "
                f"{missing_list}. Please check the source file or mapping."
            )
        
        if extra_headers:
            logger.info(f"Found {len(extra_headers)} extra headers not in mapping: {', '.join(sorted(list(extra_headers)))}")
        else:
            logger.info("All headers match expected columns exactly")
            
        result = {
            "missing_critical_headers": list(missing_critical), # Will be empty if error not raised
            "extra_headers": sorted(list(extra_headers)),
            "all_expected_present": not bool(missing_critical)
        }
        return result

    def _get_or_create_resource(self, defaults, **kwargs):
        try:
            resource, created = Resource.objects.get_or_create(defaults=defaults, **kwargs)
            if created:
                if 'uri' in kwargs:
                    logger.debug(f"Created Resource with URI: {kwargs['uri']}")
                elif 'literal_value' in kwargs:
                    logger.debug(f"Created Literal Resource: {kwargs['literal_value'][:30]}...")
                else:
                    logger.debug(f"Created Resource: {resource}")
            return resource
        except Exception as e:
            logger.error(f"Error creating resource: {str(e)}, defaults={defaults}, kwargs={kwargs}")
            raise

    def _get_or_create_rdf_term(self, term_name, description):
        logger.debug(f"Getting or creating RDF term: {term_name}")
        uri = f"{RDF_BASE_URI}{term_name}"
        return self._get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "RDF",
                'source_field': f"rdf:{term_name}",
                'literal_value': description 
            }
        )

    def _get_or_create_rdfs_term(self, term_name, description):
        logger.debug(f"Getting or creating RDFS term: {term_name}")
        uri = f"{RDFS_BASE_URI}{term_name}"
        return self._get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "RDFS",
                'source_field': f"rdfs:{term_name}",
                'literal_value': description
            }
        )

    def _get_or_create_cidoc_class_resource(self, class_short_name):
        logger.debug(f"Getting or creating CIDOC class: {class_short_name}")
        uri = f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        return self._get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.CLASS,
                'source': "CIDOC-CRM",
                'source_field': f"cidoc:{class_short_name}",
                'literal_value': f"CIDOC-CRM Class: {class_short_name}"
            }
        )

    def _get_or_create_cidoc_property_resource(self, property_short_name):
        logger.debug(f"Getting or creating CIDOC property: {property_short_name}")
        uri = f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        return self._get_or_create_resource(
            uri=uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "CIDOC-CRM",
                'source_field': f"cidoc:{property_short_name}",
                'literal_value': f"CIDOC-CRM Property: {property_short_name}"
            }
        )

    def _mint_uri(self, *parts):
        inst_code_slug = self._slugify_uri_part(self.institution_code)
        
        # Slugify all passed parts, filter out any that become empty after slugging (unless it's "n-a")
        processed_parts = [self._slugify_uri_part(p) for p in parts if p and self._slugify_uri_part(p)] 
        
        # Ensure there's at least one part to avoid URIs like base/institution//
        if not processed_parts:
            # This case should ideally be handled by callers ensuring they provide valid parts
            # or by having a default unique ID generation if all parts are empty/invalid.
            # For now, adding a fallback part. Could also raise an error.
            logger.warning("Minting URI with no valid parts, using default 'unidentified-resource' part.")
            processed_parts = ["unidentified-resource"] 

        uri = self.institution_base_uri + inst_code_slug + "/" + "/".join(processed_parts)
        logger.debug(f"Minted URI: {uri}")
        return uri

    def _infer_datatype(self, value):
        # Basic inference, extend as needed
        if isinstance(value, int):
            return f"{XSD_BASE_URI}integer"
        if isinstance(value, float):
            return f"{XSD_BASE_URI}float"
        # Try to parse as date
        if isinstance(value, str):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return f"{XSD_BASE_URI}date"
            except ValueError:
                pass
            try:
                datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
                return f"{XSD_BASE_URI}dateTime"
            except ValueError:
                pass
        return f"{XSD_BASE_URI}string"  # Default

    def _infer_language(self, rule, row_data):
        # Check for explicit language in the rule
        if 'language' in rule:
            lang = rule['language']
            logger.debug(f"Using explicit language from rule: {lang}")
            return lang
        
        # Check for language column reference
        lang_column = rule.get('language_column')
        if lang_column and lang_column in row_data:
            lang = row_data[lang_column]
            logger.debug(f"Using language from column '{lang_column}': {lang}")
            return lang
            
        # No language identified
        logger.debug("No language identified")
        return None

    def _split_multi_values(self, rule, value):
        """Splits a value into multiple values if needed based on the rule."""
        if not isinstance(value, str):
            logger.debug(f"Value is not a string, not splitting: {type(value)}")
            return [value]
            
        separator = rule.get('multi_value_separator')
        used_default_separator = False

        if not separator and rule.get('multi_valued') == True:
            separator = ';' # Default separator if multi_valued is true and no specific separator given
            used_default_separator = True
            logger.debug(f"Using default separator '{separator}' because 'multi_valued': True and no explicit separator found.")

        if separator:
            logger.debug(f"Splitting by {'default' if used_default_separator else 'explicit'} separator: '{separator}'")
            result = [val.strip() for val in value.split(separator) if val.strip()]
            logger.debug(f"Split into {len(result)} values")
            return result
            
        # Check for separator hint in the note only if no explicit/default separator was used
        note = rule.get('note', '').lower()
        if "separated by a ';'" in note: # This specific note implies semicolon
            logger.debug("Splitting by semicolon based on note hint")
            result = [val.strip() for val in value.split(';') if val.strip()]
            logger.debug(f"Split into {len(result)} values")
            return result
            
        # No splitting needed
        logger.debug("No splitting needed")
        return [value]

    def _lookup_related_data(self, rule, source_value):
        """
        Looks up related data based on the rule and source value.
        Returns a dictionary of found values or None if not applicable.
        """
        if not rule.get('lookup_type'):
            logger.debug("No lookup_type specified, skipping related data lookup")
            return None
            
        lookup_type = rule['lookup_type']
        logger.debug(f"Performing lookup of type: {lookup_type}")
        
        if lookup_type != 'related_table_literal':
            logger.warning(f"Unsupported lookup_type: {lookup_type}")
            return None
            
        related_source_name = rule.get('related_source')
        if not related_source_name or related_source_name not in self.related_sources:
            logger.warning(f"Related source '{related_source_name}' not found for lookup")
            return None
            
        related_source = self.related_sources[related_source_name]
        lookup_key_column = rule.get('related_source_key_column', 'id')
        lookup_value_column = rule.get('related_source_value_column')
        lookup_language_column = rule.get('related_source_language_column')
        
        logger.debug(f"Looking up value '{source_value}' in related source '{related_source_name}' "
                    f"key column: '{lookup_key_column}', value column: '{lookup_value_column}'")
        
        if not lookup_value_column:
            logger.warning("No value column specified for lookup in related source")
            return None
            
        # Simple implementation for list of dicts
        if isinstance(related_source, list):
            for item in related_source:
                if str(item.get(lookup_key_column)) == str(source_value):
                    result = {
                        'value': item.get(lookup_value_column)
                    }
                    if lookup_language_column and lookup_language_column in item:
                        result['language'] = item[lookup_language_column]
                    logger.debug(f"Found value in related source: {result}")
                    return result
                    
        logger.warning(f"Could not find value for '{source_value}' in related source")
        return None

    def import_data(self, source_data_iterator, primary_subject_class_short_name):
        """
        Imports data from a source iterator based on the loaded mapping.
        Assumes headers have been pre-validated if necessary.
        source_data_iterator: An iterator yielding dictionaries (rows of data).
        primary_subject_class_short_name: The CIDOC-CRM short name for the main entity 
                                          being described by each row (e.g., "E7_Activity").
        Returns:
            dict: Statistics about the import process including success and error counts
        """
        logger.info(f"Starting import with primary subject class: {primary_subject_class_short_name}")
        
        effective_primary_class = primary_subject_class_short_name
        if not effective_primary_class and self.default_domain_class:
            logger.info(f"Using default domain class from mapping: {self.default_domain_class}")
            effective_primary_class = self.default_domain_class
        elif not effective_primary_class:
            logger.error("No primary subject class provided (either as argument or as 'domain' in mapping)")
            raise ValueError("Primary subject class must be provided either as an argument or as a 'domain' in the mapping file.")

        primary_subject_class_resource = self._get_or_create_cidoc_class_resource(effective_primary_class)
        
        # Statistics counters
        stats = {
            "total_rows": 0,
            "successful_rows": 0,
            "failed_rows": 0,
            "errors": []
        }

        for i, row_data in enumerate(source_data_iterator):
            row_num = i + 1
            stats["total_rows"] += 1
            logger.info(f"Processing row {row_num}")
            logger.debug(f"Row data: {row_data}")
            
            try:
                self._import_single_row(row_data, row_num, primary_subject_class_resource)
                stats["successful_rows"] += 1
                logger.info(f"Successfully processed row {row_num}")
            except Exception as e:
                stats["failed_rows"] += 1
                error_info = {
                    "row": row_num,
                    "error": str(e),
                    "data": row_data
                }
                stats["errors"].append(error_info)
                logger.error(f"Error processing row {row_num}: {str(e)}", exc_info=True)
        
        logger.info(f"Import completed. Successful: {stats['successful_rows']}, Failed: {stats['failed_rows']}")
        if stats["failed_rows"] > 0:
            logger.warning(f"Failed to import {stats['failed_rows']} rows. Check 'errors' in returned stats for details.")
        return stats

    @transaction.atomic
    def _import_single_row(self, row_data, row_num, primary_subject_class_resource):
        """
        Import a single row of data as an atomic operation.
        If an error occurs, only this row's transaction will be rolled back.
        """
        logger.debug(f"Starting atomic import for row {row_num}")
        
        # A. Create/Identify the Main Subject Resource
        original_id_val = row_data.get('id') or row_data.get('Ereignis-ID') or f"row_{row_num}" # Fallback
        logger.debug(f"Using ID: {original_id_val} for row {row_num}")
        
        # Use primary subject class name for context in URI
        # Assumes source_field like "cidoc:E7_Activity" or just "E7_Activity"
        primary_class_name_part = primary_subject_class_resource.source_field.split(':')[-1]
        
        subject_uri = self._mint_uri(primary_class_name_part, original_id_val)
            
        logger.info(f"Creating primary subject resource with URI: {subject_uri}")
        event_subject_resource = self._get_or_create_resource(
            uri=subject_uri,
            defaults={
                'resource_type': ResourceType.IRI,
                'source': self.institution_code,
                'source_field': f"original_id={original_id_val}"
            }
        )

        # Assert primary type for the event subject
        logger.debug(f"Asserting rdf:type {primary_subject_class_resource.uri} for subject")
        Triple.objects.get_or_create(
            subject=event_subject_resource,
            predicate=self.rdf_type_resource,
            object=primary_subject_class_resource
        )
        
        # B. Iterate Through Each mapping Rule
        rule_count = len(self.mappings)
        logger.debug(f"Processing {rule_count} mapping rules for row {row_num}")
        for rule_idx, rule in enumerate(self.mappings):
            logger.debug(f"Processing rule {rule_idx+1}/{rule_count}")
            self._process_mapping_rule(rule, row_data, event_subject_resource)
            
        logger.debug(f"Completed atomic import for row {row_num}")
        return event_subject_resource

    def _process_mapping_rule(self, rule, row_data, event_subject_resource):
        source_column_name = rule.get('source_column')
        if not source_column_name or source_column_name not in row_data:
            logger.debug(f"Skipping rule: source_column '{source_column_name}' not in row data or not defined")
            return

        source_values_raw = row_data[source_column_name]
        if source_values_raw is None:
            logger.debug(f"Skipping rule: source_column '{source_column_name}' has None value")
            return
            
        # Handle multi-value columns
        source_values = self._split_multi_values(rule, source_values_raw)
        if not source_values:
            logger.debug(f"Skipping rule: no values after splitting for '{source_column_name}'")
            return

        predicate_short_name = rule.get('predicate')
        if not predicate_short_name:
            logger.warning(f"Skipping rule: no 'predicate' defined for column '{source_column_name}'")
            return
        
        logger.debug(f"Getting predicate resource for '{predicate_short_name}'")
        predicate_resource = self._get_or_create_cidoc_property_resource(predicate_short_name)

        for source_value in source_values:
            # Skip empty values
            if isinstance(source_value, str) and not source_value.strip():
                logger.debug(f"Skipping empty string value for column '{source_column_name}'")
                continue
                
            logger.debug(f"Processing source value: '{source_value}' for column '{source_column_name}'")
            object_resource = None
            
            # Determine Object Resource
            object_class_short_name = rule.get('object_class')
            object_column_name = rule.get('object_column')  # For linked resources

            # Check for lookup in related sources
            related_value = None
            if rule.get('lookup_type'):
                logger.debug(f"Attempting related data lookup for '{source_value}'")
                related_data = self._lookup_related_data(rule, source_value)
                if related_data and 'value' in related_data:
                    related_value = related_data['value']
                    related_language = related_data.get('language')
                    
                    logger.debug(f"Creating literal resource from looked-up value: '{related_value}'")
                    # Create literal for the looked-up value
                    object_resource = self._get_or_create_resource(
                        literal_value=str(related_value),
                        resource_type=ResourceType.LITERAL,
                        literal_language=related_language,
                        literal_datatype=self._infer_datatype(related_value),
                        defaults={
                            'source': self.institution_code,
                            'source_field': f"{source_column_name}={source_value}→{related_value}"
                        }
                    )
            
            # If we created a resource from a lookup, skip the rest of the processing
            if object_resource:
                logger.debug("Using object resource from lookup, skipping other processing paths")
                pass
                
            # Linked Resources (IRI object identified by source_value)
            elif rule.get('link_columns') and object_column_name and object_class_short_name:
                logger.debug(f"Processing as linked resource with class '{object_class_short_name}'")
                # Slugify the class name for the URI path
                linked_object_uri_class_part = self._slugify_uri_part(object_class_short_name)
                object_uri = self._mint_uri(linked_object_uri_class_part, str(source_value))
                
                logger.debug(f"Creating linked resource with URI: {object_uri}")
                object_resource = self._get_or_create_resource(
                    uri=object_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'source': self.institution_code,
                        'source_field': f"{object_column_name}={source_value}"
                    }
                )
                
                # Type the linked object resource
                linked_object_class_resource = self._get_or_create_cidoc_class_resource(object_class_short_name)
                logger.debug(f"Asserting rdf:type {linked_object_class_resource.uri} for linked resource")
                Triple.objects.get_or_create(
                    subject=object_resource,
                    predicate=self.rdf_type_resource,
                    object=linked_object_class_resource
                )
            
            # Intermediate IRI with literal property (object_class present but no link_columns)
            elif object_class_short_name:
                logger.debug(f"Processing as intermediate resource with class '{object_class_short_name}'")
                
                intermediate_uri_class_part = self._slugify_uri_part(object_class_short_name)
                primary_subject_class_slug = self._slugify_uri_part(event_subject_resource.uri.split('/')[-2]) # Context part from subject URI
                primary_subject_id_slug = event_subject_resource.uri.split('/')[-1] # ID part from subject URI, should be already slugged by its own minting

                intermediate_instance_uri = self._mint_uri(
                    primary_subject_class_slug, 
                    primary_subject_id_slug,
                    intermediate_uri_class_part,
                    str(source_value)[:50] 
                )

                logger.debug(f"Creating intermediate resource with URI: {intermediate_instance_uri}")
                intermediate_resource = self._get_or_create_resource(
                    uri=intermediate_instance_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'source': self.institution_code,
                        'source_field': f"{source_column_name}_instance_for_{str(source_value)[:30]}"
                    }
                )
                object_resource = intermediate_resource  # This is the object of the main triple

                # Type the intermediate instance
                intermediate_class_r = self._get_or_create_cidoc_class_resource(object_class_short_name)
                logger.debug(f"Asserting rdf:type {intermediate_class_r.uri} for intermediate resource")
                Triple.objects.get_or_create(
                    subject=intermediate_resource,
                    predicate=self.rdf_type_resource,
                    object=intermediate_class_r
                )

                # Process object_properties for the intermediate resource
                object_properties = rule.get('object_properties', [])
                if object_properties:
                    logger.debug(f"Processing {len(object_properties)} object_properties for intermediate resource {intermediate_resource.uri}")
                    for sub_rule in object_properties:
                        self._process_sub_rule(sub_rule, row_data, intermediate_resource, source_value, intermediate_uri_class_part)
                
                # Fallback behaviors if no object_properties were given
                elif object_class_short_name == "E52_Time-Span":
                    logger.debug(f"Applying default E52_Time-Span processing for {intermediate_resource.uri} using value '{source_value}'")
                    self._process_time_span(intermediate_resource, source_value, source_column_name, row_data, rule)
                else:
                    # Default: Label the intermediate instance with the actual source value of the parent rule
                    logger.debug(f"Applying default rdfs:label for {intermediate_resource.uri} using value '{source_value}'")
                    literal_language = self._infer_language(rule, row_data) # Use parent rule's context for language
                    literal_datatype = self._infer_datatype(source_value)
                    
                    label_literal_r = self._get_or_create_resource(
                        literal_value=str(source_value),
                        resource_type=ResourceType.LITERAL,
                        literal_language=literal_language,
                        literal_datatype=literal_datatype,
                        defaults={
                            'source': self.institution_code,
                            'source_field': f"{source_column_name}={str(source_value)}"
                        }
                    )
                    Triple.objects.get_or_create(
                        subject=intermediate_resource,
                        predicate=self.rdfs_label_resource,
                        object=label_literal_r
                    )
            
            # Direct Literal (no object_class or linked resource)
            else:
                logger.debug(f"Processing as direct literal: '{source_value}'")
                literal_language = self._infer_language(rule, row_data)
                literal_datatype = self._infer_datatype(source_value)
                
                object_resource = self._get_or_create_resource(
                    literal_value=str(source_value),
                    resource_type=ResourceType.LITERAL,
                    literal_language=literal_language,
                    literal_datatype=literal_datatype,
                    defaults={
                        'source': self.institution_code,
                        'source_field': f"{source_column_name}={str(source_value)}"
                    }
                )

            # Create the final triple connecting subject -> predicate -> object
            if object_resource:
                logger.debug(f"Creating triple: {event_subject_resource.uri} -> {predicate_resource.uri} -> {getattr(object_resource, 'uri', object_resource.literal_value)}")
                Triple.objects.get_or_create(
                    subject=event_subject_resource,
                    predicate=predicate_resource,
                    object=object_resource
                )
            else:
                logger.warning(f"No object resource created for source value: '{source_value}'")

    def _process_sub_rule(self, sub_rule, row_data, subject_resource, parent_source_value, parent_intermediate_uri_part):
        """
        Processes a sub-rule defined in 'object_properties'.
        Creates triples where subject_resource (an intermediate IRI) is the subject.
        parent_source_value is the value from the parent rule's source_column, usable via 'use_parent_value'.
        parent_intermediate_uri_part is the ALREADY SLUGIFIED uri part from parent rule's object_class for context in minting.
        """
        sub_source_column = sub_rule.get('source_column')
        sub_value_raw = None

        if sub_source_column and sub_source_column in row_data:
            sub_value_raw = row_data[sub_source_column]
            logger.debug(f"Sub-rule: using value '{sub_value_raw}' from column '{sub_source_column}'")
        elif 'fixed_value' in sub_rule:
            sub_value_raw = sub_rule['fixed_value']
            logger.debug(f"Sub-rule: using fixed_value '{sub_value_raw}'")
        elif sub_rule.get('use_parent_value', False):
            sub_value_raw = parent_source_value
            logger.debug(f"Sub-rule: using parent_source_value '{sub_value_raw}'")
        else:
            logger.warning(f"Sub-rule for {subject_resource.uri} lacks 'source_column', 'fixed_value', or 'use_parent_value'. Sub-rule: {sub_rule}")
            return

        if sub_value_raw is None: # Note: allow empty strings if that's intended (e.g. for fixed_value="")
            logger.debug(f"Skipping sub-rule: value is None. Sub-rule: {sub_rule}")
            return

        sub_values = self._split_multi_values(sub_rule, sub_value_raw)

        sub_predicate_short_name = sub_rule.get('predicate')
        if not sub_predicate_short_name:
            logger.warning(f"Skipping sub-rule for {subject_resource.uri}: no 'predicate' defined. Sub-rule: {sub_rule}")
            return

        sub_predicate_resource = None
        if sub_predicate_short_name == "rdf:type":
            sub_predicate_resource = self.rdf_type_resource
        elif sub_predicate_short_name == "rdfs:label":
            sub_predicate_resource = self.rdfs_label_resource
        else:
            actual_prop_name = sub_predicate_short_name.split(':')[-1]
            sub_predicate_resource = self._get_or_create_cidoc_property_resource(actual_prop_name)
        
        if not sub_predicate_resource:
            logger.error(f"Failed to get/create predicate resource for '{sub_predicate_short_name}' in sub-rule for {subject_resource.uri}.")
            return


        for i, sub_value in enumerate(sub_values):
            # Allow processing of empty strings if they resulted from split or were fixed_value
            # if isinstance(sub_value, str) and not sub_value.strip() and sub_value_raw != "": # Careful with this condition
            #     logger.debug(f"Skipping empty string sub_value for {sub_predicate_short_name} (original: '{sub_value_raw}')")
            #     continue
            
            logger.debug(f"Sub-rule processing value '{sub_value}' for predicate '{sub_predicate_short_name}' on {subject_resource.uri}")

            sub_object_resource = None
            sub_object_class = sub_rule.get('object_class')
            sub_object_uri_pattern = sub_rule.get('object_uri_pattern')

            if sub_object_uri_pattern:
                object_uri = sub_object_uri_pattern.replace("{value}", str(sub_value).strip())
                logger.debug(f"Sub-rule: object is external IRI '{object_uri}' from pattern")
                sub_object_resource = self._get_or_create_resource(
                    uri=object_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'source': self.institution_code, # Or specific source from sub_rule
                        'source_field': f"sub_uri_pattern_{actual_prop_name}={sub_value}"
                    }
                )
                if sub_object_class: # Optionally type this external IRI
                    type_res = self._get_or_create_cidoc_class_resource(sub_object_class)
                    Triple.objects.get_or_create(
                        subject=sub_object_resource, predicate=self.rdf_type_resource, object=type_res
                    )
            elif sub_object_class:
                # Mint URI relative to the subject_resource (the intermediate node) and current sub-value
                # parent_intermediate_uri_part is already a slug (e.g., "e41-appellation")
                # subject_resource ID is already a slug
                sub_object_class_slug = self._slugify_uri_part(sub_object_class)
                current_subject_id_slug = subject_resource.uri.split('/')[-1]

                sub_instance_uri = self._mint_uri(
                    current_subject_id_slug, 
                    parent_intermediate_uri_part, 
                    sub_object_class_slug, 
                    str(sub_value)[:50],
                    f"prop-{i}" # Ensure uniqueness part is also somewhat slug-friendly
                )
                logger.debug(f"Sub-rule: object is new IRI '{sub_instance_uri}' of type '{sub_object_class}'")
                sub_object_resource = self._get_or_create_resource(
                    uri=sub_instance_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'source': self.institution_code,
                        'source_field': f"{sub_source_column or 'fixed_val'}_as_{sub_object_class}"
                    }
                )
                sub_instance_class_r = self._get_or_create_cidoc_class_resource(sub_object_class)
                Triple.objects.get_or_create(
                    subject=sub_object_resource, predicate=self.rdf_type_resource, object=sub_instance_class_r
                )
                # Automatically label this new IRI with its generating sub_value if it's a simple type
                if isinstance(sub_value, (str, int, float)) and not sub_rule.get('no_auto_label', False):
                    label_lang = self._infer_language(sub_rule, row_data)
                    label_dtype = self._infer_datatype(sub_value)
                    label_lit_res = self._get_or_create_resource(
                        literal_value=str(sub_value), resource_type=ResourceType.LITERAL,
                        literal_language=label_lang, literal_datatype=label_dtype,
                        defaults={'source': self.institution_code, 'source_field': f"auto_label_for_{sub_object_class_slug}"}
                    )
                    Triple.objects.get_or_create(
                        subject=sub_object_resource, predicate=self.rdfs_label_resource, object=label_lit_res
                    )
            else:
                # Default: The object of the sub-property is a Literal.
                sub_literal_language = self._infer_language(sub_rule, row_data)
                sub_literal_datatype = self._infer_datatype(sub_value)
                logger.debug(f"Sub-rule: object is Literal '{sub_value}' lang={sub_literal_language} type={sub_literal_datatype}")
                sub_object_resource = self._get_or_create_resource(
                    literal_value=str(sub_value),
                    resource_type=ResourceType.LITERAL,
                    literal_language=sub_literal_language,
                    literal_datatype=sub_literal_datatype,
                    defaults={
                        'source': self.institution_code,
                        'source_field': f"{sub_source_column or 'fixed_val'}_{actual_prop_name}={str(sub_value)}"
                    }
                )
            
            if sub_object_resource:
                Triple.objects.get_or_create(
                    subject=subject_resource,
                    predicate=sub_predicate_resource,
                    object=sub_object_resource
                )
            else:
                logger.warning(f"Sub-rule: no object resource created for predicate '{sub_predicate_short_name}', value '{sub_value}' on {subject_resource.uri}")

    def _process_time_span(self, time_span_resource, date_value, source_column_name, row_data, rule):
        """
        Process a time span entity with appropriate begin/end properties.
        """
        logger.debug(f"Processing time span for date value: '{date_value}'")
        
        # Skip empty date values
        if isinstance(date_value, str) and not date_value.strip():
            logger.debug(f"Skipping empty date value for time span")
            return
            
        # Try to parse the date string
        try:
            # Parse the date - adjust format as needed
            date_obj = datetime.strptime(date_value, "%Y-%m-%d")
            logger.debug(f"Successfully parsed date: {date_obj}")
            
            # Check if this is a start or end date based on the column name or rule
            is_start = "beginn" in source_column_name.lower() or rule.get('is_start_date', True)
            logger.debug(f"Treating as {'start' if is_start else 'end'} date based on {'column name' if 'beginn' in source_column_name.lower() else 'rule default'}")
            
            # Create the appropriate literal for the date
            date_literal = self._get_or_create_resource(
                literal_value=date_value,
                resource_type=ResourceType.LITERAL,
                literal_datatype=f"{XSD_BASE_URI}date",
                defaults={
                    'source': self.institution_code,
                    'source_field': f"{source_column_name}={date_value}"
                }
            )
            
            # Get the appropriate properties from the rule or use defaults
            if is_start:
                # Use the rule-specified properties or default to CIDOC time properties
                begin_property = rule.get('begin_property', 'P82a_begin_of_the_begin')
                logger.debug(f"Using begin property: {begin_property}")
                begin_predicate = self._get_or_create_cidoc_property_resource(begin_property)
                
                Triple.objects.get_or_create(
                    subject=time_span_resource,
                    predicate=begin_predicate,
                    object=date_literal
                )
                
                # Check for approximation qualifier
                approx_column = rule.get('approximation_column')
                if approx_column and approx_column in row_data and row_data[approx_column]:
                    approx_value = str(row_data[approx_column])
                    if approx_value.lower() in ('true', 'yes', '1', 'y'):
                        logger.debug(f"Date is approximate based on column: {approx_column}")
                        approx_literal = self._get_or_create_resource(
                            literal_value="approximate",
                            resource_type=ResourceType.LITERAL,
                            defaults={
                                'source': self.institution_code,
                                'source_field': f"{approx_column}=true"
                            }
                        )
                        
                        # Use rule-specified qualification property or default
                        begin_qual_property = rule.get('begin_qualification_property', 'P79_beginning_is_qualified_by')
                        logger.debug(f"Using qualification property: {begin_qual_property}")
                        begin_qual_predicate = self._get_or_create_cidoc_property_resource(begin_qual_property)
                        
                        Triple.objects.get_or_create(
                            subject=time_span_resource,
                            predicate=begin_qual_predicate,
                            object=approx_literal
                        )
            else:
                # Use the rule-specified properties or default to CIDOC time properties
                end_property = rule.get('end_property', 'P82b_end_of_the_end')
                logger.debug(f"Using end property: {end_property}")
                end_predicate = self._get_or_create_cidoc_property_resource(end_property)
                
                Triple.objects.get_or_create(
                    subject=time_span_resource,
                    predicate=end_predicate,
                    object=date_literal
                )
                
                # Check for approximation qualifier
                approx_column = rule.get('approximation_column')
                if approx_column and approx_column in row_data and row_data[approx_column]:
                    approx_value = str(row_data[approx_column])
                    if approx_value.lower() in ('true', 'yes', '1', 'y'):
                        logger.debug(f"Date is approximate based on column: {approx_column}")
                        approx_literal = self._get_or_create_resource(
                            literal_value="approximate",
                            resource_type=ResourceType.LITERAL,
                            defaults={
                                'source': self.institution_code,
                                'source_field': f"{approx_column}=true"
                            }
                        )
                        
                        # Use rule-specified qualification property or default
                        end_qual_property = rule.get('end_qualification_property', 'P80_end_is_qualified_by')
                        logger.debug(f"Using qualification property: {end_qual_property}")
                        end_qual_predicate = self._get_or_create_cidoc_property_resource(end_qual_property)
                        
                        Triple.objects.get_or_create(
                            subject=time_span_resource,
                            predicate=end_qual_predicate,
                            object=approx_literal
                        )
                
        except ValueError:
            # If date parsing fails, fall back to using the value as a plain label
            logger.warning(f"Could not parse date '{date_value}', using as plain label")
            label_literal = self._get_or_create_resource(
                literal_value=date_value,
                resource_type=ResourceType.LITERAL,
                defaults={
                    'source': self.institution_code,
                    'source_field': f"{source_column_name}={date_value}"
                }
            )
            Triple.objects.get_or_create(
                subject=time_span_resource,
                predicate=self.rdfs_label_resource,
                object=label_literal
            )

    def validate_csv_headers(self, csv_fieldnames):
        """Validates CSV field names against expected columns"""
        logger.info(f"Validating CSV headers: {csv_fieldnames}")
        return self.validate_source_headers(csv_fieldnames)

# Example Usage (you would call this from a management command or a view)
# if __name__ == '__main__':
#     # This is illustrative; Django setup needed to run this directly
#     # Ensure Django is configured:
#     # import django
#     # import os
#     # os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arkumu.config.settings.local')
#     # django.setup()
# 
#     importer = JSONMappingImporter(mapping_file_path='path_to_your/Ereignis.json')
#     
#     # Mock source data
#     mock_data = [
#         {
#             'id': 'event1',
#             'Ereignistyp': '123', # Assuming this links to an event_type_id
#             'Deutscher Ereignisname': 'Eröffnung der Großen Kunstausstellung',
#             'Ereignisbeginn': '2023-01-15',
#             # ... other columns from Ereignis.json source_columns
#             'Ereignisort': 'wd:Q64; wd:Q1794', # Example multi-value for place_wikidata_id
#             'NotAColumn': 'some data' # To test skipping
#         },
#         {
#             'id': 'event2',
#             'Ereignistyp': '456',
#             'Deutscher Ereignisname': 'Konzertabend',
#             'Ereignisbeschreibung-ID': 'desc1; desc2', # Example for link_columns + multi-value
#             # ...
#         }
#     ]
#     importer.import_data(mock_data, primary_subject_class_short_name="E7_Activity")
