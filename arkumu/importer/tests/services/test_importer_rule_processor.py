# Tests for JSONMappingImporter._process_mapping_rule (rationalized, focused on unique rule processor logic)
# Only essential and unique tests for rule skipping, direct literal, linked resource, intermediate instance, multi-value, time-span, related data lookup, and object_properties logic are retained.
import pytest
import json
import logging
from datetime import datetime
from arkumu.importer.services.importer import JSONMappingImporter
from arkumu.importer.services.uri_utils import (
    CIDOC_CRM_BASE_URI,
    DEFAULT_INSTITUTION_BASE_URI,
    XSD_BASE_URI,
    OWL_BASE_URI,
    slugify_uri_part,
    mint_uri
)
from arkumu.cidoc.models import Resource, Triple, ResourceType

# Helper functions for common assertions
def _assert_rdr_uri(rdr_resource, expected_uri_prefix, col_name_for_uri, value_for_uri, importer_inst_slug):
    """Asserts the type and URI of an RDR resource based on column and value."""
    col_slug = slugify_uri_part(col_name_for_uri)
    val_slug = slugify_uri_part(value_for_uri)
    expected_rdr_uri = f"{expected_uri_prefix}{importer_inst_slug}/{col_slug}/{val_slug}"
    assert rdr_resource.resource_type == ResourceType.IRI
    assert rdr_resource.uri == expected_rdr_uri

def _assert_resource_type(resource, type_class_resource, importer_instance):
    """Asserts that a resource has the given rdf:type."""
    assert Triple.objects.filter(
        subject=resource, 
        predicate=importer_instance.rdf_type_resource,
        object=type_class_resource
    ).exists()

def _assert_literal_label(resource, expected_value, importer_instance, expected_lang=None):
    """Asserts that a resource has a specific rdfs:label with an optional language tag."""
    label_triple = Triple.objects.get(subject=resource, predicate=importer_instance.rdfs_label_resource, object__literal_value=expected_value)
    assert label_triple.object.resource_type == ResourceType.LITERAL
    assert label_triple.object.literal_language == expected_lang

def _assert_no_label(resource, importer_instance):
    """Asserts that a resource does not have an rdfs:label."""
    assert not Triple.objects.filter(subject=resource, predicate=importer_instance.rdfs_label_resource).exists()

def _assert_owl_sameas(resource, expected_target_resource, importer_instance):
    """Asserts that a resource has an owl:sameAs link to the expected target resource."""
    assert Triple.objects.filter(
        subject=resource, 
        predicate=importer_instance.owl_sameas_resource,
        object=expected_target_resource
    ).exists()

def _assert_no_owl_sameas(resource, importer_instance):
    """Asserts that a resource does not have an owl:sameAs link."""
    assert not Triple.objects.filter(subject=resource, predicate=importer_instance.owl_sameas_resource).exists()

def _get_rdr_for_fixed_value(fixed_value, predicate_for_synthetic_col, importer):
    """Constructs the expected RDR Resource for a fixed value used in object_properties."""
    # This logic is inferred from object_properties tests for fixed_value RDRs.
    synthetic_col_name = f"fixed-value-for-{slugify_uri_part(predicate_for_synthetic_col)}"
    col_slug = slugify_uri_part(synthetic_col_name)
    val_slug = slugify_uri_part(fixed_value)
    expected_uri = f"{DEFAULT_INSTITUTION_BASE_URI}{importer.institution_code_slug}/{col_slug}/{val_slug}"
    # Use get_or_create_resource to ensure it's available for linking, not just for URI check
    return importer.resource_manager.get_or_create_resource(expected_uri, resource_type=ResourceType.IRI)


# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING)
    yield

@pytest.fixture
def rule_processor_mapping_content():
    return {
        "institution": "RULE_PROC_TEST",
        "mappings": []
    }

@pytest.fixture
def rule_processor_mapping_file(tmp_path, rule_processor_mapping_content):
    file_path = tmp_path / "rule_proc_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(rule_processor_mapping_content, f)
    return str(file_path)

@pytest.fixture
def related_source_data():
    return {
        "descriptions": [
            {"id": "desc1", "text": "First related text", "language": "en"},
            {"id": "desc2", "text": "Zweiter Text", "language": "de"}
        ]
    }

@pytest.fixture
def importer_for_rule_processing(rule_processor_mapping_file, related_source_data):
    return JSONMappingImporter(
        mapping_file_path=rule_processor_mapping_file,
        related_sources=related_source_data
    )

@pytest.fixture
def mock_event_subject(importer_for_rule_processing):
    event_uri = mint_uri(
        importer_for_rule_processing.institution_base_uri, 
        importer_for_rule_processing.institution_code_slug,
        "event", 
        "evt123"
    )
    subject_resource, _ = Resource.objects.get_or_create(
        uri=event_uri,
        defaults={
            'resource_type': ResourceType.IRI,
            'source': importer_for_rule_processing.institution_code,
            'source_field': "test_event_id=evt123"
        }
    )
    return subject_resource

@pytest.mark.django_db
class TestImporterRuleProcessor:
    @pytest.mark.parametrize("rule,row_data", [
        ({"predicate": "P1"}, {"colA": "valueA"}), # missing source_column
        ({"source_column": "NonExistentCol", "predicate": "P1"}, {"colA": "valueA"}), # source_column not in row
        ({"source_column": "ColWithEmptySplit", "predicate": "P1", "note": "Separated by a ';'"}, {"ColWithEmptySplit": ";;;"}), # empty after split
        ({"source_column": "NullableCol", "predicate": "P1"}, {"NullableCol": None}), # value is None
        ({"source_column": "colA"}, {"colA": "valueA"}) # missing predicate
    ])
    def test_rule_skipping_cases(self, importer_for_rule_processing, mock_event_subject, rule, row_data):
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject, row_num=1)
        assert Triple.objects.count() == initial_triple_count

    PROCESS_SINGLE_RDR_TEST_CASES = [
        (
            "direct_literal",
            {"source_column": "Description", "predicate": "P3_has_note"},
            {"Description": "A simple note."},
            {
                "rdr_label": {"value": "A simple note."},
                "expect_no_type_on_rdr": True,
                "expect_no_owl_sameas_on_rdr": True
            }
        ),
        (
            "linked_resource",
            {"source_column": "PlaceID", "predicate": "P7_took_place_at", "object_class": "E53_Place", "range": "uri"},
            {"PlaceID": "placeXYZ"},
            {
                "rdr_type_class": "E53_Place",
                "rdr_owl_sameas_value": "placeXYZ", "rdr_owl_sameas_class": "E53_Place", # Uses rule["object_class"]
                "expect_no_label_on_rdr": True
            }
        ),
        (
            "intermediate_typed_instance",
            {"source_column": "ObjectName", "predicate": "P1_is_identified_by", "object_class": "E41_Appellation"},
            {"ObjectName": "The Masterpiece"},
            {
                "rdr_type_class": "E41_Appellation",
                "rdr_label": {"value": "The Masterpiece"},
                "expect_no_owl_sameas_on_rdr": True
            }
        ),
        (
            "time_span_basic",
            {"source_column": "StartDate", "predicate": "P4_has_time-span", "object_class": "E52_Time-Span", "is_start_date": True, "approximation_column": "StartDateApprox"},
            {"StartDate": "2023-05-15", "StartDateApprox": "true"},
            {
                "rdr_type_class": "E52_Time-Span",
                "expect_no_label_on_rdr": True, # Basic RDR for E52 has no label from source_column value
                "expect_no_owl_sameas_on_rdr": True,
                "time_span_specific_uri_check": True # RDR URI for E52 from date needs specific check part
            }
        ),
        (
            "related_data_lookup",
            {"source_column": "DescriptionID", "predicate": "P3_has_note", "lookup_type": "related_table_literal", "related_source": "descriptions", "related_source_key_column": "id", "related_source_value_column": "text", "related_source_language_column": "language"},
            {"DescriptionID": "desc1"},
            {
                "rdr_uri_source_column": "DescriptionID", # Explicitly state this for clarity
                "rdr_uri_source_value": "desc1",          # RDR URI from original key
                "rdr_label": {"value": "First related text", "lang": "en"}, # Label from looked-up value
                "expect_no_type_on_rdr": True,
                "expect_no_owl_sameas_on_rdr": True
            }
        )
    ]
    @pytest.mark.parametrize("test_id, rule, row_data, expectations", PROCESS_SINGLE_RDR_TEST_CASES)
    def test_process_single_rdr_creation_cases(self, importer_for_rule_processing, mock_event_subject, test_id, rule, row_data, expectations):
        source_value = row_data[rule["source_column"]]
        inst_slug = importer_for_rule_processing.institution_code_slug

        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject, row_num=1)
        
        prop_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource(rule["predicate"])
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=prop_res) # Assumes 1 main triple
        rdr_object_resource = main_triple.object

        rdr_uri_col = expectations.get("rdr_uri_source_column", rule["source_column"])
        rdr_uri_val = expectations.get("rdr_uri_source_value", source_value)
        _assert_rdr_uri(rdr_object_resource, DEFAULT_INSTITUTION_BASE_URI,
                        rdr_uri_col, rdr_uri_val, inst_slug)

        if "rdr_type_class" in expectations:
            class_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource(expectations["rdr_type_class"])
            _assert_resource_type(rdr_object_resource, class_res, importer_for_rule_processing)
        elif expectations.get("expect_no_type_on_rdr", False):
            assert not Triple.objects.filter(subject=rdr_object_resource, predicate=importer_for_rule_processing.rdf_type_resource).exists()
        
        if "rdr_label" in expectations:
            label_info = expectations["rdr_label"]
            _assert_literal_label(rdr_object_resource, label_info["value"], importer_for_rule_processing, expected_lang=label_info.get("lang"))
        elif expectations.get("expect_no_label_on_rdr", False):
            _assert_no_label(rdr_object_resource, importer_for_rule_processing)

        if "rdr_owl_sameas_value" in expectations:
            semantic_val = expectations["rdr_owl_sameas_value"]
            # If rdr_owl_sameas_class is not provided, it defaults to rule["object_class"]
            semantic_class_name = expectations.get("rdr_owl_sameas_class", rule.get("object_class"))
            assert semantic_class_name, f"Test {test_id}: rdr_owl_sameas_class or rule['object_class'] must be defined for owl:sameAs"

            semantic_val_slug = slugify_uri_part(semantic_val)
            semantic_class_slug = slugify_uri_part(semantic_class_name)
            
            expected_semantic_uri = mint_uri(importer_for_rule_processing.institution_base_uri, 
                                             importer_for_rule_processing.institution_code_slug, 
                                             semantic_class_slug, semantic_val_slug)
            semantic_res, _ = Resource.objects.get_or_create(uri=expected_semantic_uri, defaults={'resource_type': ResourceType.IRI})
            _assert_owl_sameas(rdr_object_resource, semantic_res, importer_for_rule_processing)
        elif expectations.get("expect_no_owl_sameas_on_rdr", False):
            _assert_no_owl_sameas(rdr_object_resource, importer_for_rule_processing)

        if expectations.get("time_span_specific_uri_check"):
            # For time-span, the RDR URI is based on the source_column and its date value.
            # The generic _assert_rdr_uri already covers this. We just ensure it's being checked.
            # If more specific P81a/b checks were needed, they'd go here.
            # The current simplified time-span test doesn't create P81a/b automatically.
            assert inst_slug in rdr_object_resource.uri # Use rdr_object_resource
            # This part needs rework if we want to be very specific about time-span URI parts
            # For now, relying on the main _assert_rdr_uri using source_value which is the date string.
            pass

    def test_process_multi_value_linked_resource(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "ActorIDs", 
            "predicate": "P11_had_participant", 
            "object_class": "E39_Actor",
            "range": "uri",
            "note": "Multi-values separated by a ';' please"
        }
        row_data = {"ActorIDs": "actor123; actor456"}
        source_values_list = ["actor123", "actor456"] # Corrected: actual values after split

        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject, row_num=1)

        inst_slug = importer_for_rule_processing.institution_code_slug
        p11_prop = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource("P11_had_participant")
        created_main_triples = Triple.objects.filter(subject=mock_event_subject, predicate=p11_prop)
        assert created_main_triples.count() == 2

        e39_class_resource = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource("E39_Actor")
        semantic_class_slug = slugify_uri_part(rule["object_class"])
        
        found_rdr_uris = set()
        processed_source_values = set()

        for triple_obj in created_main_triples: # Renamed to avoid conflict
            rdr_object_resource = triple_obj.object
            found_rdr_uris.add(rdr_object_resource.uri)

            # Try to map RDR back to one of the original source values for detailed assertion
            matched_source_value = None
            for sv_item in source_values_list: # Renamed to avoid conflict
                if slugify_uri_part(sv_item) in rdr_object_resource.uri:
                    matched_source_value = sv_item
                    processed_source_values.add(sv_item)
                    break
            assert matched_source_value is not None, f"Could not map RDR {rdr_object_resource.uri} back to a source value from {source_values_list}"
            
            _assert_rdr_uri(rdr_object_resource, DEFAULT_INSTITUTION_BASE_URI,
                            rule["source_column"], matched_source_value, inst_slug)
            _assert_resource_type(rdr_object_resource, e39_class_resource, importer_for_rule_processing)

            semantic_val_slug = slugify_uri_part(matched_source_value)
            expected_semantic_uri_str = mint_uri(importer_for_rule_processing.institution_base_uri, inst_slug, semantic_class_slug, semantic_val_slug)
            expected_semantic_resource, _ = Resource.objects.get_or_create(uri=expected_semantic_uri_str, defaults={'resource_type': ResourceType.IRI})
            _assert_owl_sameas(rdr_object_resource, expected_semantic_resource, importer_for_rule_processing)
            _assert_no_label(rdr_object_resource, importer_for_rule_processing) # RDRs from range=uri don't get labels from source value
        
        assert len(found_rdr_uris) == len(source_values_list)
        assert processed_source_values == set(source_values_list)

@pytest.mark.django_db
class TestImporterRuleProcessorWithObjectProperties:
    def test_intermediate_with_object_properties_basic(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "ActorName", 
            "predicate": "P1_is_identified_by", 
            "object_class": "E41_Appellation",
            "object_properties": [
                {
                    "predicate": "rdfs:label", 
                    "fixed_value": "The Great Actor"
                },
                {
                    "predicate": "P2_has_type",
                    "object_class": "E55_Type",
                    "fixed_value": "Official Name" 
                }
            ]
        }
        row_data = {"ActorName": "Some Actor"}
        source_value_actor_name = row_data[rule["source_column"]]

        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject, row_num=1)

        inst_slug = importer_for_rule_processing.institution_code_slug

        p1_prop = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource("P1_is_identified_by")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p1_prop)
        rdr_e41_resource = main_triple.object
        
        _assert_rdr_uri(rdr_e41_resource, DEFAULT_INSTITUTION_BASE_URI,
                        rule["source_column"], source_value_actor_name, inst_slug)

        e41_class_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource("E41_Appellation")
        _assert_resource_type(rdr_e41_resource, e41_class_res, importer_for_rule_processing)

        _assert_literal_label(rdr_e41_resource, source_value_actor_name, importer_for_rule_processing) 

        fixed_label_great_actor = "The Great Actor"
        assert Triple.objects.filter(subject=rdr_e41_resource, predicate=importer_for_rule_processing.rdfs_label_resource, object__literal_value=fixed_label_great_actor).exists()
        assert Triple.objects.filter(subject=rdr_e41_resource, predicate=importer_for_rule_processing.rdfs_label_resource).count() == 2
        
        p2_prop_obj_prop_rule = rule["object_properties"][1]
        p2_prop_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource(p2_prop_obj_prop_rule["predicate"])
        obj_prop_triple_p2 = Triple.objects.get(subject=rdr_e41_resource, predicate=p2_prop_res)
        rdr_e55_resource = obj_prop_triple_p2.object
        
        fixed_val_official_name = p2_prop_obj_prop_rule["fixed_value"]
        expected_rdr_e55_uri_obj = _get_rdr_for_fixed_value(fixed_val_official_name, p2_prop_obj_prop_rule["predicate"], importer_for_rule_processing)
        assert rdr_e55_resource.uri == expected_rdr_e55_uri_obj.uri
        assert rdr_e55_resource.resource_type == ResourceType.IRI

        e55_class_res_obj_prop = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource(p2_prop_obj_prop_rule["object_class"])
        _assert_resource_type(rdr_e55_resource, e55_class_res_obj_prop, importer_for_rule_processing)
        _assert_literal_label(rdr_e55_resource, fixed_val_official_name, importer_for_rule_processing)

    def test_intermediate_with_object_properties_use_parent_value(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "WorkTitle", 
            "predicate": "P102_has_title", 
            "object_class": "E35_Title",
            "object_properties": [
                {
                    "predicate": "rdfs:label",
                    "use_parent_value": True 
                },
                {
                    "predicate": "P2_has_type",
                    "object_class": "E55_Type",
                    "fixed_value": "Main Title"
                }
            ]
        }
        row_data = {"WorkTitle": "Original Work Title"}
        source_value_work_title = row_data[rule["source_column"]]

        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject, row_num=1)

        inst_slug = importer_for_rule_processing.institution_code_slug

        p102_prop = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource("P102_has_title")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p102_prop)
        rdr_e35_resource = main_triple.object
        
        _assert_rdr_uri(rdr_e35_resource, DEFAULT_INSTITUTION_BASE_URI,
                        rule["source_column"], source_value_work_title, inst_slug)

        e35_class_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource("E35_Title")
        _assert_resource_type(rdr_e35_resource, e35_class_res, importer_for_rule_processing)

        _assert_literal_label(rdr_e35_resource, source_value_work_title, importer_for_rule_processing)
        assert Triple.objects.filter(subject=rdr_e35_resource, predicate=importer_for_rule_processing.rdfs_label_resource).count() == 1
        
        p2_prop_obj_prop_rule = rule["object_properties"][1]
        p2_prop_res = importer_for_rule_processing.resource_manager.get_or_create_cidoc_property_resource(p2_prop_obj_prop_rule["predicate"])
        obj_prop_triple_p2 = Triple.objects.get(subject=rdr_e35_resource, predicate=p2_prop_res)
        rdr_e55_maintitle_resource = obj_prop_triple_p2.object
        
        fixed_val_main_title = p2_prop_obj_prop_rule["fixed_value"]
        expected_rdr_e55_uri_obj = _get_rdr_for_fixed_value(fixed_val_main_title, p2_prop_obj_prop_rule["predicate"], importer_for_rule_processing)
        assert rdr_e55_maintitle_resource.uri == expected_rdr_e55_uri_obj.uri
        assert rdr_e55_maintitle_resource.resource_type == ResourceType.IRI
        
        e55_class_res_obj_prop = importer_for_rule_processing.resource_manager.get_or_create_cidoc_class_resource(p2_prop_obj_prop_rule["object_class"])
        _assert_resource_type(rdr_e55_maintitle_resource, e55_class_res_obj_prop, importer_for_rule_processing)
        _assert_literal_label(rdr_e55_maintitle_resource, fixed_val_main_title, importer_for_rule_processing)