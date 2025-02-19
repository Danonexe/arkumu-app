"""
CIDOC CRM Mappings for Metadata Models

AuditLog:
- Maps to E5_Event (more specific than E7_Activity, represents changes/modifications to objects)
- id -> P48_has_preferred_identifier
- persisted_object_id -> P67_refers_to (reference to the affected object)
- property_name -> P3_has_note (specifies which property was changed)
- date_created -> P4_has_time-span (E52_Time-Span)
- last_updated -> P4_has_time-span (E52_Time-Span)
- event_name -> P2_has_type (E55_Type)
- actor -> P14_carried_out_by (E39_Actor)
- new_value -> P190_has_symbolic_content (current state)
- old_value -> P190_has_symbolic_content (previous state)
- class_name -> P2_has_type (E55_Type, specifies the type of object modified)
- persisted_object_version -> P3_has_note (version information)
- uri -> P1_is_identified_by (E41_Appellation)

DataImporter:
- Maps to E7_Activity (represents data import/transfer activity)
- id -> P48_has_preferred_identifier
- source_table -> P16_used_specific_object (E75_Conceptual_Object)
- destination_table -> P16_used_specific_object (E75_Conceptual_Object)
- last_updated_by -> P14_carried_out_by (E39_Actor)
- created_by -> P14_carried_out_by (E39_Actor)
- date_created -> P4_has_time-span (E52_Time-Span)
- last_updated -> P4_has_time-span (E52_Time-Span)
- data_source_id -> P1_is_identified_by (E42_Identifier)
- data_destination_id -> P1_is_identified_by (E42_Identifier)
- contributor -> P14_carried_out_by (E39_Actor)
- status -> P2_has_type (E55_Type)

Tooltip:
- Maps to E33_Linguistic_Object (represents multilingual textual content)
- id -> P48_has_preferred_identifier
- tt_text_en -> P72_has_language (E56_Language: "en") + P190_has_symbolic_content
- tt_text_de -> P72_has_language (E56_Language: "de") + P190_has_symbolic_content
- view -> P2_has_type (E55_Type, context where tooltip appears)
- field -> P2_has_type (E55_Type, specific field tooltip relates to)

Note: The unique_together constraint on (view, field) ensures each context has unique tooltip content
"""

# The actual model implementations would go here if needed
# This file serves as a mapping reference between the metadata models
# and their corresponding CIDOC CRM entities and properties
