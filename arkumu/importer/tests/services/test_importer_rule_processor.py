# Tests for JSONMappingImporter._process_mapping_rule 

import pytest
import json
import logging
from datetime import datetime
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
def rule_processor_mapping_content():
    # Minimal content, specific rules will be passed directly in tests
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
    # Create a simple subject resource for testing rules against
    event_uri = importer_for_rule_processing._mint_uri("event", "evt123")
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

    def test_rule_skip_missing_source_column_in_rule(self, importer_for_rule_processing, mock_event_subject):
        rule = {"predicate": "P1"} # Missing source_column
        row_data = {"colA": "valueA"}
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        assert Triple.objects.count() == initial_triple_count # No triple created

    def test_rule_skip_source_column_not_in_row_data(self, importer_for_rule_processing, mock_event_subject):
        rule = {"source_column": "NonExistentCol", "predicate": "P1"}
        row_data = {"colA": "valueA"}
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        assert Triple.objects.count() == initial_triple_count

    def test_rule_skip_empty_source_values_after_processing(self, importer_for_rule_processing, mock_event_subject):
        rule = {"source_column": "ColWithEmptySplit", "predicate": "P1", "note": "Separated by a ';'"}
        row_data = {"ColWithEmptySplit": ";;;"} # Will result in empty list
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        assert Triple.objects.count() == initial_triple_count
    
    def test_rule_skip_source_value_is_none(self, importer_for_rule_processing, mock_event_subject):
        rule = {"source_column": "NullableCol", "predicate": "P1"}
        row_data = {"NullableCol": None}
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        assert Triple.objects.count() == initial_triple_count

    def test_rule_skip_missing_predicate_in_rule(self, importer_for_rule_processing, mock_event_subject):
        rule = {"source_column": "colA"} # Missing predicate
        row_data = {"colA": "valueA"}
        initial_triple_count = Triple.objects.count()
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        assert Triple.objects.count() == initial_triple_count

    def test_process_direct_literal_object(self, importer_for_rule_processing, mock_event_subject):
        rule = {"source_column": "Description", "predicate": "P3_has_note"}
        row_data = {"Description": "A simple note."}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        p3_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note")
        created_triple = Triple.objects.get(subject=mock_event_subject, predicate=p3_prop)
        assert created_triple.object.resource_type == ResourceType.LITERAL
        assert created_triple.object.literal_value == "A simple note."
        assert created_triple.object.literal_datatype == f"{XSD_BASE_URI}string" # From _infer_datatype default

    def test_process_linked_resource_object(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "PlaceID", 
            "predicate": "P7_took_place_at", 
            "object_class": "E53_Place",
            "object_column": "place_id_field", # Name of the ID field for the linked entity
            "link_columns": True
        }
        row_data = {"PlaceID": "placeXYZ"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        p7_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P7_took_place_at")
        created_triple = Triple.objects.get(subject=mock_event_subject, predicate=p7_prop)
        object_res = created_triple.object
        
        assert object_res.resource_type == ResourceType.IRI
        # Check part of URI based on _mint_uri logic (e.g., /e53-place/placexyz)
        assert "/e53-place/placexyz" in object_res.uri 
        assert object_res.source == importer_for_rule_processing.institution_code
        assert object_res.source_field == "place_id_field=placeXYZ"
        
        # Check rdf:type for the linked object
        e53_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E53_Place")
        assert Triple.objects.filter(subject=object_res, 
                                     predicate=importer_for_rule_processing.rdf_type_resource, 
                                     object=e53_class).exists()

    def test_process_intermediate_typed_instance_appellation(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "ObjectName", 
            "predicate": "P1_is_identified_by", 
            "object_class": "E41_Appellation"
        }
        row_data = {"ObjectName": "The Masterpiece"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        created_triple = Triple.objects.get(subject=mock_event_subject, predicate=p1_prop)
        intermediate_res = created_triple.object
        
        assert intermediate_res.resource_type == ResourceType.IRI
        # Check rdf:type for the intermediate E41 Appellation
        e41_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E41_Appellation")
        assert Triple.objects.filter(subject=intermediate_res, 
                                     predicate=importer_for_rule_processing.rdf_type_resource, 
                                     object=e41_class).exists()
        
        # Check rdfs:label for the intermediate E41 Appellation
        label_triple = Triple.objects.get(subject=intermediate_res, 
                                          predicate=importer_for_rule_processing.rdfs_label_resource)
        assert label_triple.object.resource_type == ResourceType.LITERAL
        assert label_triple.object.literal_value == "The Masterpiece"

    def test_process_multi_value_linked_resource(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "ActorIDs", 
            "predicate": "P11_had_participant", 
            "object_class": "E39_Actor",
            "object_column": "actor_system_id",
            "link_columns": True,
            "note": "Multi-values separated by a ';' please"
        }
        row_data = {"ActorIDs": "actor123; actor456"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        p11_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P11_had_participant")
        created_triples = Triple.objects.filter(subject=mock_event_subject, predicate=p11_prop)
        assert created_triples.count() == 2
        
        e39_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E39_Actor")
        object_uris = sorted([t.object.uri for t in created_triples])
        
        actor1_uri = importer_for_rule_processing._mint_uri("e39-actor", "actor123")
        actor2_uri = importer_for_rule_processing._mint_uri("e39-actor", "actor456")
        
        assert actor1_uri in object_uris
        assert actor2_uri in object_uris
        
        actor1_res = Resource.objects.get(uri=actor1_uri)
        actor2_res = Resource.objects.get(uri=actor2_uri)

        assert Triple.objects.filter(subject=actor1_res, predicate=importer_for_rule_processing.rdf_type_resource, object=e39_class).exists()
        assert Triple.objects.filter(subject=actor2_res, predicate=importer_for_rule_processing.rdf_type_resource, object=e39_class).exists()
        assert actor1_res.source_field == "actor_system_id=actor123"
        assert actor2_res.source_field == "actor_system_id=actor456"
        
    def test_process_multi_value_with_explicit_separator(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "Keywords", 
            "predicate": "P2_has_type", 
            "object_class": "E55_Type",
            "object_column": "keyword_id",
            "link_columns": True,
            "multi_value_separator": "|" # Explicit separator
        }
        row_data = {"Keywords": "keyword1|keyword2|keyword3"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        created_triples = Triple.objects.filter(subject=mock_event_subject, predicate=p2_prop)
        assert created_triples.count() == 3
        
        # Check that all three keywords were processed
        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        for i in range(1, 4):
            keyword_uri = importer_for_rule_processing._mint_uri("e55-type", f"keyword{i}")
            keyword_res = Resource.objects.get(uri=keyword_uri)
            assert Triple.objects.filter(
                subject=mock_event_subject, 
                predicate=p2_prop, 
                object=keyword_res
            ).exists()
            assert Triple.objects.filter(
                subject=keyword_res, 
                predicate=importer_for_rule_processing.rdf_type_resource, 
                object=e55_class
            ).exists()
            
    def test_process_time_span(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "StartDate", 
            "predicate": "P4_has_time-span", 
            "object_class": "E52_Time-Span",
            "is_start_date": True
        }
        row_data = {
            "StartDate": "2023-05-15",
            "StartDateApprox": "true"  # Approximation indicator
        }
        
        # Add approximation column reference to the rule
        rule["approximation_column"] = "StartDateApprox"
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        # Check for main triple connecting event to timespan
        p4_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P4_has_time-span")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p4_prop)
        timespan_res = main_triple.object
        
        # Check rdf:type for the timespan
        e52_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E52_Time-Span")
        assert Triple.objects.filter(
            subject=timespan_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e52_class
        ).exists()
        
        # Check P82a_begin_of_the_begin property
        begin_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P82a_begin_of_the_begin")
        begin_triple = Triple.objects.get(subject=timespan_res, predicate=begin_prop)
        date_literal = begin_triple.object
        
        assert date_literal.resource_type == ResourceType.LITERAL
        assert date_literal.literal_value == "2023-05-15"
        assert date_literal.literal_datatype == f"{XSD_BASE_URI}date"
        
        # Check the approximation qualifier
        qual_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P79_beginning_is_qualified_by")
        qual_triple = Triple.objects.get(subject=timespan_res, predicate=qual_prop)
        qual_literal = qual_triple.object
        
        assert qual_literal.resource_type == ResourceType.LITERAL
        assert qual_literal.literal_value == "approximate"
        
    def test_process_time_span_with_custom_properties(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "EndDate", 
            "predicate": "P4_has_time-span", 
            "object_class": "E52_Time-Span",
            "is_start_date": False,
            "end_property": "P82b_end_of_the_end",
            "end_qualification_property": "P80_end_is_qualified_by"
        }
        row_data = {
            "EndDate": "2023-06-30",
            "EndDateApprox": "yes"  # Approximation indicator
        }
        
        # Add approximation column reference to the rule
        rule["approximation_column"] = "EndDateApprox"
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        # Check main triple and timespan type
        p4_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P4_has_time-span")
        timespan_res = Triple.objects.get(subject=mock_event_subject, predicate=p4_prop).object
        
        # Check end date property
        end_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P82b_end_of_the_end")
        end_triple = Triple.objects.get(subject=timespan_res, predicate=end_prop)
        date_literal = end_triple.object
        
        assert date_literal.literal_value == "2023-06-30"
        
        # Check qualification property
        qual_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P80_end_is_qualified_by")
        qual_triple = Triple.objects.get(subject=timespan_res, predicate=qual_prop)
        assert qual_triple.object.literal_value == "approximate"
        
    def test_process_time_span_invalid_date(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "DateText", 
            "predicate": "P4_has_time-span", 
            "object_class": "E52_Time-Span"
        }
        row_data = {"DateText": "Early 19th century"}  # Not a parseable date
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        # Check main triple and timespan type
        p4_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P4_has_time-span")
        timespan_res = Triple.objects.get(subject=mock_event_subject, predicate=p4_prop).object
        
        # Should fallback to using rdfs:label
        label_triple = Triple.objects.get(
            subject=timespan_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.literal_value == "Early 19th century"
        
    def test_process_related_data_lookup(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "DescriptionID", 
            "predicate": "P3_has_note",
            "lookup_type": "related_table_literal",
            "related_source": "descriptions",
            "related_source_key_column": "id",
            "related_source_value_column": "text",
            "related_source_language_column": "language"
        }
        row_data = {"DescriptionID": "desc1"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)
        
        # Check that the description was looked up and set as the note
        p3_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P3_has_note")
        note_triple = Triple.objects.get(subject=mock_event_subject, predicate=p3_prop)
        
        # Should have the text from the related source
        assert note_triple.object.literal_value == "First related text"
        # Should have the language from the related source
        assert note_triple.object.literal_language == "en"
        # Source field should show the lookup path
        assert "desc1→First related text" in note_triple.object.source_field 

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
                    "predicate": "P2_has_type", # Or rdf:type, but P2 is more common for this pattern
                    "object_class": "E55_Type", # Type of appellation, e.g., nickname, official name
                    "fixed_value": "Official Name" # This will become the label of the E55_Type instance
                }
            ]
        }
        row_data = {"ActorName": "Some Actor"} # This value creates the E41 instance
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)

        # 1. Check main triple: Event -> P1_is_identified_by -> E41_Appellation
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p1_prop)
        intermediate_appellation_res = main_triple.object
        
        assert intermediate_appellation_res.resource_type == ResourceType.IRI
        # URI for E41 is minted using "Some Actor" and "e41-appellation"
        assert "/e41-appellation/some_actor" in intermediate_appellation_res.uri 

        # 2. Check rdf:type for the intermediate E41 Appellation
        e41_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E41_Appellation")
        assert Triple.objects.filter(
            subject=intermediate_appellation_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e41_class
        ).exists()

        # 3. Check sub-rule: E41_Appellation -> rdfs:label -> "The Great Actor"
        label_triple = Triple.objects.get(
            subject=intermediate_appellation_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.resource_type == ResourceType.LITERAL
        assert label_triple.object.literal_value == "The Great Actor"

        # 4. Check sub-rule: E41_Appellation -> P2_has_type -> E55_Type ("Official Name")
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        type_triple = Triple.objects.get(subject=intermediate_appellation_res, predicate=p2_prop)
        appellation_type_res = type_triple.object # This is an E55_Type instance

        assert appellation_type_res.resource_type == ResourceType.IRI
        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        assert Triple.objects.filter(
            subject=appellation_type_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e55_class
        ).exists()
        
        # The E55_Type instance should be labeled with "Official Name" (auto-label from fixed_value)
        type_label_triple = Triple.objects.get(
            subject=appellation_type_res,
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert type_label_triple.object.literal_value == "Official Name"
        assert "/e55-type/official_name" in appellation_type_res.uri # URI minted from class and fixed_value 

    def test_intermediate_with_object_properties_use_parent_value(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "WorkTitle", 
            "predicate": "P102_has_title", 
            "object_class": "E35_Title",
            "object_properties": [
                {
                    "predicate": "rdfs:label",
                    "use_parent_value": True # Use "Original Work Title" from WorkTitle column
                },
                {
                    "predicate": "P2_has_type",
                    "object_class": "E55_Type",
                    "fixed_value": "Main Title"
                }
            ]
        }
        row_data = {"WorkTitle": "Original Work Title"}
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)

        # 1. Check main triple: Event -> P102_has_title -> E35_Title
        p102_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P102_has_title")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p102_prop)
        intermediate_title_res = main_triple.object
        
        assert intermediate_title_res.resource_type == ResourceType.IRI
        assert "/e35-title/original_work_title" in intermediate_title_res.uri 

        # 2. Check rdf:type for the intermediate E35_Title
        e35_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E35_Title")
        assert Triple.objects.filter(
            subject=intermediate_title_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e35_class
        ).exists()

        # 3. Check sub-rule: E35_Title -> rdfs:label -> "Original Work Title" (from use_parent_value)
        label_triple = Triple.objects.get(
            subject=intermediate_title_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.resource_type == ResourceType.LITERAL
        assert label_triple.object.literal_value == "Original Work Title"

        # 4. Check sub-rule: E35_Title -> P2_has_type -> E55_Type ("Main Title")
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        type_triple = Triple.objects.get(subject=intermediate_title_res, predicate=p2_prop)
        title_type_res = type_triple.object

        assert title_type_res.resource_type == ResourceType.IRI
        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        assert Triple.objects.filter(
            subject=title_type_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e55_class
        ).exists()
        type_label_triple = Triple.objects.get(
            subject=title_type_res,
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert type_label_triple.object.literal_value == "Main Title"

    def test_intermediate_with_object_properties_source_column(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "Identifier", # Main value to create the E42_Identifier
            "predicate": "P1_is_identified_by", 
            "object_class": "E42_Identifier",
            "object_properties": [
                {
                    "predicate": "rdfs:label", # Label the E42_Identifier itself
                    "use_parent_value": True
                },
                {
                    "predicate": "P2_has_type", # Type of the identifier
                    "object_class": "E55_Type",
                    "source_column": "IdentifierType" # Get type from a different CSV column
                }
            ]
        }
        row_data = {
            "Identifier": "ARK:12345/foo",
            "IdentifierType": "Persistent ARK ID"
        }
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)

        # 1. Check main triple: Event -> P1_is_identified_by -> E42_Identifier
        p1_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P1_is_identified_by")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p1_prop)
        intermediate_identifier_res = main_triple.object
        
        assert intermediate_identifier_res.resource_type == ResourceType.IRI
        assert "/e42-identifier/ark:12345%2Ffoo" in intermediate_identifier_res.uri 

        # 2. Check rdf:type for E42_Identifier
        e42_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E42_Identifier")
        assert Triple.objects.filter(
            subject=intermediate_identifier_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e42_class
        ).exists()

        # 3. Check rdfs:label for E42_Identifier (from use_parent_value)
        label_triple = Triple.objects.get(
            subject=intermediate_identifier_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.literal_value == "ARK:12345/foo"

        # 4. Check sub-rule: E42_Identifier -> P2_has_type -> E55_Type ("Persistent ARK ID")
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        type_triple = Triple.objects.get(subject=intermediate_identifier_res, predicate=p2_prop)
        identifier_type_res = type_triple.object # This is an E55_Type instance

        assert identifier_type_res.resource_type == ResourceType.IRI
        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        assert Triple.objects.filter(
            subject=identifier_type_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e55_class
        ).exists()
        
        # The E55_Type instance should be labeled with "Persistent ARK ID" (from source_column)
        type_label_triple = Triple.objects.get(
            subject=identifier_type_res,
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert type_label_triple.object.literal_value == "Persistent ARK ID"
        assert "/e55-type/persistent_ark_id" in identifier_type_res.uri

    def test_intermediate_with_object_properties_object_uri_pattern(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "MaterialName", # Value to create the E57_Material instance
            "predicate": "P45_consists_of", 
            "object_class": "E57_Material",
            "object_properties": [
                {
                    "predicate": "rdfs:label", 
                    "use_parent_value": True # Label E57 with "Wood"
                },
                {
                    "predicate": "P2_has_type", # Type of the material
                    "object_uri_pattern": "http://vocab.getty.edu/aat/{value}",
                    "source_column": "MaterialAAT_ID" # Source for the ID in the URI pattern
                    # Optionally, we could add "object_class": "E55_Type" here if we want to also assert rdf:type for the AAT URI
                }
            ]
        }
        row_data = {
            "MaterialName": "Wood",
            "MaterialAAT_ID": "300012295" # AAT ID for Wood
        }
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)

        # 1. Check main triple: Event -> P45_consists_of -> E57_Material
        p45_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P45_consists_of")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p45_prop)
        intermediate_material_res = main_triple.object
        
        assert intermediate_material_res.resource_type == ResourceType.IRI
        assert "/e57-material/wood" in intermediate_material_res.uri 

        # 2. Check rdf:type for E57_Material
        e57_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E57_Material")
        assert Triple.objects.filter(
            subject=intermediate_material_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e57_class
        ).exists()

        # 3. Check rdfs:label for E57_Material (from use_parent_value)
        label_triple = Triple.objects.get(
            subject=intermediate_material_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.literal_value == "Wood"

        # 4. Check sub-rule: E57_Material -> P2_has_type -> <AAT_URI>
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        type_triple = Triple.objects.get(subject=intermediate_material_res, predicate=p2_prop)
        material_type_res_uri = type_triple.object 

        assert material_type_res_uri.resource_type == ResourceType.IRI
        expected_aat_uri = "http://vocab.getty.edu/aat/300012295"
        assert material_type_res_uri.uri == expected_aat_uri
        
        # Ensure the AAT URI resource was created (or fetched if pre-existing)
        aat_resource = Resource.objects.get(uri=expected_aat_uri)
        assert aat_resource is not None

    def test_intermediate_with_object_properties_sub_rule_multi_value(self, importer_for_rule_processing, mock_event_subject):
        rule = {
            "source_column": "DocumentReference", # Creates E31_Document
            "predicate": "P70_documents", 
            "object_class": "E31_Document",
            "object_properties": [
                {
                    "predicate": "rdfs:label", 
                    "use_parent_value": True
                },
                {
                    "predicate": "P2_has_type", # Document can have multiple types
                    "object_class": "E55_Type",
                    "source_column": "DocumentTypes", # e.g., "Invoice;Report;Letter"
                    "multi_value_separator": ";"
                }
            ]
        }
        row_data = {
            "DocumentReference": "DOC-001",
            "DocumentTypes": "Invoice;Report;Letter"
        }
        
        importer_for_rule_processing._process_mapping_rule(rule, row_data, mock_event_subject)

        # 1. Check main triple: Event -> P70_documents -> E31_Document
        p70_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P70_documents")
        main_triple = Triple.objects.get(subject=mock_event_subject, predicate=p70_prop)
        intermediate_doc_res = main_triple.object
        
        assert intermediate_doc_res.resource_type == ResourceType.IRI
        assert "/e31-document/doc-001" in intermediate_doc_res.uri

        # 2. Check rdf:type for E31_Document
        e31_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E31_Document")
        assert Triple.objects.filter(
            subject=intermediate_doc_res, 
            predicate=importer_for_rule_processing.rdf_type_resource, 
            object=e31_class
        ).exists()

        # 3. Check rdfs:label for E31_Document
        label_triple = Triple.objects.get(
            subject=intermediate_doc_res, 
            predicate=importer_for_rule_processing.rdfs_label_resource
        )
        assert label_triple.object.literal_value == "DOC-001"

        # 4. Check sub-rule for P2_has_type (multiple types)
        p2_prop = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}P2_has_type")
        type_triples = Triple.objects.filter(subject=intermediate_doc_res, predicate=p2_prop)
        assert type_triples.count() == 3

        e55_class = Resource.objects.get(uri=f"{CIDOC_CRM_BASE_URI}E55_Type")
        expected_type_labels = ["Invoice", "Report", "Letter"]
        created_type_labels = []

        for type_triple in type_triples:
            doc_type_res = type_triple.object
            assert doc_type_res.resource_type == ResourceType.IRI
            assert Triple.objects.filter(
                subject=doc_type_res, 
                predicate=importer_for_rule_processing.rdf_type_resource, 
                object=e55_class
            ).exists()
            
            type_label_triple = Triple.objects.get(
                subject=doc_type_res,
                predicate=importer_for_rule_processing.rdfs_label_resource
            )
            created_type_labels.append(type_label_triple.object.literal_value)
            # Check URI minting for these types
            assert f"/e55-type/{type_label_triple.object.literal_value.lower()}" in doc_type_res.uri

        assert sorted(created_type_labels) == sorted(expected_type_labels)