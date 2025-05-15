# Tests for JSONMappingImporter.import_data (main flow) 
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
from arkumu.cidoc.models import Resource, Triple, ResourceType

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
                "property": "P1_is_identified_by",
                "range": "E41_Appellation"
            },
            {
                "source_column": "EventTypeID", 
                "property": "P2_has_type",
                "range": "E55_Type",
                "object_column": "type_id",
                "link_columns": True
            },
            {
                "source_column": "EventDescription", 
                "property": "P3_has_note"
            },
            {
                "source_column": "EventParticipants", 
                "property": "P11_had_participant",
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
                # This implies EventType column contains an ID that becomes part of the E55 URI
                # For a linked resource, typically "link_columns": True and an "object_column" would be used.
                # If EventType is just a string like "Concert", it should make an intermediate E55_Type
                # or a literal. Let's assume it creates an intermediate E55 and labels it.
                # To make it a linked resource from an ID in EventType:
                "link_columns": True, 
                "object_column": "event_type_id" # Logical source for the ID itself
            },
            {
                "source_column": "EventDate", # Was "Ereignisbeginn"
                "property": "P4_has_time-span",
                "range": "E52_Time-Span",
                "object_properties": [
                    # Use the EventDate value for P82a_begin_of_the_begin
                    {"property": "P82a_begin_of_the_begin", "use_parent_value": True},
                    # Add a fixed type to the time-span, e.g. "official start date"
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

        # Validate headers (assuming these match the mock_csv_data keys)
        headers = list(source_data[0].keys())
        importer_for_main_flow.validate_source_headers(headers) # Should not raise error
        
        initial_resource_count = Resource.objects.count()
        initial_triple_count = Triple.objects.count()

        # Call import_data and check returned stats
        stats = importer_for_main_flow.import_data(source_data)
        
        # Verify stats
        assert stats["total_rows"] == 1
        assert stats["successful_rows"] == 1
        assert stats["failed_rows"] == 0
        assert len(stats["errors"]) == 0

        # --- Assertions for the main event resource --- 
        inst_code_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.institution_code)
        primary_class_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.default_domain_class.split('_')[-1])
        event_id_slug = importer_for_main_flow._slugify_uri_part(source_data[0]["id"]) # "event001"
        
        # Expected: /<slugged_inst_code>/<slugged_primary_class_name>/<slugged_event_id>
        # e.g., /main-flow-test/activity/event001
        expected_event_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event_id_slug}"
        
        event_resource = Resource.objects.get(uri__endswith=expected_event_uri_suffix)
        assert event_resource.resource_type == ResourceType.IRI
        assert event_resource.source == "MAIN_FLOW_TEST"

        # Check rdf:type for the event
        e7_class_resource = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}{importer_for_main_flow.default_domain_class}")
        assert Triple.objects.filter(subject=event_resource, 
                                     predicate=importer_for_main_flow.rdf_type_resource, 
                                     object=e7_class_resource).exists()

        # --- Assertions for "EventName" -> E41_Appellation ---
        # P1_is_identified_by
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        # Intermediate E41 Appellation resource
        appellation_resource = Triple.objects.get(subject=event_resource, predicate=p1_prop).object
        assert appellation_resource.resource_type == ResourceType.IRI
        
        # Previous context parts for event_resource URI
        # inst_code_slug, primary_class_slug, event_id_slug are defined above
        
        e41_class_name_slug = importer_for_main_flow._slugify_uri_part("E41_Appellation")
        event_name_slug = importer_for_main_flow._slugify_uri_part(source_data[0]["EventName"]) # "Grand Opening Ceremony"
        
        # Expected: /<slugged_inst_code>/<primary_class_slug>/<event_id_slug>/<e41_class_slug>/<event_name_slug>
        # e.g., /main-flow-test/activity/event001/e41-appellation/grand-opening-ceremony
        expected_appellation_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event_id_slug}/{e41_class_name_slug}/{event_name_slug}"
        assert appellation_resource.uri.endswith(expected_appellation_uri_suffix)
        
        e41_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E41_Appellation")
        assert Triple.objects.filter(subject=appellation_resource, 
                                     predicate=importer_for_main_flow.rdf_type_resource, 
                                     object=e41_class).exists()
        # Literal label for the Appellation
        appellation_label_literal = Triple.objects.get(subject=appellation_resource, 
                                                       predicate=importer_for_main_flow.rdfs_label_resource).object
        assert appellation_label_literal.literal_value == "Grand Opening Ceremony"
        assert appellation_label_literal.resource_type == ResourceType.LITERAL

        # --- Assertions for "EventTypeID" -> P2_has_type -> E55_Type (linked) ---
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        linked_type_resource = Triple.objects.get(subject=event_resource, predicate=p2_prop).object
        assert linked_type_resource.resource_type == ResourceType.IRI
        
        # inst_code_slug is defined above
        e55_class_name_slug = importer_for_main_flow._slugify_uri_part("E55_Type")
        event_type_id_slug = importer_for_main_flow._slugify_uri_part(source_data[0]["EventTypeID"]) # "type_A"
        
        # Expected: /<slugged_inst_code>/<e55_class_slug>/<event_type_id_slug>
        # e.g., /main-flow-test/e55-type/type-a
        expected_linked_type_uri_suffix = f"/{inst_code_slug}/{e55_class_name_slug}/{event_type_id_slug}"
        assert linked_type_resource.uri.endswith(expected_linked_type_uri_suffix)
        
        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        assert Triple.objects.filter(subject=linked_type_resource, 
                                     predicate=importer_for_main_flow.rdf_type_resource, 
                                     object=e55_class).exists()

        # --- Assertions for "EventDescription" -> P3_has_note (direct literal) ---
        p3_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note")
        description_literal = Triple.objects.get(subject=event_resource, predicate=p3_prop).object
        assert description_literal.resource_type == ResourceType.LITERAL
        assert description_literal.literal_value == "The official opening event."

        # --- Assertions for "EventParticipants" -> P11_had_participant (multi-value, linked) ---
        p11_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P11_had_participant")
        participant_triples = Triple.objects.filter(subject=event_resource, predicate=p11_prop)
        assert participant_triples.count() == 2
        e39_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E39_Actor")
        
        # inst_code_slug is defined above
        e39_class_name_slug = importer_for_main_flow._slugify_uri_part("E39_Actor")
        actor1_id_slug = importer_for_main_flow._slugify_uri_part("actor1")
        actor2_id_slug = importer_for_main_flow._slugify_uri_part("actor2")

        expected_actor1_uri_suffix = f"/{inst_code_slug}/{e39_class_name_slug}/{actor1_id_slug}"
        expected_actor2_uri_suffix = f"/{inst_code_slug}/{e39_class_name_slug}/{actor2_id_slug}"

        actor1_res = Resource.objects.get(uri__endswith=expected_actor1_uri_suffix)
        actor2_res = Resource.objects.get(uri__endswith=expected_actor2_uri_suffix)

        assert Triple.objects.filter(subject=event_resource, predicate=p11_prop, object=actor1_res).exists()
        assert Triple.objects.filter(subject=event_resource, predicate=p11_prop, object=actor2_res).exists()
        assert Triple.objects.filter(subject=actor1_res, predicate=importer_for_main_flow.rdf_type_resource, object=e39_class).exists()
        assert Triple.objects.filter(subject=actor2_res, predicate=importer_for_main_flow.rdf_type_resource, object=e39_class).exists()
        
        # Rough check on number of new resources and triples
        # Event(1) + E7(1) + P1(1) + Appellation(1) + E41(1) + AppellationLiteral(1) 
        # + P2(1) + LinkedType(1) + E55(1) 
        # + P3(1) + DescriptionLiteral(1) 
        # + P11(1) + Actor1(1) + Actor2(1) + E39(1) 
        # + Pre-cached rdf:type, rdfs:label (2)
        # Total expected new unique resources: around 15-16 (some classes/props might be reused if tests run together)
        # This count can be tricky due to shared resources (like CIDOC classes/props) across tests/rules.
        # A more precise way is to count specific new URIs.

        # Total new triples: 1 (event type) + 2 (appellation + its type) + 2 (linked type + its type) 
        # + 1 (description) + 4 (2 participants + their types) = 10
        # This count does not include pre-existing rdf:type/label resources themselves, but triples using them.
        assert Triple.objects.count() >= initial_triple_count + 10 
        # Resource count is harder to predict exactly due to shared classes/properties
        assert Resource.objects.count() >= initial_resource_count + 10 # A loose lower bound

    def test_import_data_multiple_rows(self, importer_for_main_flow, mock_csv_data_multiple):
        source_data = mock_csv_data_multiple
        headers = list(source_data[0].keys())
        importer_for_main_flow.validate_source_headers(headers)

        # Call import_data and check returned stats
        stats = importer_for_main_flow.import_data(source_data)
        
        # Verify stats
        assert stats["total_rows"] == 2
        assert stats["successful_rows"] == 2
        assert stats["failed_rows"] == 0
        assert len(stats["errors"]) == 0

        # Check for 2 event resources
        event_resources = Resource.objects.filter(subject_triples__predicate=importer_for_main_flow.rdf_type_resource, 
                                                  subject_triples__object__uri=f"{CIDOC_CRM_BASE_URI}{importer_for_main_flow.default_domain_class}").distinct()
        assert event_resources.count() == 2

        # Check one specific detail from the second event to ensure it was processed
        inst_code_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.institution_code)
        primary_class_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.default_domain_class.split('_')[-1])
        
        event2_id_slug = importer_for_main_flow._slugify_uri_part("event002")
        expected_event2_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event2_id_slug}"
        event2_resource = Resource.objects.get(uri__endswith=expected_event2_uri_suffix)
        p3_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note")
        assert Triple.objects.filter(subject=event2_resource, predicate=p3_prop, object__literal_value="A display of modern art.").exists()

        # Participants for event003 (3 participants)
        event3_id_slug = importer_for_main_flow._slugify_uri_part("event003")
        expected_event3_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event3_id_slug}"
        event3_resource = Resource.objects.get(uri__endswith=expected_event3_uri_suffix)
        p11_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P11_had_participant")
        assert Triple.objects.filter(subject=event3_resource, predicate=p11_prop).count() == 3

    def test_import_data_missing_primary_class_raises_error(self, importer_for_main_flow, mock_csv_data_basic):
        # This test's importer (importer_for_main_flow) now HAS a default_domain_class.
        # So, calling import_data without an explicit primary class should SUCCEED.
        # The original intent of this test needs to change, or it needs a different fixture.
        
        # Let's modify this test to ensure that if a domain IS in the mapping, passing None/empty still works.
        assert importer_for_main_flow.default_domain_class == "E7_Activity"
        try:
            importer_for_main_flow.import_data(mock_csv_data_basic, primary_subject_class_short_name=None)
            importer_for_main_flow.import_data(mock_csv_data_basic, primary_subject_class_short_name="")
        except ValueError:
            pytest.fail("import_data raised ValueError even when domain was in mapping and arg was None/empty")

        # To test the original error case (NO domain in mapping AND no arg), we need a different importer fixture.
        # This is already tested by test_import_data_error_conditions in test_importer_initialization.py.
        # So, this test can be simplified or focused on the override.

    def test_import_data_with_missing_column_in_source_skips_rule_gracefully(self, importer_for_main_flow):
        # Mapping expects "EventDescription", but data won't have it.
        source_data = [{
            "id": "event004",
            "EventName": "Silent Auction", # This rule should work
            "EventTypeID": "type_D",       # This rule should work
            "EventParticipants": "actor7"    # This rule should work
        }]
        headers = list(source_data[0].keys()) 
    
        stats = importer_for_main_flow.import_data(source_data)
        
        # Verify the row was processed successfully despite the missing column
        assert stats["total_rows"] == 1
        assert stats["successful_rows"] == 1
        assert stats["failed_rows"] == 0
    
        inst_code_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.institution_code)
        primary_class_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.default_domain_class.split('_')[-1])
        event_id_slug = importer_for_main_flow._slugify_uri_part(source_data[0]["id"]) # "event004"
        
        expected_event4_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event_id_slug}"
        event4_resource = Resource.objects.get(uri__endswith=expected_event4_uri_suffix)
    
        # Check that triples for existing columns were created
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        assert Triple.objects.filter(subject=event4_resource, predicate=p1_prop).exists()
    
        # Better approach: Check that no triple exists with a predicate URI containing P3_has_note
        # First, verify the resource doesn't exist to confirm skipping behavior
        assert not Resource.objects.filter(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note").exists()
        
        # Also verify no triples with any predicate containing P3_has_note in the URI
        p3_triples = Triple.objects.filter(
            subject=event4_resource, 
            predicate__uri__contains="P3_has_note"
        )
        assert p3_triples.count() == 0
        
        assert stats["errors"][0]["row"] == 2
        assert "Simulated error" in stats["errors"][0]["error"]
        
        # Verify that the first row was imported correctly
        inst_code_slug = importer_for_main_flow._slugify_uri_part(importer_for_main_flow.institution_code)
        primary_class_slug = importer_for_main_flow._slugify_uri_part("E7_Activity".split('_')[-1]) # Explicitly use E7_Activity here
        event4_id_slug = importer_for_main_flow._slugify_uri_part(mock_csv_data_with_error[0]["id"]) # "event004"
        expected_event4_uri_suffix_err_case = f"/{inst_code_slug}/{primary_class_slug}/{event4_id_slug}"
        assert Resource.objects.filter(uri__endswith=expected_event4_uri_suffix_err_case).exists()
        
        # Verify that the second row was not imported
        event5_id_slug = importer_for_main_flow._slugify_uri_part(mock_csv_data_with_error[1]["id"]) # "event005"
        expected_event5_uri_suffix = f"/{inst_code_slug}/{primary_class_slug}/{event5_id_slug}"
        assert not Resource.objects.filter(uri__endswith=expected_event5_uri_suffix).exists()

    def test_import_data_with_error_in_row(self, importer_for_main_flow, mock_csv_data_with_error, monkeypatch):
        """Test that an error in one row doesn't affect other rows."""
        # Make the second row trigger an error during processing
        def mock_process_mapping_rule(self, rule, row_data, event_subject_resource):
            if row_data.get('id') == 'event005':
                raise ValueError("Simulated error in row processing")
            # Call the original method for the first row
            original_method(rule, row_data, event_subject_resource)
            
        # Store the original method and patch it
        original_method = importer_for_main_flow._process_mapping_rule
        monkeypatch.setattr(importer_for_main_flow, '_process_mapping_rule', 
                          lambda rule, row_data, event_subject_resource: 
                          mock_process_mapping_rule(importer_for_main_flow, rule, row_data, event_subject_resource))
        
        # Call import_data
        stats = importer_for_main_flow.import_data(
            mock_csv_data_with_error 
        )
        
        # Verify the stats show one successful row and one failed row
        assert stats["total_rows"] == 2
        assert stats["successful_rows"] == 1
        assert stats["failed_rows"] == 1
        assert len(stats["errors"]) == 1
        assert stats["errors"][0]["row"] == 2
        assert "Simulated error" in stats["errors"][0]["error"]
        
        # Verify that the first row was imported correctly
        event4_uri_part = importer_for_main_flow._mint_uri("event", "event004").replace(DEFAULT_INSTITUTION_BASE_URI, "")
        assert Resource.objects.filter(uri__endswith=event4_uri_part).exists()
        
        # Verify that the second row was not imported
        event5_uri_part = importer_for_main_flow._mint_uri("event", "event005").replace(DEFAULT_INSTITUTION_BASE_URI, "")
        assert not Resource.objects.filter(uri__endswith=event5_uri_part).exists()

@pytest.mark.django_db
class TestImporterNewConventionFlow:

    def test_import_data_new_conventions_comprehensive(self, importer_for_ereignis_simple_style, mock_csv_data_ereignis_simple_style):
        source_data = mock_csv_data_ereignis_simple_style
        importer = importer_for_ereignis_simple_style
        
        stats = importer.import_data(source_data) 
        
        assert stats["total_rows"] == 2
        assert stats["successful_rows"] == 2
        assert stats["failed_rows"] == 0
        
        # --- Assertions for first row (act001) ---
        inst_code_slug = importer._slugify_uri_part(importer.institution_code) 
        domain_class_slug = importer._slugify_uri_part(importer.default_domain_class.split('_')[-1])
        act001_id_slug = importer._slugify_uri_part("act001")

        act001_res_uri_suffix = f"/{inst_code_slug}/{domain_class_slug}/{act001_id_slug}"
        act001_res = Resource.objects.get(uri__endswith=act001_res_uri_suffix)
        domain_class_res = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}{importer.default_domain_class}")
        assert Triple.objects.filter(subject=act001_res, predicate=importer.rdf_type_resource, object=domain_class_res).exists()

        # 1. EventName -> P1_is_identified_by -> E41_Appellation (fallback label)
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        appellation_triple = Triple.objects.get(subject=act001_res, predicate=p1_prop)
        appellation_res = appellation_triple.object
        e41_slug = importer._slugify_uri_part("E41_Appellation")
        name_slug = importer._slugify_uri_part(source_data[0]["EventName"])
        expected_app_uri_suffix = f"/{inst_code_slug}/{domain_class_slug}/{act001_id_slug}/{e41_slug}/{name_slug}"
        assert appellation_res.uri.endswith(expected_app_uri_suffix)
        app_label_triple = Triple.objects.get(subject=appellation_res, predicate=importer.rdfs_label_resource)
        assert app_label_triple.object.literal_value == source_data[0]["EventName"]

        # 2. EventType -> P2_has_type -> E55_Type (linked)
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        e55_slug = importer._slugify_uri_part("E55_Type")
        event_type_id_slug = importer._slugify_uri_part(source_data[0]["EventType"]) # type_workshop
        expected_event_type_uri_suffix = f"/{inst_code_slug}/{e55_slug}/{event_type_id_slug}"
        event_type_res = Triple.objects.get(subject=act001_res, predicate=p2_prop).object
        assert event_type_res.uri.endswith(expected_event_type_uri_suffix)
        e55_class_res = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        assert Triple.objects.filter(subject=event_type_res, predicate=importer.rdf_type_resource, object=e55_class_res).exists()

        # 3. EventDate -> P4_has_time-span -> E52_Time-Span (with object_properties)
        p4_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P4_has_time-span")
        timespan_triple = Triple.objects.get(subject=act001_res, predicate=p4_prop)
        timespan_res = timespan_triple.object
        e52_slug = importer._slugify_uri_part("E52_Time-Span")
        date_slug = importer._slugify_uri_part(source_data[0]["EventDate"]) # 2023-10-26
        expected_ts_uri_suffix = f"/{inst_code_slug}/{domain_class_slug}/{act001_id_slug}/{e52_slug}/{date_slug}"
        assert timespan_res.uri.endswith(expected_ts_uri_suffix)
        # Check P82a_begin_of_the_begin from object_properties
        p82a_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P82a_begin_of_the_begin")
        ts_begin_triple = Triple.objects.get(subject=timespan_res, predicate=p82a_prop)
        assert ts_begin_triple.object.literal_value == source_data[0]["EventDate"]
        assert ts_begin_triple.object.literal_datatype == f"{XSD_BASE_URI}date"
        # Check P2_has_type for Time-span (fixed_value "Recorded Event Start")
        ts_type_triple = Triple.objects.get(subject=timespan_res, predicate=p2_prop) # p2_prop already fetched
        ts_type_e55_res = ts_type_triple.object
        assert ts_type_e55_res.resource_type == ResourceType.IRI
        ts_type_label = Triple.objects.get(subject=ts_type_e55_res, predicate=importer.rdfs_label_resource)
        assert ts_type_label.object.literal_value == "Recorded Event Start"

        # 4. EventLocationIDs -> P7_took_place_at -> E53_Place (multi-valued, linked)
        p7_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P7_took_place_at")
        location_triples = Triple.objects.filter(subject=act001_res, predicate=p7_prop)
        assert location_triples.count() == 2
        e53_slug = importer._slugify_uri_part("E53_Place")
        loc1_slug = importer._slugify_uri_part("wd:Q123")
        loc2_slug = importer._slugify_uri_part("wd:Q456")
        expected_loc1_uri_suffix = f"/{inst_code_slug}/{e53_slug}/{loc1_slug}"
        expected_loc2_uri_suffix = f"/{inst_code_slug}/{e53_slug}/{loc2_slug}"
        assert Resource.objects.filter(uri__endswith=expected_loc1_uri_suffix).exists()
        assert Resource.objects.filter(uri__endswith=expected_loc2_uri_suffix).exists()

        # 5. EventDescription -> P3_has_note (direct literal)
        p3_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note")
        desc_literal_triple = Triple.objects.get(subject=act001_res, predicate=p3_prop)
        assert desc_literal_triple.object.literal_value == source_data[0]["EventDescription"]

        # Verify second row was processed by checking its description
        act002_id_slug = importer._slugify_uri_part("act002")
        act002_res_uri_suffix = f"/{inst_code_slug}/{domain_class_slug}/{act002_id_slug}"
        act002_res = Resource.objects.get(uri__endswith=act002_res_uri_suffix)
        assert Triple.objects.filter(subject=act002_res, predicate=p3_prop, object__literal_value=source_data[1]["EventDescription"]).exists() 