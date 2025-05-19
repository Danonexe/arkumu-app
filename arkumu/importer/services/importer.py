import json
import logging
from django.db import transaction
from arkumu.metadata.models import ResourceType, Triple

from arkumu.importer.services.uri_utils import (
    RDF_BASE_URI, RDFS_BASE_URI, CIDOC_CRM_BASE_URI, XSD_BASE_URI, OWL_BASE_URI, DEFAULT_INSTITUTION_BASE_URI,
    slugify_uri_part, mint_uri
)
from arkumu.importer.services.data_utils import (
    extract_expected_source_columns,
    validate_source_headers,
    infer_datatype,
    infer_language,
    split_multi_values,
    lookup_related_data
)
from arkumu.importer.services.resource_manager import ResourceManager
from arkumu.importer.services.rule_processor import MappingRuleProcessor

# Setup logger
logger = logging.getLogger(__name__)


class JSONMappingImporter:
    """
    JSONMappingImporter handles importing data based on JSON mapping configurations.

    The importer supports reference validation between related datasets through
    the 'strict_references' option. When enabled, references to non-existent
    entities will cause the import to skip those relationships.

    Args:
        mapping_file_path: Path to the JSON mapping file
        institution_base_uri: Optional base URI for the institution
        related_sources: Dictionary of related data sources for reference validation
        strict_references: If True, invalid references will be skipped (default: False)
    """
    def __init__(self, mapping_file_path, institution_base_uri=None, related_sources=None, strict_references=False):
        logger.info(f"Initializing JSONMappingImporter with mapping file: {mapping_file_path}")
        try:
            with open(mapping_file_path, 'r') as f:
                self.mapping_config = json.load(f)
            
            self.institution_code = self.mapping_config.get("institution")
            if not self.institution_code:
                logger.error("Missing 'institution' code in mapping JSON")
                raise ValueError("Mapping JSON must contain an 'institution' code.")
            self.institution_code_slug = slugify_uri_part(self.institution_code) # Pre-slugify

            # Use DEFAULT_INSTITUTION_BASE_URI from uri_utils
            self.institution_base_uri = institution_base_uri or DEFAULT_INSTITUTION_BASE_URI 
            if not self.institution_base_uri.endswith('/'):
                self.institution_base_uri += '/'
            
            # Instantiate ResourceManager
            self.resource_manager = ResourceManager(institution_code=self.institution_code)

            self.default_domain_class = self.mapping_config.get("domain")
            if self.default_domain_class:
                logger.info(f"Default domain class from mapping: {self.default_domain_class}")
            
            self.source_format = self.mapping_config.get("source_format", "N/A")
            self.mappings = self.mapping_config.get("mappings", [])
            logger.debug(f"Loaded {len(self.mappings)} mapping rules")
            
            # Use data_utils.extract_expected_source_columns
            self.expected_source_columns = extract_expected_source_columns(self.mappings)
            logger.debug(f"Extracted {len(self.expected_source_columns)} expected source columns")
            
            self.related_sources = related_sources or {}
            self.strict_references = strict_references
            logger.debug(f"Initialized with {len(self.related_sources)} related sources and strict_references={strict_references}")

            logger.debug("Pre-caching common RDF resources using ResourceManager")
            self.rdf_type_resource = self.resource_manager.get_or_create_rdf_term("type", "RDF type property")
            self.rdfs_label_resource = self.resource_manager.get_or_create_rdfs_term("label", "RDFS label property")
            self.owl_sameas_resource = self.resource_manager.get_or_create_owl_term("sameAs", "OWL sameAs property")
            logger.info(f"JSONMappingImporter initialized successfully for institution: {self.institution_code}")

            # Initialize Rule Processor
            self.rule_processor = MappingRuleProcessor(
                resource_manager=self.resource_manager,
                institution_base_uri=self.institution_base_uri,
                institution_code_slug=self.institution_code_slug,
                institution_code=self.institution_code,
                rdf_type_resource=self.rdf_type_resource,
                rdfs_label_resource=self.rdfs_label_resource,
                owl_sameas_resource=self.owl_sameas_resource,
                related_sources=self.related_sources,
                strict_references=self.strict_references
            )

        except Exception as e:
            logger.exception(f"Failed to initialize JSONMappingImporter: {str(e)}")
            raise

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

    def validate_csv_headers(self, csv_fieldnames):
        """Validates CSV field names against expected columns. Wrapper for data_utils function."""
        logger.info(f"Validating CSV headers: {csv_fieldnames}")
        # Uses self.expected_source_columns which is instance data
        return validate_source_headers(self.expected_source_columns, csv_fieldnames)

    def import_data(self, source_data_iterator, primary_subject_class_short_name, strict_references=None):
        """
        Imports data from a source iterator based on the loaded mapping.
        Assumes headers have been pre-validated if necessary.
        
        Args:
            source_data_iterator: An iterator yielding dictionaries (rows of data).
            primary_subject_class_short_name: The CIDOC-CRM short name for the main entity 
                                            being described by each row (e.g., "E7_Activity").
            strict_references: Override the instance setting for strict reference checking
            
        Returns:
            dict: Statistics about the import process including success and error counts
        """
        if strict_references is not None:
            # Override the instance setting if provided
            original_strict_setting = self.strict_references
            self.strict_references = strict_references
            logger.info(f"Temporarily overriding strict_references setting to {strict_references}")
        
        logger.info(f"Starting import with primary subject class: {primary_subject_class_short_name}")
        
        effective_primary_class = primary_subject_class_short_name
        if not effective_primary_class and self.default_domain_class:
            logger.info(f"Using default domain class from mapping: {self.default_domain_class}")
            effective_primary_class = self.default_domain_class
        elif not effective_primary_class:
            logger.error("No primary subject class provided (either as argument or as 'domain' in mapping)")
            raise ValueError("Primary subject class must be provided either as an argument or as a 'domain' in the mapping file.")

        primary_subject_class_resource = self.resource_manager.get_or_create_cidoc_class_resource(effective_primary_class)
        
        # Statistics counters
        stats = {
            "total_rows": 0,
            "successful_rows": 0,
            "failed_rows": 0,
            "reference_warnings": 0,
            "reference_errors": 0,
            "errors": []
        }

        for i, row_data in enumerate(source_data_iterator):
            row_num = i + 1
            stats["total_rows"] += 1
            logger.info(f"Processing row {row_num}")
            logger.debug(f"Row data: {row_data}")
            
            try:
                self._import_single_row(row_data, row_num, primary_subject_class_resource, stats)
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
        
        # If we overrode the setting, restore it at the end
        if strict_references is not None:
            self.strict_references = original_strict_setting
        
        return stats

    @transaction.atomic
    def _import_single_row(self, row_data, row_num, primary_subject_class_resource, stats=None):
        """
        Import a single row of data as an atomic operation.
        If an error occurs, only this row's transaction will be rolled back.
        
        Args:
            row_data: The data for this row
            row_num: The row number for logging purposes
            primary_subject_class_resource: The main subject class resource
            stats: Dictionary to track import statistics
        """
        logger.debug(f"Starting atomic import for row {row_num}")
        
        # A. Create/Identify the Main Subject Resource using anchor_column if defined
        original_id_val = None
        
        # Check for anchor_column in mapping configuration
        anchor_column = self.mapping_config.get("anchor_column")
        if anchor_column and anchor_column in row_data:
            original_id_val = row_data[anchor_column]
            logger.info(f"Using anchor column '{anchor_column}' with value '{original_id_val}' for row {row_num}")
        
        # Fallbacks if anchor_column not found or empty
        if not original_id_val:
            original_id_val = row_data.get('id') or row_data.get('Ereignis-ID') or f"row_{row_num}" # Legacy fallbacks
            logger.debug(f"No anchor_column defined or empty value - using fallback ID: {original_id_val} for row {row_num}")
        
        # Use primary subject class name for context in URI
        # Assumes source_field like "cidoc:E7_Activity" or just "E7_Activity"
        primary_class_name_part = primary_subject_class_resource.source_field.split(':')[-1]
        
        # Extract just the part after the underscore for more semantic URIs (e.g. "Activity" from "E7_Activity")
        if '_' in primary_class_name_part:
            primary_class_name_part = primary_class_name_part.split('_', 1)[1]
            logger.debug(f"Using semantic part of class name for URI: {primary_class_name_part}")
        
        # Use uri_utils.mint_uri
        subject_uri = mint_uri(self.institution_base_uri, self.institution_code_slug, 
                                 primary_class_name_part, original_id_val)
            
        logger.info(f"Creating primary subject resource with URI: {subject_uri}")
        event_subject_resource = self.resource_manager.get_or_create_resource(
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
            logger.debug(f"Processing rule {rule_idx+1}/{rule_count} for row {row_num}")
            self.rule_processor.process_mapping_rule(rule, row_data, event_subject_resource, row_num, stats)
            
        logger.debug(f"Completed atomic import for row {row_num}")
        return event_subject_resource

    def _create_rdr_for_value(self, source_column_name, source_value, row_num):
        """
        Creates or retrieves an RDR for a given source column and value.
        Returns a tuple (rdr_object, rdr_uri_slugified_column) or None if creation fails.
        """
        logger.debug(f"Row {row_num}: Attempting to create RDR for column '{source_column_name}', value '{source_value}'")
        # Use uri_utils.slugify_uri_part
        rdr_uri_slugified_column = slugify_uri_part(source_column_name)
        rdr_uri_slugified_value = slugify_uri_part(str(source_value))

        if not rdr_uri_slugified_column or not rdr_uri_slugified_value:
            logger.warning(f"Row {row_num}: Skipping RDR creation for column '{source_column_name}' due to empty slug component (col: '{rdr_uri_slugified_column}', val: '{rdr_uri_slugified_value}'). Original value: '{source_value}'")
            return None

        # Use uri_utils.mint_uri
        rdr_uri = mint_uri(self.institution_base_uri, self.institution_code_slug, 
                           rdr_uri_slugified_column, rdr_uri_slugified_value)
        rdr_defaults = {
            'resource_type': ResourceType.IRI,
            'source': self.institution_code,
            'source_field': f"{source_column_name}_rdr={source_value}"
        }
        try:
            rdr_object = self.resource_manager.get_or_create_resource(uri=rdr_uri, defaults=rdr_defaults)
            logger.debug(f"Row {row_num}: Successfully created/got RDR: {rdr_object.uri}")
            return rdr_object, rdr_uri_slugified_column
        except Exception as e:
            logger.error(f"Row {row_num}: Exception during RDR resource creation for URI {rdr_uri}: {e}", exc_info=True)
            return None

    def _conditionally_label_rdr_object(self, rdr_object, rule, row_data, source_value, predicate_resource_of_main_rule, rdr_uri_slugified_column, row_num):
        """
        Adds an rdfs:label to the RDR if the main rule implies a literal object.
        This happens if the main rule's predicate is rdfs:label (and not targeting an IRI object),
        or if the main rule's range is 'literal'.
        """
        rule_range = rule.get('range')
        rule_object_class = rule.get('object_class')
        rule_uri_prefix = rule.get('uri_prefix')

        # Condition: If the original rule intended a literal (e.g. predicate was rdfs:label or range was 'literal'),
        # then this RDR (which is the object of that predicate) should get an rdfs:label with the source_value.
        if (predicate_resource_of_main_rule == self.rdfs_label_resource and 
            not rule_object_class and 
            not (rule_range == 'uri' and rule_uri_prefix)) or \
           (rule_range == 'literal'):
            
            logger.debug(f"Row {row_num}: RDR {rdr_object.uri} will get an rdfs:label as original rule intended a literal.")
            # Use data_utils.infer_language
            rdr_label_language = infer_language(rule, row_data)
            rdr_label_datatype = None
            if not rdr_label_language:
                rdr_label_datatype = f"{XSD_BASE_URI}string"
            
            try:
                rdr_actual_label_literal = self.resource_manager.get_or_create_resource(
                    literal_value=str(source_value),
                    resource_type=ResourceType.LITERAL,
                    literal_language=rdr_label_language,
                    literal_datatype=rdr_label_datatype,
                    defaults={'source': self.institution_code, 'source_field': f"value_as_label_for_rdr_{rdr_uri_slugified_column}={source_value}"}
                )
                Triple.objects.get_or_create(
                    subject=rdr_object, # The RDR gets the label
                    predicate=self.rdfs_label_resource,
                    object=rdr_actual_label_literal
                )
                logger.debug(f"Row {row_num}: Added rdfs:label '{str(source_value)}' to RDR {rdr_object.uri}")
            except Exception as e:
                logger.error(f"Row {row_num}: Failed to add rdfs:label to RDR {rdr_object.uri}: {e}", exc_info=True)
        else:
            logger.debug(f"Row {row_num}: RDR {rdr_object.uri} will not be auto-labeled based on main rule predicate/range.")

    def _apply_additional_semantics_to_rdr(self, rdr_object, rule, row_data, source_value, rdr_uri_slugified_column, row_num):
        """
        Applies further semantic meaning to an RDR, such as CIDOC typing, owl:sameAs links,
        or processing object_properties.
        """
        logger.debug(f"Row {row_num}: Applying additional semantics to RDR {rdr_object.uri}")
        rule_range = rule.get('range')
        rule_object_class = rule.get('object_class')
        rule_uri_prefix = rule.get('uri_prefix')

        # Determine semantic class for the RDR if specified
        object_class_short_name = rule_object_class 
        if not object_class_short_name and rule_range and rule_range not in ('literal', 'uri'):
            object_class_short_name = rule_range

        # Handle various semantic enrichments
        if rule.get('lookup_type'): # Note: Lookup currently only logs a warning.
            logger.debug(f"Row {row_num}: Attempting related data lookup for '{source_value}' to describe RDR {rdr_object.uri}")
            # Use data_utils.lookup_related_data, passing self.related_sources
            related_data = lookup_related_data(rule, source_value, self.related_sources)
            if related_data and 'value' in related_data:
                logger.warning(f"Row {row_num}: Looked up value '{related_data['value']}' for RDR {rdr_object.uri}. Define strategy in mapping to attach this.")

        elif rule_range == 'uri' and rule_uri_prefix:
            external_uri_str = rule_uri_prefix + str(source_value).strip()
            logger.debug(f"Row {row_num}: RDR {rdr_object.uri} is related to external URI: {external_uri_str}")
            try:
                external_uri_resource = self.resource_manager.get_or_create_resource(
                    uri=external_uri_str,
                    defaults={'resource_type': ResourceType.IRI, 'source': self.institution_code, 'source_field': f"{rdr_uri_slugified_column}_external_uri_link={source_value}"}
                )
                Triple.objects.get_or_create(
                    subject=rdr_object, # RDR owl:sameAs External
                    predicate=self.owl_sameas_resource, 
                    object=external_uri_resource
                )
                logger.debug(f"Row {row_num}: Linked RDR {rdr_object.uri} owl:sameAs {external_uri_str}")
            except Exception as e:
                logger.error(f"Row {row_num}: Failed to link RDR {rdr_object.uri} with external URI {external_uri_str}: {e}", exc_info=True)

        elif object_class_short_name:
            # Add semantic CIDOC type to the RDR
            logger.debug(f"Row {row_num}: Typing RDR {rdr_object.uri} as {object_class_short_name}")
            try:
                cidoc_class_for_rdr = self.resource_manager.get_or_create_cidoc_class_resource(object_class_short_name)
                Triple.objects.get_or_create(
                    subject=rdr_object,
                    predicate=self.rdf_type_resource,
                    object=cidoc_class_for_rdr
                )
                logger.debug(f"Row {row_num}: Added semantic type {cidoc_class_for_rdr.uri} to RDR {rdr_object.uri}")
            except Exception as e:
                logger.error(f"Row {row_num}: Failed to type RDR {rdr_object.uri} as {object_class_short_name}: {e}", exc_info=True)
            
            # Process object_properties for this RDR (now that it might be typed)
            # We can extract this part to _process_rdr_object_properties if it makes sense
            object_properties = rule.get('object_properties', [])
            if object_properties:
                logger.debug(f"Row {row_num}: Processing {len(object_properties)} object_properties for RDR {rdr_object.uri}")
                for sub_rule_idx, sub_rule in enumerate(object_properties):
                    logger.debug(f"Row {row_num}: RDR object_property rule {sub_rule_idx + 1}")
                    try:
                        self._process_sub_rule(sub_rule, row_data, rdr_object, source_value, rdr_uri_slugified_column, row_num)
                    except Exception as e:
                        logger.error(f"Row {row_num}: Error processing sub-rule for RDR {rdr_object.uri}: {e} Rule: {sub_rule}", exc_info=True)
        else:
            logger.debug(f"Row {row_num}: No further specific semantic action (type, sameAs, obj_props) for RDR {rdr_object.uri} from this main rule.")


