import logging
from arkumu.metadata.models import ResourceType, Triple
from arkumu.importer.services.importer.uri_utils import (
    XSD_BASE_URI,
    slugify_uri_part, mint_uri
)
from arkumu.importer.services.importer.data_utils import (
    infer_datatype,
    infer_language,
    split_multi_values,
)

logger = logging.getLogger(__name__)

class MappingRuleProcessor:
    def __init__(self, resource_manager, institution_base_uri, institution_code_slug, 
                 institution_code, rdf_type_resource, rdfs_label_resource, 
                 owl_sameas_resource, related_sources, strict_references):
        self.resource_manager = resource_manager
        self.institution_base_uri = institution_base_uri
        self.institution_code_slug = institution_code_slug
        self.institution_code = institution_code
        self.rdf_type_resource = rdf_type_resource
        self.rdfs_label_resource = rdfs_label_resource
        self.owl_sameas_resource = owl_sameas_resource
        self.related_sources = related_sources
        self.strict_references = strict_references

    def _apply_typing_to_resource(self, resource, class_name):
        """
        Adds rdf:type triple to a resource with the specified CIDOC-CRM class.
        Args:
            resource: The Resource object to type
            class_name: The CIDOC-CRM class name (e.g., 'E42_Identifier', 'E52_Time-Span')
        """
        logger.debug(f"Typing resource {resource.uri} as {class_name}")
        try:
            cidoc_class = self.resource_manager.get_or_create_cidoc_class_resource(class_name)
            Triple.objects.get_or_create(
                subject=resource,
                predicate=self.rdf_type_resource,
                object=cidoc_class
            )
            logger.debug(f"Successfully typed resource {resource.uri} as {class_name}")
        except Exception as e:
            logger.error(f"Failed to type resource {resource.uri} as {class_name}: {e}", exc_info=True)

    def _validate_reference(self, object_column, reference_value, row_num):
        """
        Validates that a referenced entity exists before creating a relationship.
        If the referenced entity doesn't exist, creates a placeholder resource.
        
        Args:
            object_column: The column/model being referenced
            reference_value: The ID or value used as reference
            row_num: Current row number for logging
            
        Returns:
            bool: True if reference is valid or placeholder was created, False if creation failed
        """
        if not object_column or not reference_value:
            return False
        
        # Check if target entity exists in related_sources
        reference_found = False
        if object_column in self.related_sources:
            # Look for the reference value in the appropriate dataset
            dataset = self.related_sources[object_column]
            if isinstance(dataset, dict):
                # If we have a dictionary of entities
                reference_found = str(reference_value) in dataset
            elif isinstance(dataset, list):
                # If we have a list of entity dictionaries
                for item in dataset:
                    if str(item.get('id', '')) == str(reference_value):
                        reference_found = True
                        break
        
        if reference_found:
            logger.debug(f"Row {row_num}: Found referenced entity {object_column}={reference_value} in related sources")
            return True
        
        # Reference not found, create a placeholder resource
        try:
            # Extract the table name from the column name (common pattern is TableName_ID)
            table_name_parts = object_column.split('_')
            table_name = table_name_parts[0] if len(table_name_parts) > 0 else "unknown"
            
            # Create a predictable URI for the resource using the same pattern that would be used when it's actually imported
            placeholder_uri = mint_uri(
                self.institution_base_uri,
                self.institution_code_slug,
                table_name.lower(),  # Assume lowercase table name in URI
                reference_value
            )
            
            placeholder = self.resource_manager.get_or_create_resource(
                uri=placeholder_uri,
                defaults={
                    'resource_type': ResourceType.IRI,
                    'source': self.institution_code,
                    'source_field': f"PLACEHOLDER:{object_column}={reference_value}",
                    'is_placeholder': True
                }
            )
            
            logger.info(f"Row {row_num}: Created placeholder for referenced entity {object_column}={reference_value} with URI {placeholder_uri}")
            return True
        except Exception as e:
            logger.error(f"Row {row_num}: Failed to create placeholder for {object_column}={reference_value}: {e}", exc_info=True)
            return False

    def process_mapping_rule(self, rule, row_data, event_subject_resource, row_num, stats=None):
        source_column_name = rule.get('source_column')
        if not source_column_name or source_column_name not in row_data:
            logger.debug(f"Row {row_num}: Skipping rule: source_column '{source_column_name}' not in row data or not defined")
            return

        source_values_raw = row_data[source_column_name]
        if source_values_raw is None:
            logger.debug(f"Row {row_num}: Skipping rule: source_column '{source_column_name}' has None value")
            return
            
        # Handle multi-value columns - use data_utils.split_multi_values
        # The function expects the rule object and the value
        # Add the delimiter as multi_value_separator in the rule if needed
        rule_with_delimiter = rule.copy()
        if 'delimiter' in rule and 'multi_value_separator' not in rule:
            rule_with_delimiter['multi_value_separator'] = rule['delimiter']
            
        source_values = split_multi_values(rule_with_delimiter, source_values_raw)
        
        # Skip if no values after splitting
        if not source_values:
            logger.debug(f"Row {row_num}: Skipping rule: no values after splitting for '{source_column_name}'")
            return
            
        # Get predicate Resource for this mapping
        property_name = rule.get('property') or rule.get('predicate')
        
        # Handle different types of properties based on namespace
        pred_resource = None
        if property_name == "rdf:type":
            pred_resource = self.rdf_type_resource
        elif property_name == "rdfs:label":
            pred_resource = self.rdfs_label_resource
        elif property_name == "owl:sameAs":
            pred_resource = self.owl_sameas_resource
        else:
            # Default case: assume it's a CIDOC property
            # Extract the property name without namespace prefix (e.g., "P1_is_identified_by" from "cidoc:P1_is_identified_by")
            actual_prop_name = property_name.split(':')[-1]
            pred_resource = self.resource_manager.get_or_create_cidoc_property_resource(actual_prop_name)
        
        if not pred_resource:
            logger.warning(f"Row {row_num}: Skip rule - could not create predicate resource for '{property_name}'")
            return
            
        logger.debug(f"Row {row_num}: Getting predicate resource for '{property_name}'")
            
        # For each value in source_values (might be just one if not multi-valued)
        for source_value in source_values:
            # Special case: Direct attachment of rdfs:label literals 
            is_literal_label = (property_name == 'rdfs:label' and rule.get('range') == 'literal')
            
            logger.debug(f"Row {row_num}: Processing source value: '{source_value}' for column '{source_column_name}'")
            
            # --- Special case: Direct literal label attachment --- 
            if is_literal_label:
                logger.debug(f"Row {row_num}: Attaching direct rdfs:label literal to main subject for value: '{source_value}'")
                literal_language = infer_language(rule, row_data)
                literal_datatype = None
                if not literal_language:
                    literal_datatype = f"{XSD_BASE_URI}string"
                
                direct_literal_resource = self.resource_manager.get_or_create_resource(
                    literal_value=str(source_value),
                    resource_type=ResourceType.LITERAL,
                    literal_language=literal_language,
                    literal_datatype=literal_datatype,
                    defaults={'source': self.institution_code, 'source_field': f"direct_label_for_main_subject={source_value}"}
                )
                
                if direct_literal_resource:
                    label_triple = Triple.objects.create(
                        subject=event_subject_resource,
                        predicate=self.rdfs_label_resource,
                        object=direct_literal_resource
                    )
                    logger.debug(f"Row {row_num}: Added direct rdfs:label '{source_value}' to main subject {event_subject_resource.uri}")
            
            # --- Standard RDR Creation for all properties ---
            # (We still create the RDR even for literal labels, just don't link it directly)
            try:
                # Create RDR for standard case
                logger.debug(f"Row {row_num}: Attempting to create RDR for column '{source_column_name}', value '{source_value}'")
                
                # IMPORTANT: For URI fields, use the value directly as part of the RDR URI
                # For non-URI fields, follow the institutionalized pattern
                rdr_resource = None
                
                # Check if this is a URI field with special handling
                if rule.get('range') == 'uri' and rule.get('uri_prefix'):
                    # For URI fields with prefix, create a local RDR but link it to the external URI
                    external_uri = f"{rule.get('uri_prefix')}{source_value}"
                    
                    # Create RDR resource
                    rdr_resource = self.resource_manager.get_or_create_resource(
                        uri=mint_uri(self.institution_base_uri, self.institution_code_slug, 
                                    slugify_uri_part(source_column_name), 
                                    slugify_uri_part(source_value)),
                        resource_type=ResourceType.IRI,
                        defaults={'source': self.institution_code, 'source_field': f"{source_column_name}_rdr={source_value}"}
                    )
                    
                    # Create external URI resource
                    external_uri_resource = self.resource_manager.get_or_create_resource(
                        uri=external_uri,
                        resource_type=ResourceType.IRI,
                        defaults={'source': self.institution_code, 'source_field': f"{source_column_name}_external_uri_link={source_value}"}
                    )
                    
                    # Link RDR to external URI with owl:sameAs
                    Triple.objects.create(
                        subject=rdr_resource,
                        predicate=self.owl_sameas_resource,
                        object=external_uri_resource
                    )
                    logger.debug(f"Row {row_num}: Linked RDR {rdr_resource.uri} owl:sameAs {external_uri_resource.uri}")
                else:
                    # Standard RDR creation
                    rdr_resource = self.resource_manager.get_or_create_resource(
                        uri=mint_uri(self.institution_base_uri, self.institution_code_slug, 
                                    slugify_uri_part(source_column_name), 
                                    slugify_uri_part(source_value)),
                        resource_type=ResourceType.IRI,
                        defaults={'source': self.institution_code, 'source_field': f"{source_column_name}_rdr={source_value}"}
                    )
                
                if not rdr_resource:
                    logger.warning(f"Row {row_num}: Failed to create RDR for '{source_column_name}={source_value}'")
                    continue
                    
                logger.debug(f"Row {row_num}: Successfully created/got RDR: {rdr_resource.uri}")
                
                # Apply RDR labeling according to rule
                if rule.get('range') == 'literal':
                    # For literal ranges, use the source value as the label
                    literal_language = infer_language(rule, row_data)
                    
                    logger.debug(f"Row {row_num}: RDR {rdr_resource.uri} will get an rdfs:label as original rule intended a literal.")
                    
                    # Create a literal resource and link it to the RDR
                    label_resource = self.resource_manager.get_or_create_resource(
                        literal_value=str(source_value),
                        resource_type=ResourceType.LITERAL,
                        literal_language=literal_language,
                        defaults={'source': self.institution_code, 'source_field': f"{source_column_name}_label={source_value}"}
                    )
                    
                    # Attach the label to the RDR
                    if label_resource:
                        Triple.objects.create(
                            subject=rdr_resource,
                            predicate=self.rdfs_label_resource,
                            object=label_resource
                        )
                        logger.debug(f"Row {row_num}: Added rdfs:label '{source_value}' to RDR {rdr_resource.uri}")
                else:
                    # For non-literal ranges, don't automatically label from source value
                    logger.debug(f"Row {row_num}: RDR {rdr_resource.uri} will not be auto-labeled based on main rule predicate/range.")
                
                # Add additional semantics to RDR based on rule
                logger.debug(f"Row {row_num}: Applying additional semantics to RDR {rdr_resource.uri}")
                
                # 1. Apply typing if specified
                range_class = rule.get('range')
                if range_class and range_class not in ['uri', 'literal']:
                    logger.debug(f"Row {row_num}: Typing RDR {rdr_resource.uri} as {range_class}")
                    self._apply_typing_to_resource(rdr_resource, range_class)
                    
                # 2. Apply external URI linking if specified and not already handled
                if rule.get('range') == 'uri' and rule.get('uri_prefix') and not rule.get('multi_valued'):
                    # Already handled above for multi-valued
                    pass  
                    
                # 3. Apply object properties if specified
                if rule.get('object_properties'):
                    logger.debug(f"Row {row_num}: Processing {len(rule['object_properties'])} object_properties for RDR {rdr_resource.uri}")
                    
                    for idx, sub_rule in enumerate(rule['object_properties'], 1):
                        logger.debug(f"Row {row_num}: RDR object_property rule {idx}")
                        self.process_sub_rule(sub_rule, row_data, rdr_resource, source_value, source_column_name, row_num, stats)
                else:
                    logger.debug(f"Row {row_num}: No further specific semantic action (type, sameAs, obj_props) for RDR {rdr_resource.uri} from this main rule.")
                
                # Inside _process_mapping_rule method, before creating the triple
                is_valid_reference = True # Default to true, set to false if validation fails
                if rule.get('object_column'):
                    is_valid_reference = self._validate_reference(
                        rule['object_column'], source_value, row_num
                    )
                    
                    if not is_valid_reference:
                        if self.strict_references:  # Add this as a configurable option
                            logger.error(f"Row {row_num}: Skipping invalid reference {rule['object_column']}={source_value}")
                            if stats: stats["reference_errors"] += 1
                            continue  # Skip this triple
                        else:
                            logger.warning(f"Row {row_num}: Creating relationship with potentially invalid reference {rule['object_column']}={source_value}")
                            if stats: stats["reference_warnings"] += 1

                # Now create the triple as before
                main_triple = Triple.objects.create(
                    subject=event_subject_resource,
                    predicate=pred_resource,
                    object=rdr_resource
                )
                logger.debug(f"Row {row_num}: Created main triple: {event_subject_resource.uri} -> {pred_resource.uri} -> {rdr_resource.uri}")
                    
            except Exception as e:
                logger.error(f"Row {row_num}: Error processing rule source '{source_column_name}': {e}", exc_info=True)

            # Update statistics counters - MOVED INSIDE THE IF not is_valid_reference BLOCK
            # if stats and not is_valid_reference: # This check is now done before continue or warning
            #     pass

    def process_sub_rule(self, sub_rule, row_data, subject_resource, parent_source_value, 
                         parent_intermediate_uri_part, row_num=None, stats=None):
        """
        Processes a sub-rule defined in 'object_properties'.
        Creates triples where subject_resource (an intermediate IRI) is the subject.
        parent_source_value is the value from the parent rule's source_column, usable via 'use_parent_value'.
        parent_intermediate_uri_part is the ALREADY SLUGIFIED uri part from parent rule's object_class for context in minting.
        row_num is the original row number for logging purposes.
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
            row_log = f" for row {row_num}" if row_num else ""
            logger.warning(f"Sub-rule for {subject_resource.uri}{row_log} lacks 'source_column', 'fixed_value', or 'use_parent_value'. Sub-rule: {sub_rule}")
            return

        if sub_value_raw is None: # Note: allow empty strings if that's intended (e.g. for fixed_value="")
            row_log = f" for row {row_num}" if row_num else ""
            logger.debug(f"Skipping sub-rule{row_log}: value is None. Sub-rule: {sub_rule}")
            return

        # Use data_utils.split_multi_values
        sub_values = split_multi_values(sub_rule, sub_value_raw)

        sub_predicate_short_name = sub_rule.get('predicate') or sub_rule.get('property')
        if not sub_predicate_short_name:
            row_log = f" for row {row_num}" if row_num else ""
            logger.warning(f"Skipping sub-rule for {subject_resource.uri}{row_log}: no 'predicate' or 'property' defined. Sub-rule: {sub_rule}")
            return

        sub_predicate_resource = None
        if sub_predicate_short_name == "rdf:type":
            sub_predicate_resource = self.rdf_type_resource
            actual_prop_name = "type"
        elif sub_predicate_short_name == "rdfs:label":
            sub_predicate_resource = self.rdfs_label_resource
            actual_prop_name = "label"
        else:
            actual_prop_name = sub_predicate_short_name.split(":")[-1]
            sub_predicate_resource = self.resource_manager.get_or_create_cidoc_property_resource(actual_prop_name)
        
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

            # Add to _process_sub_rule after checking sub_value_raw and before creating resources
            is_valid_reference = True # Default to true
            if sub_rule.get('object_column'):
                is_valid_reference = self._validate_reference(
                    sub_rule['object_column'], sub_value, row_num
                )
                
                if not is_valid_reference:
                    if self.strict_references:
                        logger.error(f"Sub-rule: Skipping invalid reference {sub_rule['object_column']}={sub_value}")
                        if stats: stats["reference_errors"] += 1
                        continue  # Skip processing this sub-value
                    else:
                        logger.warning(f"Sub-rule: Creating relationship with potentially invalid reference {sub_rule['object_column']}={sub_value}")
                        if stats: stats["reference_warnings"] += 1

            if sub_object_uri_pattern: # External URI from pattern
                object_uri = sub_object_uri_pattern.replace("{value}", str(sub_value).strip())
                logger.debug(f"Sub-rule: object is external IRI '{object_uri}' from pattern")
                sub_object_resource = self.resource_manager.get_or_create_resource(
                    uri=object_uri,
                    defaults={
                        'resource_type': ResourceType.IRI,
                        'source': self.institution_code, # Or specific source from sub_rule
                        'source_field': f"sub_uri_pattern_{slugify_uri_part(actual_prop_name)}={sub_value}" # Slugify actual_prop_name
                    }
                )
                if sub_object_class: # Optionally type this external IRI
                    type_res = self.resource_manager.get_or_create_cidoc_class_resource(sub_object_class)
                    Triple.objects.get_or_create(
                        subject=sub_object_resource, predicate=self.rdf_type_resource, object=type_res
                    )
            elif sub_object_class: # New IRI to be minted for sub-property object
                # parent_intermediate_uri_part is the slug of the main rule's source_column (e.g., "ereignisbeginn")
                # actual_prop_name is the short name of the sub-predicate (e.g., "P79_beginning_is_qualified_by")
                
                sub_instance_raw_type_slug = f"{parent_intermediate_uri_part}-{slugify_uri_part(actual_prop_name)}"
                sub_instance_raw_id_slug = slugify_uri_part(str(sub_value)) # Ensure sub_value is string for slugify
                
                # Add a uniqueness suffix if multiple values for the same sub-property could lead to collision with identical slug(sub_value)
                # This uses the index 'i' from the loop over sub_values if source was multi-valued.
                if len(sub_values) > 1:
                    sub_instance_raw_id_slug = f"{sub_instance_raw_id_slug}-{i}"

                sub_instance_uri = mint_uri(
                    self.institution_base_uri, self.institution_code_slug,
                    sub_instance_raw_type_slug,
                    sub_instance_raw_id_slug
                )
                logger.debug(f"Sub-rule: object is new raw IRI '{sub_instance_uri}' (raw type: '{sub_instance_raw_type_slug}') to be typed as '{sub_object_class}'")
                
                sub_object_defaults = {
                    'resource_type': ResourceType.IRI,
                    'source': self.institution_code,
                    'source_field': f"{sub_instance_raw_type_slug}_raw={sub_value}"
                }
                sub_object_resource = self.resource_manager.get_or_create_resource(uri=sub_instance_uri, defaults=sub_object_defaults)
                
                # Type this new raw sub-resource
                sub_instance_cidoc_class_r = self.resource_manager.get_or_create_cidoc_class_resource(sub_object_class)
                Triple.objects.get_or_create(
                    subject=sub_object_resource, predicate=self.rdf_type_resource, object=sub_instance_cidoc_class_r
                )
                
                # Auto-label this new raw sub-IRI with its generating sub_value if it's a simple type and not suppressed
                # Note: This auto-labeling for sub-rules was part of the original logic and is retained here.
                # If this also needs to be strictly explicit, this block would be removed or conditionalized.
                if isinstance(sub_value, (str, int, float)) and not sub_rule.get('no_auto_label', False):
                    # Use data_utils.infer_language and data_utils.infer_datatype
                    label_lang = infer_language(sub_rule, row_data)
                    label_dtype = infer_datatype(sub_value)
                    label_lit_res = self.resource_manager.get_or_create_resource(
                        literal_value=str(sub_value), resource_type=ResourceType.LITERAL,
                        literal_language=label_lang, literal_datatype=label_dtype,
                        defaults={'source': self.institution_code, 'source_field': f"auto_label_for_{slugify_uri_part(sub_object_class)}"}
                    )
                    Triple.objects.get_or_create(
                        subject=sub_object_resource, predicate=self.rdfs_label_resource, object=label_lit_res
                    )
            else:
                # Default: The object of the sub-property is a Literal.
                # Use data_utils.infer_language and data_utils.infer_datatype
                sub_literal_language = infer_language(sub_rule, row_data)
                sub_literal_datatype = infer_datatype(sub_value)
                logger.debug(f"Sub-rule: object is Literal '{sub_value}' lang={sub_literal_language} type={sub_literal_datatype}")
                sub_object_resource = self.resource_manager.get_or_create_resource(
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
                triple, created = Triple.objects.get_or_create(
                    subject=subject_resource,
                    predicate=sub_predicate_resource,
                    object=sub_object_resource
                )
                # logger.debug(f"Row {row_num}: Created triple: {triple.subject.uri} -> {triple.predicate.uri} -> {getattr(triple.object, 'uri', getattr(triple.object, 'literal_value', None))}")
            else:
                logger.warning(f"Sub-rule: no object resource created for predicate '{sub_predicate_short_name}', value '{sub_value}' on {subject_resource.uri}")

