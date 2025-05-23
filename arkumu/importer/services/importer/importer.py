import json
import logging
from django.db import transaction

from arkumu.metadata.models import ResourceType, Triple
from arkumu.importer.services.importer.uri_utils import (
 XSD_BASE_URI, DEFAULT_INSTITUTION_BASE_URI,
    slugify_uri_part, mint_uri
)
from arkumu.importer.services.importer.data_utils import (
    extract_expected_source_columns,
    validate_source_headers,
    infer_language,
    lookup_related_data,
    normalize_csv_data_nfc,
    normalize_dict_values_nfc
)
from arkumu.importer.services.importer.resource_manager import ResourceManager
from arkumu.importer.services.importer.rule_processor import MappingRuleProcessor
from arkumu.importer.services.validation.validation import MappingValidator, validate_mapping_columns, validate_mapping

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
    def __init__(self, mapping_file_path_or_config, institution_base_uri=None, related_sources=None, strict_references=False):
        logger.info(f"Initializing JSONMappingImporter")
        
        try:
            # Check if the input is a dictionary (pre-loaded config) or a file path
            if isinstance(mapping_file_path_or_config, dict):
                logger.debug("Using pre-loaded mapping configuration")
                self.mapping_config = mapping_file_path_or_config
                self.mapping_file_path = None
            else:
                # Assume it's a file path
                logger.debug(f"Loading mapping from file: {mapping_file_path_or_config}")
                self.mapping_file_path = mapping_file_path_or_config
                with open(mapping_file_path_or_config, 'r') as f:
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
            
            # Store related sources with NFC normalization
            self.related_sources = {}
            if related_sources:
                logger.debug(f"Normalizing {len(related_sources)} related data sources with NFC")
                for source_key, source_data in related_sources.items():
                    if isinstance(source_data, list):
                        self.related_sources[source_key] = normalize_csv_data_nfc(source_data)
                    else:
                        self.related_sources[source_key] = source_data  # Keep as is if not a list
            
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

            # Create a validator instance for validation operations
            self.validator = MappingValidator()

        except Exception as e:
            logger.exception(f"Failed to initialize JSONMappingImporter: {str(e)}")
            raise

    def validate_mapping_against_csv(self, csv_file_path, data_dir=None, strict=True):
        """
        Validates the mapping configuration against a CSV file before import.
        
        Args:
            csv_file_path: Path to the CSV file to validate against
            data_dir: Directory containing related data files for reference validation
            strict: If True, validation will fail on warnings
            
        Returns:
            tuple: (is_valid, report) - is_valid is boolean, report is ValidationReport
        """
        logger.info(f"Validating mapping against CSV {csv_file_path}")
        
        # Delegate to the validator directly
        if self.mapping_file_path:
            # Validate mapping structure, source columns, and references using file path
            logger.debug(f"Validating using mapping file path: {self.mapping_file_path}")
            report = self.validator.validate_references(
                self.mapping_file_path,
                csv_file_path,
                related_sources=self.related_sources,
                data_dir=data_dir
            )
        else:
            # For pre-loaded configurations, we need to write to a temporary file
            import tempfile
            import os
            
            logger.debug("Creating temporary file for validation of pre-loaded mapping")
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
                json.dump(self.mapping_config, tmp)
                tmp_path = tmp.name
            
            try:
                # Use the temporary file for validation
                report = self.validator.validate_references(
                    tmp_path,
                    csv_file_path,
                    related_sources=self.related_sources,
                    data_dir=data_dir
                )
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary mapping file {tmp_path}: {e}")
        
        # Print summary for logging
        logger.info(report.summary())
        
        # Determine if validation passed based on strict mode
        is_valid = report.is_valid
        if strict and report.warnings:
            is_valid = False
            logger.warning("Validation failed in strict mode due to warnings")
        
        return is_valid, report

    def validate_csv_headers(self, csv_fieldnames):
        """
        Validates CSV field names against expected columns.
        
        Args:
            csv_fieldnames: List of field names from CSV
            
        Returns:
            dict: A dictionary with validation results
        """
        logger.info(f"Validating CSV headers: {csv_fieldnames}")
        # Basic column presence validation
        basic_validation = validate_source_headers(self.expected_source_columns, csv_fieldnames)
        
        # If we have a mapping file path, we can also use validate_mapping_columns 
        # for more detailed column analysis
        if self.mapping_file_path and hasattr(csv_fieldnames, '__iter__') and len(csv_fieldnames) > 0:
            try:
                # Create a temporary CSV just for validation
                import tempfile
                import csv
                
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as tmp:
                    temp_csv_writer = csv.writer(tmp, delimiter=';')
                    temp_csv_writer.writerow(csv_fieldnames)
                    temp_csv_path = tmp.name
                    
                try:
                    # Run the more comprehensive column validation
                    detailed_report = validate_mapping_columns(
                        self.mapping_file_path,
                        temp_csv_path,
                        print_output=False
                    )
                    
                    # Merge the detailed report with the basic validation results
                    if hasattr(detailed_report, 'details') and 'columns' in detailed_report.details:
                        basic_validation['column_details'] = detailed_report.details
                    
                    logger.debug("Extended column validation completed")
                    
                finally:
                    # Clean up the temporary file
                    try:
                        import os
                        os.unlink(temp_csv_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary CSV file: {e}")
                
            except Exception as e:
                logger.warning(f"Extended column validation failed: {e}")
        
        return basic_validation

    def import_data(self, source_data_iterator, primary_subject_class_short_name, strict_references=None, validate_first=True, csv_file_path=None, apply_nfc=True):
        """
        Imports data from a source iterator based on the loaded mapping.
        Assumes headers have been pre-validated if necessary.
        
        Args:
            source_data_iterator: An iterator yielding dictionaries (rows of data).
            primary_subject_class_short_name: The CIDOC-CRM short name for the main entity 
                                            being described by each row (e.g., "E7_Activity").
            strict_references: Override the instance setting for strict reference checking
            validate_first: If True, validate the mapping before importing
            csv_file_path: Path to the CSV file for validation
            apply_nfc: If True, apply NFC normalization to all string values in data (default: True)
            
        Returns:
            dict: Statistics about the import process including success and error counts
        """
        # Validate references first if requested
        if validate_first and csv_file_path:
            # Use the validate_mapping function which provides a more comprehensive validation
            if self.mapping_file_path:
                logger.info(f"Validating mapping file against CSV data before import")
                report = validate_mapping(
                    self.mapping_file_path,
                    csv_file_path,
                    strict=(strict_references if strict_references is not None else self.strict_references),
                    print_output=False
                )
            else:
                # For pre-loaded configurations, we need to use our instance method
                logger.info(f"Validating pre-loaded mapping against CSV data before import")
                is_valid, report = self.validate_mapping_against_csv(
                    csv_file_path, 
                    strict=(strict_references if strict_references is not None else self.strict_references)
                )
                
            # Check if validation passed
            if isinstance(report, bool):  # If validate_mapping returned a boolean
                is_valid = report
                report_summary = "Validation failed" if not is_valid else "Validation passed"
            else:  # If it returned a ValidationReport
                is_valid = report.is_valid
                if strict_references and report.warnings:
                    is_valid = False
                report_summary = report.summary() if hasattr(report, 'summary') else str(report)
                
            if not is_valid:
                logger.error("Validation failed. Import aborted.")
                return {
                    "validation_passed": False,
                    "validation_report": report_summary,
                    "total_rows": 0,
                    "successful_rows": 0,
                    "failed_rows": 0,
                    "errors": ["Import aborted due to validation failures"]
                }
        
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
            "validation_passed": True,
            "total_rows": 0,
            "successful_rows": 0,
            "failed_rows": 0,
            "reference_warnings": 0,
            "reference_errors": 0,
            "errors": []
        }

        # Apply NFC normalization to input data if requested
        normalized_data_iterator = source_data_iterator
        if apply_nfc:
            logger.info("Applying NFC normalization to all input data")
            if isinstance(source_data_iterator, list):
                normalized_data_iterator = normalize_csv_data_nfc(source_data_iterator)
            else:
                # For non-list iterators, we'll normalize each row as we process it
                logger.info("Will normalize each row individually during processing")

        for i, original_row_data in enumerate(normalized_data_iterator):
            # Apply NFC normalization to individual row if needed
            row_data = original_row_data
            if apply_nfc and not isinstance(source_data_iterator, list):
                row_data = normalize_dict_values_nfc(original_row_data)
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

        # Check if we've resolved a placeholder
        if hasattr(event_subject_resource, 'is_placeholder') and event_subject_resource.is_placeholder is False:
            # This was a placeholder that was just resolved
            logger.info(f"Row {row_num}: Resolved placeholder resource with URI {subject_uri}")
            
            # Check for additional placeholders that might refer to this entity from other tables
            self._check_and_resolve_related_placeholders(event_subject_resource, row_data, anchor_column, original_id_val, row_num)

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
            # Ensure every rule has a property
            property_uri = rule.get('property')
            if not property_uri:
                column_name = rule.get('source_column')
                property_uri = f"arkumu:column_{slugify_uri_part(column_name)}"
                rule['property'] = property_uri  # Update the rule for downstream use

            # Ensure the property resource exists and is of type PROPERTY
            predicate_resource = self.resource_manager.get_or_create_resource(
                uri=property_uri,
                defaults={'resource_type': ResourceType.PROPERTY, 'source': self.institution_code}
            )

            # Process the source column according to the rule
            source_column = rule.get('source_column')
            if source_column in row_data:
                source_value = row_data[source_column]
                
                # If we're using a fallback property (original property was empty), ensure we link directly
                if property_uri.startswith('arkumu:column_'):
                    logger.debug(f"Row {row_num}: Using fallback property {property_uri} for column {source_column}")
                    
                    # For unmapped columns, create a simple literal and link it directly
                    if source_value is not None:
                        # Create literal resource for the value
                        literal_resource = self.resource_manager.get_or_create_resource(
                            literal_value=str(source_value),
                            resource_type=ResourceType.LITERAL,
                            defaults={
                                'source': self.institution_code,
                                'source_field': f"unmapped_{source_column}={source_value}"
                            }
                        )
                        
                        # Create triple linking subject to literal using fallback property
                        Triple.objects.get_or_create(
                            subject=event_subject_resource,
                            predicate=predicate_resource,
                            object=literal_resource
                        )
                        logger.debug(f"Row {row_num}: Linked unmapped column {source_column}={source_value} using fallback property")

            # Pass the rule to the rule processor (let it resolve the property as usual)
            self.rule_processor.process_mapping_rule(
                rule, row_data, event_subject_resource, row_num, stats
            )
            
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

    def _check_and_resolve_related_placeholders(self, resource, row_data, anchor_column, id_value, row_num):
        """
        Check for related placeholders that might refer to this entity and update them.
        This is useful when placeholders were created during cross-references.
        
        Args:
            resource: The main resource that might have been a placeholder
            row_data: The row data being imported
            anchor_column: The anchor column name
            id_value: The ID value from the anchor column
            row_num: The row number being processed
        """
        try:
            # Try to find placeholders in source_field that reference this table/column/ID
            table_name = self.mapping_config.get("table_name", "").lower()
            if not table_name:
                # Try to guess table name from path if available
                if hasattr(self, 'mapping_file_path') and self.mapping_file_path:
                    import os
                    table_name = os.path.basename(self.mapping_file_path).split('.')[0].lower()
            
            if not table_name:
                return
                
            # Look for placeholders with source_field patterns like "PLACEHOLDER:TableName_ID=value"
            placeholder_pattern = f"PLACEHOLDER:{table_name}_"
            placeholder_resources = Resource.objects.filter(
                source_field__startswith=placeholder_pattern,
                is_placeholder=True
            )
            
            for placeholder in placeholder_resources:
                # Extract column and value from source_field
                try:
                    source_parts = placeholder.source_field.split('=')
                    if len(source_parts) == 2:
                        placeholder_value = source_parts[1]
                        if str(placeholder_value) == str(id_value):
                            logger.info(f"Row {row_num}: Found related placeholder {placeholder.uri} for {table_name}={id_value}")
                            
                            # Mark as no longer a placeholder
                            placeholder.is_placeholder = False
                            placeholder.source_field = f"RESOLVED:{placeholder.source_field[11:]}"  # Remove "PLACEHOLDER:" prefix
                            placeholder.save()
                except Exception as e:
                    logger.warning(f"Row {row_num}: Error parsing placeholder source_field: {e}", exc_info=True)
        except Exception as e:
            logger.warning(f"Row {row_num}: Error checking related placeholders: {e}", exc_info=True)

    def get_remaining_placeholders(self):
        """
        Returns information about remaining placeholders in the database.
        This is useful after importing all tables to identify missing data.
        
        Returns:
            dict: Dictionary with counts and details of remaining placeholders
        """
        result = {
            "total_placeholders": 0,
            "by_table": {},
            "placeholders": []
        }
        
        try:
            # Get all placeholders
            placeholders = self.resource_manager.get_all_placeholders()
            result["total_placeholders"] = placeholders.count()
            
            for placeholder in placeholders:
                placeholder_info = {
                    "uri": placeholder.uri,
                    "source_field": placeholder.source_field
                }
                
                # Try to extract table and ID information
                if placeholder.source_field and placeholder.source_field.startswith("PLACEHOLDER:"):
                    source_parts = placeholder.source_field[11:].split('=')  # Remove "PLACEHOLDER:" prefix
                    if len(source_parts) == 2:
                        column = source_parts[0]
                        value = source_parts[1]
                        
                        # Extract table name from column name (e.g., "TableName_ID" -> "TableName")
                        table_parts = column.split('_')
                        if len(table_parts) > 0:
                            table_name = table_parts[0]
                            
                            # Update table counter
                            if table_name not in result["by_table"]:
                                result["by_table"][table_name] = 0
                            result["by_table"][table_name] += 1
                            
                            # Add to placeholder details
                            placeholder_info["table"] = table_name
                            placeholder_info["column"] = column
                            placeholder_info["value"] = value
                
                result["placeholders"].append(placeholder_info)
                
        except Exception as e:
            logger.error(f"Error getting remaining placeholders: {e}", exc_info=True)
            
        return result


