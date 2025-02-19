"""
CIDOC-CRM Mappings for Project-related Models

Core concept mappings:
- Projekt -> E7_Activity (represents a creative/production activity)
           + Can also be considered as E36_Visual_Item for the resulting work
- ProjektArt -> E55_Type (classification of projects)
- ProjektKategorie -> E55_Type (hierarchical categories)
- Titel -> E35_Title (titles/names of works)
- ProjektBeschreibung -> E62_String (descriptions)

Additional key relationships:
- P2_has_type: Used for classifications and types
- P67_refers_to: For references between entities
- P70_documents: For documentation relationships
- P14_carried_out_by: For actor associations
"""

# Projekt Model
# Primary: E7_Activity
# Secondary: E36_Visual_Item (for the resulting work)
"""
Field mappings:
- id -> None (technical identifier)
- normdatei -> P1_is_identified_by (E42_Identifier)
- dateiabfrage_dokument -> P70_documents (E31_Document)
- last_updated_by -> P14_carried_out_by (E21_Person)
- bestehender_lizenzvertrag -> P104_is_subject_to (E30_Right)
- date_created -> P4_has_time-span (E52_Time-Span)
- signatur -> P1_is_identified_by (E42_Identifier)
- rechtsstatus -> P104_is_subject_to (E30_Right)
- letzte_modifikation -> P4_has_time-span (E52_Time-Span)
- kommentar_de/en -> P3_has_note (E62_String)
- art_lizenzvertrag -> P2_has_type (E55_Type)
- neuer_lizenzvertrag -> P104_is_subject_to (E30_Right)
- tonart -> P2_has_type (E55_Type)
- sonderregelung -> P2_has_type (E55_Type)
- bevorzugter_titel -> P102_has_title (E35_Title)
- dokumentation_lizenzvertrag -> P70_documents (E31_Document)
- externe_projekt_webseite -> P1_is_identified_by (E42_Identifier)
                           + P67_refers_to (E73_Information_Object)
- signatur_einlieferer -> P1_is_identified_by (E42_Identifier)
- hochschule -> P14_carried_out_by (E40_Legal_Body)
- status -> P2_has_type (E55_Type)
- verzeichnisnummern -> P1_is_identified_by (E42_Identifier)
- dauer -> P43_has_dimension (E54_Dimension)
- kommentar_intern -> P3_has_note (E62_String)
- erstellungs_datum_einlieferer -> P4_has_time-span (E52_Time-Span)
- wikidataid -> P1_is_identified_by (E42_Identifier)
- gndid -> P1_is_identified_by (E42_Identifier)

Additional implicit relationships:
- P94i_was_created_by: Links to creation event
- P105_right_held_by: For rights management
- P67_refers_to: For external references
"""

# ProjektArt Model
# E55_Type
"""
Field mappings:
- id -> None (technical identifier)
- date_created -> P95_has_formed (E66_Formation)
- last_updated -> P4_has_time-span (E52_Time-Span)
- wikidataid -> P1_is_identified_by (E42_Identifier)
- name_en/de -> P1_is_identified_by (E41_Appellation)
- last_updated_by/created_by -> P14_carried_out_by (E21_Person)
"""

# ProjektKategorie Model
# E55_Type with hierarchical structure
"""
Field mappings:
- id -> None (technical identifier)
- date_created -> P95_has_formed (E66_Formation)
- last_updated -> P4_has_time-span (E52_Time-Span)
- name_en/de -> P1_is_identified_by (E41_Appellation)
- parent -> P127_has_broader_term (E55_Type)
- last_updated_by/created_by -> P14_carried_out_by (E21_Person)
- aatid -> P1_is_identified_by (E42_Identifier)
- wikidataid -> P1_is_identified_by (E42_Identifier)
- gndid -> P1_is_identified_by (E42_Identifier)
"""

# Titel Model
# E35_Title
"""
Field mappings:
- id -> None (technical identifier)
- last_updated_by/created_by -> P14_carried_out_by (E21_Person)
- date_created -> P95_has_formed (E66_Formation)
- sprache_titel -> P72_has_language (E56_Language)
- last_updated -> P4_has_time-span (E52_Time-Span)
- projekt -> P102i_is_title_of (E7_Activity)
- untertitel -> P1_is_identified_by (E41_Appellation)
- titel -> P190_has_symbolic_content (E62_String)
- sprache_untertitel -> P72_has_language (E56_Language)
- rang -> P166_was_a_presence_of (E92_Spacetime_Volume)
"""

# ProjektBeschreibung Model
# E33_Linguistic_Object
"""
Field mappings:
- id -> None (technical identifier)
- last_updated_by/created_by -> P14_carried_out_by (E21_Person)
- date_created -> P95_has_formed (E66_Formation)
- last_updated -> P4_has_time-span (E52_Time-Span)
- projekt -> P67i_is_referred_to_by (E7_Activity)
- sprache -> P72_has_language (E56_Language)
- rang -> P166_was_a_presence_of (E92_Spacetime_Volume)
- beschreibung -> P190_has_symbolic_content (E62_String)
"""

# ProjektRelation Model
# E13_Attribute_Assignment
"""
Field mappings:
- id -> None (technical identifier)
- art_der_relation -> P177_assigned_property_type (E55_Type)
- projekt1/projekt2 -> P140_assigned_attribute_to (E1_CRM_Entity)
- projekt_relationen_idx -> P140_assigned_attribute_to (E1_CRM_Entity)
"""

# ProjektEigenschaftswert Model
# E13_Attribute_Assignment
"""
Field mappings:
- id -> None (technical identifier)
- projekt -> P140_assigned_attribute_to (E1_CRM_Entity)
- eigenschaft -> P177_assigned_property_type (E55_Type)
- wert -> P141_assigned (E1_CRM_Entity)
- projekt_eigenschaften_idx -> P140_assigned_attribute_to (E1_CRM_Entity)
"""

# Association Models
"""
ProjektProjektArt:
- Links E7_Activity (Projekt) with E55_Type (ProjektArt)
- P2_has_type relationship
- Additional context: P67_refers_to for related information

ProjektProjektKategorie:
- Links E7_Activity (Projekt) with E55_Type (ProjektKategorie)
- P2_has_type relationship
- Supports hierarchical categorization through P127_has_broader_term

ProjektSchlagworte:
- Links E7_Activity (Projekt) with E55_Type (Schlagwort)
- P2_has_type relationship
- Additional context: P67_refers_to for subject references

ProjektInhaltswarnung:
- Links E7_Activity (Projekt) with E55_Type (Inhaltswarnung)
- P2_has_type relationship
- Additional context: P67_refers_to for content warnings

ProjektFileUpload:
- Links E7_Activity (Projekt) with E31_Document (FileUpload)
- P70_documents relationship
- Additional context: P104_is_subject_to for rights management

ProjektEreignis:
- Links E7_Activity (Projekt) with E5_Event (Ereignis)
- P9_consists_of relationship
- Additional context: P4_has_time-span for temporal aspects

ProjektOrganisationseinheit:
- Links E7_Activity (Projekt) with E40_Legal_Body (Organisationseinheit)
- P14_carried_out_by relationship
- Additional context: P107_has_current_or_former_member for membership

ProjektAngegebeneNutzungsrechte:
- Links E7_Activity (Projekt) with E30_Right
- P104_is_subject_to relationship
- Additional context: P105_right_held_by for rights holders

ProjektKategorieSynonyme:
- Links E55_Type (ProjektKategorie) with E41_Appellation
- P1_is_identified_by relationship
- Additional context: P139_has_alternative_form for synonyms
"""

"""
Additional considerations and improvements:

1. Temporal Aspects:
   - All date fields should use E52_Time-Span
   - Consider using E2_Temporal_Entity for complex temporal relationships

2. Rights Management:
   - Enhanced mapping for license and rights management using E30_Right
   - Consider adding P105_right_held_by relationships

3. Documentation:
   - Added P70_documents for file relationships
   - Consider E31_Document for documentation aspects

4. Multilingual Support:
   - Added proper language mappings using E56_Language
   - P72_has_language relationships for all language-specific content

5. Identifiers:
   - Consistent use of E42_Identifier for all ID fields
   - Added P1_is_identified_by relationships

6. Attribution:
   - Added P14_carried_out_by for all user-related fields
   - Consider E21_Person for user mappings

7. Classification:
   - Enhanced type system using E55_Type
   - Added hierarchical relationships using P127_has_broader_term
"""
