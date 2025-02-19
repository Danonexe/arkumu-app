"""
CIDOC CRM Mappings for Licensing Models

BestehenderLizenzvertrag (Existing License Agreement):
- Maps to E72_Legal_Object
- Properties:
  - lizenz_status -> P2_has_type (E55_Type)
  - pdf -> P70_documents (E31_Document)
  - vertrags_text_de/en -> P3_has_note (E62_String)
  - hochschule -> P50_has_current_keeper (E40_Legal_Body)
  - bezeichnung_de/en -> P1_is_identified_by (E41_Appellation)
  - uri -> P1_is_identified_by (E41_Appellation)

ProduktId (Product ID):
- Maps to E42_Identifier
- Properties:
  - wert (value) -> P190_has_symbolic_content (E62_String)
  - nummernart -> P2_has_type (E55_Type)
  - informationstraeger -> P48_has_preferred_identifier (E22_Human-Made_Object)
- Temporal Properties:
  - date_created -> P95_has_formed (E66_Formation)
  - last_updated -> P4_has_time-span (E52_Time-Span)

Nummernart (Number Type):
- Maps to E55_Type
- Properties:
  - name_de/en -> P1_is_identified_by (E41_Appellation)
  - gndid -> P48_has_preferred_identifier (E42_Identifier)
  - wikidataid -> P48_has_preferred_identifier (E42_Identifier)
- Temporal Properties:
  - date_created -> P95_has_formed (E66_Formation)
  - last_updated -> P4_has_time-span (E52_Time-Span)

Note: The user tracking fields (created_by, last_updated_by) can be mapped to 
P14_carried_out_by (E21_Person) through respective creation/modification events.
"""
