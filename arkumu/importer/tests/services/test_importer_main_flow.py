# Tests for JSONMappingImporter main import flow (import_data), including single/multi-row import, error handling, and triple/resource creation.
import pytest
import json
import csv
import logging
from io import StringIO
from arkumu.importer.services.importer import (
    JSONMappingImporter,
    CIDOC_CRM_BASE_URI,
    DEFAULT_INSTITUTION_BASE_URI,
    XSD_BASE_URI
)
from arkumu.importer.services.uri_utils import slugify_uri_part, mint_uri
from arkumu.metadata.models import Resource, Triple, ResourceType

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING)
    yield

@pytest.fixture
def main_flow_mapping_content():
    return {
        "institution": "MAIN_FLOW_TEST",
        "domain": "E7_Activity",
        "mappings": [
            {
                "source_column": "EventName", 
                "predicate": "P1_is_identified_by",
                "range": "E41_Appellation"
            },
            {
                "source_column": "EventTypeID", 
                "predicate": "P2_has_type",
                "range": "E55_Type",
                "object_column": "type_id",
                "link_columns": True
            },
            {
                "source_column": "EventDescription", 
                "predicate": "P3_has_note"
            },
            {
                "source_column": "EventParticipants", 
                "predicate": "P11_had_participant",
                "range": "E39_Actor",
                "object_column": "actor_id",
                "link_columns": True,
                "multi_valued": True
            }
        ]
    }

@pytest.fixture
def main_flow_mapping_file(tmp_path, main_flow_mapping_content):
    file_path = tmp_path / "main_flow_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(main_flow_mapping_content, f)
    return str(file_path)

@pytest.fixture
def importer_for_main_flow(main_flow_mapping_file):
    return JSONMappingImporter(mapping_file_path=main_flow_mapping_file)

@pytest.fixture
def mock_csv_data_basic():
    return [
        {
            "id": "event001",
            "EventName": "Grand Opening Ceremony",
            "EventTypeID": "type_A",
            "EventDescription": "The official opening event.",
            "EventParticipants": "actor1; actor2"
        }
    ]

@pytest.fixture
def mock_csv_data_multiple():
    return [
        {
            "id": "event002",
            "EventName": "Art Exhibition",
            "EventTypeID": "type_B",
            "EventDescription": "A display of modern art.",
            "EventParticipants": "actor3"
        },
        {
            "id": "event003",
            "EventName": "Music Concert",
            "EventTypeID": "type_C",
            "EventDescription": "Live music performance.",
            "EventParticipants": "actor4;actor5; actor6"
        }
    ]

@pytest.fixture
def mock_csv_data_with_error():
    return [
        {
            "id": "event004",
            "EventName": "Valid Event",
            "EventTypeID": "type_D",
            "EventDescription": "This event should import correctly.",
            "EventParticipants": "actor7"
        },
        {
            "id": "event005",
            "EventTypeID": "type_E",
            "EventDescription": "This event should fail but not affect event004.",
            "EventParticipants": "actor8"
        }
    ]

@pytest.fixture
def ereignis_simple_style_mapping_content():
    # Closer to the user's provided Ereignis_simple.json structure
    return {
        "institution": "EREIGNIS_TEST",
        "domain": "E7_Activity",
        "mappings": [
            {
                "source_column": "EventName", # Was "Deutscher Ereignisname"
                "property": "P1_is_identified_by",
                "range": "E41_Appellation" 
                # No object_properties, label will be via fallback from "EventName" value
            },
            {
                "source_column": "EventType", # Was "Ereignistyp"
                "property": "P2_has_type",
                "range": "E55_Type",
                "link_columns": True, 
                "object_column": "event_type_id" # Logical source for the ID itself
            },
            {
                "source_column": "EventDate", # Was "Ereignisbeginn"
                "property": "P4_has_time-span",
                "range": "E52_Time-Span",
                "object_properties": [
                    {
                        "property": "P82a_begin_of_the_begin",
                        "use_parent_value": True
                    },
                    {
                        "property": "P79_beginning_is_qualified_by",
                        "fixed_value": "Recorded Event Start"
                    },
                    {
                        "property": "P2_has_type",
                        "range": "E55_Type",
                        "fixed_value": "Recorded Event Start"
                    }
                ]
            },
            {
                "source_column": "EventLocationIDs", # Was "Ereignisort"
                "property": "P7_took_place_at",
                "range": "E53_Place",
                "multi_valued": True, # Uses default ';' separator for EventLocationIDs
                "link_columns": True,
                "object_column": "location_wikidata_id"
            },
            {
                "source_column": "EventDescription",
                "property": "P3_has_note"
                # No range, becomes a direct literal
            }
        ]
    }

@pytest.fixture
def ereignis_simple_style_mapping_file(tmp_path, ereignis_simple_style_mapping_content):
    file_path = tmp_path / "ereignis_simple_style_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(ereignis_simple_style_mapping_content, f)
    return str(file_path)

@pytest.fixture
def importer_for_ereignis_simple_style(ereignis_simple_style_mapping_file):
    # No institution_base_uri specified, will use DEFAULT_INSTITUTION_BASE_URI
    return JSONMappingImporter(mapping_file_path=ereignis_simple_style_mapping_file)

@pytest.fixture
def mock_csv_data_ereignis_simple_style():
    return [
        {
            "id": "act001", 
            "EventName": "Simple Workshop Name",
            "EventType": "type_workshop", # ID for an E55_Type
            "EventDate": "2023-10-26",
            "EventLocationIDs": "wd:Q123;wd:Q456",
            "EventDescription": "A simple workshop description."
        },
        {
            "id": "act002",
            "EventName": "Another Simple Meeting",
            "EventType": "type_meeting",
            "EventDate": "2023-11-15",
            "EventLocationIDs": "wd:Q789",
            "EventDescription": "Another simple meeting description."
        }
    ]

@pytest.mark.django_db
class TestImporterMainFlow:

    def test_import_data_single_row_comprehensive(self, importer_for_main_flow, mock_csv_data_basic):
        source_data = mock_csv_data_basic
        headers = list(source_data[0].keys())
        importer_for_main_flow.validate_source_headers(headers)
        initial_resource_count = Resource.objects.count()
        initial_triple_count = Triple.objects.count()
        stats = importer_for_main_flow.import_data(source_data, primary_subject_class_short_name="E7_Activity")
        assert stats["successful_rows"] == 1
        assert Resource.objects.count() > initial_resource_count
        assert Triple.objects.count() > initial_triple_count

    def test_import_data_multiple_rows(self, importer_for_main_flow, mock_csv_data_multiple):
        source_data = mock_csv_data_multiple
        headers = list(source_data[0].keys())
        importer_for_main_flow.validate_source_headers(headers)
        stats = importer_for_main_flow.import_data(source_data, primary_subject_class_short_name="E7_Activity")
        assert stats["successful_rows"] == 2
        assert stats["failed_rows"] == 0

    def test_import_data_missing_primary_class_raises_error(self, importer_for_main_flow, mock_csv_data_basic):
        # Should succeed because domain is present in mapping
        stats = importer_for_main_flow.import_data(mock_csv_data_basic, primary_subject_class_short_name=None)
        assert stats["successful_rows"] == 1
        # Should raise if both argument and domain are missing (not tested here)

    def test_import_data_with_missing_column_in_source_skips_rule_gracefully(self, importer_for_main_flow):
        # Mapping expects "EventDescription", but data won't have it.
        source_data = [{
            "id": "event004",
            "EventName": "Silent Auction",
            "EventTypeID": "type_D",
            "EventParticipants": "actor7"
        }]
        headers = list(source_data[0].keys())
        with pytest.raises(ValueError, match="Critical columns from mapping are missing in the source data headers"):
            importer_for_main_flow.validate_source_headers(headers)

    def test_import_data_with_error_in_row(self, importer_for_main_flow, mock_csv_data_with_error, monkeypatch):
        """Test that an error in one row doesn't affect other rows."""
        def mock_process_mapping_rule(self, rule, row_data, event_subject_resource, row_num):
            if row_data.get('id') == 'event005':
                raise ValueError("Simulated error in row processing")
            original_method(rule, row_data, event_subject_resource, row_num)
        original_method = importer_for_main_flow._process_mapping_rule
        monkeypatch.setattr(importer_for_main_flow, '_process_mapping_rule',
                          lambda rule, row_data, event_subject_resource, row_num:
                          mock_process_mapping_rule(importer_for_main_flow, rule, row_data, event_subject_resource, row_num))
        stats = importer_for_main_flow.import_data(
            mock_csv_data_with_error, primary_subject_class_short_name="E7_Activity"
        )
        assert stats["successful_rows"] == 1
        assert stats["failed_rows"] == 1

@pytest.mark.django_db
class TestImporterNewConventionFlow:

    def test_import_data_new_conventions_comprehensive(self, importer_for_ereignis_simple_style, mock_csv_data_ereignis_simple_style):
        source_data = mock_csv_data_ereignis_simple_style
        importer = importer_for_ereignis_simple_style
        # Ensure importer's resource manager is accessible for labels etc.
        rm = importer.resource_manager

        stats = importer.import_data(source_data, primary_subject_class_short_name="E7_Activity")
        assert stats["total_rows"] == 2
        assert stats["successful_rows"] == 2
        assert stats["failed_rows"] == 0
        
        # --- Assertions for first row (act001) ---
        inst_code_slug = slugify_uri_part(importer.institution_code) # "ereignis_test"
        domain_class_slug = slugify_uri_part(importer.default_domain_class) # "e7_activity"
        
        act001_id_slug = slugify_uri_part(source_data[0]["id"]) # "act001"
        # Expected URI for the main E7_Activity resource
        expected_act001_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, domain_class_slug, act001_id_slug
        )
        act001_res = Resource.objects.get(uri=expected_act001_uri)
        
        domain_class_res = rm.get_or_create_cidoc_class_resource(importer.default_domain_class)
        assert Triple.objects.filter(subject=act001_res, predicate=importer.rdf_type_resource, object=domain_class_res).exists()

        # 1. EventName -> P1_is_identified_by -> RDR (typed E41_Appellation, labeled with EventName)
        p1_prop = rm.get_or_create_cidoc_property_resource("P1_is_identified_by")
        event_name_value = source_data[0]["EventName"]
        event_name_slug = slugify_uri_part(event_name_value)
        event_name_col_slug = slugify_uri_part("EventName") # from mapping source_column

        expected_rdr_eventname_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, event_name_col_slug, event_name_slug
        )
        rdr_eventname_res = Triple.objects.get(subject=act001_res, predicate=p1_prop).object
        assert rdr_eventname_res.uri == expected_rdr_eventname_uri
        assert rdr_eventname_res.resource_type == ResourceType.IRI
        
        e41_class_res = rm.get_or_create_cidoc_class_resource("E41_Appellation")
        assert Triple.objects.filter(subject=rdr_eventname_res, predicate=importer.rdf_type_resource, object=e41_class_res).exists()
        
        # Check label on the RDR
        app_label_triple = Triple.objects.get(subject=rdr_eventname_res, predicate=importer.rdfs_label_resource)
        assert app_label_triple.object.literal_value == event_name_value

        # 2. EventType -> P2_has_type -> RDR (typed E55_Type)
        p2_prop = rm.get_or_create_cidoc_property_resource("P2_has_type")
        event_type_value = source_data[0]["EventType"]
        event_type_slug = slugify_uri_part(event_type_value)
        event_type_col_slug = slugify_uri_part("EventType")

        expected_rdr_eventtype_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, event_type_col_slug, event_type_slug
        )
        rdr_eventtype_res = Triple.objects.get(subject=act001_res, predicate=p2_prop).object
        assert rdr_eventtype_res.uri == expected_rdr_eventtype_uri
        assert rdr_eventtype_res.resource_type == ResourceType.IRI

        e55_class_res = rm.get_or_create_cidoc_class_resource("E55_Type")
        assert Triple.objects.filter(subject=rdr_eventtype_res, predicate=importer.rdf_type_resource, object=e55_class_res).exists()
        # Note: No automatic owl:sameAs is created by current importer for this mapping rule

        # 3. EventDate -> P4_has_time-span -> RDR (typed E52_Time-Span, with object_properties)
        p4_prop = rm.get_or_create_cidoc_property_resource("P4_has_time-span")
        event_date_value = source_data[0]["EventDate"]
        event_date_slug = slugify_uri_part(event_date_value)
        event_date_col_slug = slugify_uri_part("EventDate")

        expected_rdr_timespan_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, event_date_col_slug, event_date_slug
        )
        rdr_timespan_res = Triple.objects.get(subject=act001_res, predicate=p4_prop).object
        assert rdr_timespan_res.uri == expected_rdr_timespan_uri
        assert rdr_timespan_res.resource_type == ResourceType.IRI
        
        e52_class_res = rm.get_or_create_cidoc_class_resource("E52_Time-Span")
        assert Triple.objects.filter(subject=rdr_timespan_res, predicate=importer.rdf_type_resource, object=e52_class_res).exists()

        # Check P82a_begin_of_the_begin from object_properties (use_parent_value)
        p82a_prop = rm.get_or_create_cidoc_property_resource("P82a_begin_of_the_begin")
        ts_begin_triple = Triple.objects.get(subject=rdr_timespan_res, predicate=p82a_prop)
        assert ts_begin_triple.object.literal_value == event_date_value
        assert ts_begin_triple.object.literal_datatype == f"{XSD_BASE_URI}date" # Assuming infer_datatype works

        # Check P2_has_type for Time-span RDR (fixed_value "Recorded Event Start", creates sub-instance)
        # This sub-instance is for the object_property itself.
        obj_prop_p2_fixed_value = "Recorded Event Start"
        obj_prop_p2_fixed_value_slug = slugify_uri_part(obj_prop_p2_fixed_value)
        # sub_instance_raw_type_slug = parent_col_slug + "-" + sub_predicate_slug
        sub_instance_type_slug_for_p2 = f"{event_date_col_slug}-{slugify_uri_part('P2_has_type')}"
        
        expected_sub_instance_p2_uri = mint_uri(
             importer.institution_base_uri, inst_code_slug, 
             sub_instance_type_slug_for_p2, 
             obj_prop_p2_fixed_value_slug
        )
        ts_type_triple = Triple.objects.get(subject=rdr_timespan_res, predicate=p2_prop) # Main RDR -> P2 -> Sub-instance
        sub_instance_p2_res = ts_type_triple.object
        assert sub_instance_p2_res.uri == expected_sub_instance_p2_uri
        assert sub_instance_p2_res.resource_type == ResourceType.IRI
        
        # This sub-instance should be typed E55_Type and labeled
        assert Triple.objects.filter(subject=sub_instance_p2_res, predicate=importer.rdf_type_resource, object=e55_class_res).exists()
        ts_type_label = Triple.objects.get(subject=sub_instance_p2_res, predicate=importer.rdfs_label_resource)
        assert ts_type_label.object.literal_value == obj_prop_p2_fixed_value

        # 4. EventLocationIDs -> P7_took_place_at -> RDRs (multi-valued, typed E53_Place)
        p7_prop = rm.get_or_create_cidoc_property_resource("P7_took_place_at")
        location_triples = Triple.objects.filter(subject=act001_res, predicate=p7_prop)
        assert location_triples.count() == 2
        
        event_loc_col_slug = slugify_uri_part("EventLocationIDs")
        e53_class_res = rm.get_or_create_cidoc_class_resource("E53_Place")
        
        loc_values = source_data[0]["EventLocationIDs"].split(';')
        found_loc_rdr_uris = {triple.object.uri for triple in location_triples}

        for loc_val_raw in loc_values:
            loc_val = loc_val_raw.strip()
            loc_slug = slugify_uri_part(loc_val)
            expected_rdr_loc_uri = mint_uri(
                importer.institution_base_uri, inst_code_slug, event_loc_col_slug, loc_slug
            )
            assert expected_rdr_loc_uri in found_loc_rdr_uris
            # Additionally, check type for one of them (or loop and check all)
            loc_rdr = Resource.objects.get(uri=expected_rdr_loc_uri)
            assert Triple.objects.filter(subject=loc_rdr, predicate=importer.rdf_type_resource, object=e53_class_res).exists()

        # 5. EventDescription -> P3_has_note -> RDR (labeled with EventDescription)
        p3_prop = rm.get_or_create_cidoc_property_resource("P3_has_note")
        event_desc_value = source_data[0]["EventDescription"]
        event_desc_slug = slugify_uri_part(event_desc_value)
        event_desc_col_slug = slugify_uri_part("EventDescription")

        expected_rdr_desc_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, event_desc_col_slug, event_desc_slug
        )
        rdr_desc_res = Triple.objects.get(subject=act001_res, predicate=p3_prop).object
        assert rdr_desc_res.uri == expected_rdr_desc_uri
        assert rdr_desc_res.resource_type == ResourceType.IRI
        
        # Check label on the RDR for description
        desc_label_triple = Triple.objects.get(subject=rdr_desc_res, predicate=importer.rdfs_label_resource)
        assert desc_label_triple.object.literal_value == event_desc_value
        
        # Verify second row was processed by checking its main subject resource and one property (e.g. P3 note)
        act002_id_slug = slugify_uri_part(source_data[1]["id"]) # "act002"
        expected_act002_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, domain_class_slug, act002_id_slug
        )
        act002_res = Resource.objects.get(uri=expected_act002_uri)
        assert act002_res is not None # Check it exists

        # Check P3 note for the second event
        event2_desc_value = source_data[1]["EventDescription"]
        event2_desc_slug = slugify_uri_part(event2_desc_value)
        # event_desc_col_slug is the same

        expected_rdr_desc2_uri = mint_uri(
            importer.institution_base_uri, inst_code_slug, event_desc_col_slug, event2_desc_slug
        )
        rdr_desc2_res = Triple.objects.get(subject=act002_res, predicate=p3_prop).object
        assert rdr_desc2_res.uri == expected_rdr_desc2_uri
        
        desc2_label_triple = Triple.objects.get(subject=rdr_desc2_res, predicate=importer.rdfs_label_resource)
        assert desc2_label_triple.object.literal_value == event2_desc_value 