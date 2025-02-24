"""
CIDOC-CRM Mappings for Actor Models

Akteur (Actor) Core Mapping:
- Maps to E39_Actor (superclass that encompasses both people and groups)
- Can be mapped more specifically to:
  - E21_Person (for individual human actors)
  - E74_Group (for organizational actors)

Core Properties:
- Names (name_de, name_en):
  - Map to E41_Appellation
  - Use P72_has_language to indicate language
- Places:
  - geburtsort -> E53_Place linked via E67_Birth
  - sterbeort -> E53_Place linked via E69_Death
  - gruendungsort -> E53_Place linked via E66_Formation
  - aufloesungort -> E53_Place linked via E68_Dissolution
- Identifiers:
  - orcid, gndid, lccnid, viafid, wikidataid -> E42_Identifier
  - Use P2_has_type to distinguish identifier types

Privacy and Restricted Data:
- nicht_oeffentliche_namen (non-public names):
  - Maps to E41_Appellation
  - Use E13_Attribute_Assignment with P67_refers_to
  - Add E55_Type for "private/restricted access"
- nicht_oeffentliche_namen_erlaeuterung:
  - Maps to E62_String as P3_has_note on E13_Attribute_Assignment

Contact Information:
- kontakt_emails, kontakt_telefon, kontakt_postanschrift:
  - Map to E51_Contact_Point
  - Use P2_has_type to distinguish type
- webseiten:
  - Map to E51_Contact_Point with P2_has_type "website"

Temporal Information:
- Birth/Death dates (fruehstes_geburtsdatum, spaetestes_geburtsdatum, etc.):
  - Map to E52_Time-Span as part of E67_Birth and E69_Death
- Activity periods (fruehster_wirkungsbegin, spaetster_wirkungsbegin, etc.):
  - Map to E52_Time-Span as part of E7_Activity
  - Use P82a_begin_of_the_begin and P82b_end_of_the_begin
  - Use P82a_begin_of_the_end and P82b_end_of_the_end

Titles and Alternative Names:
- vorangestellter_titel/nachgestellter_titel:
  - Map to E41_Appellation
  - Use P2_has_type for "pre-nominal" or "post-nominal"
- alternativer_namen:
  - Map to E41_Appellation
  - Use P139_has_alternative_form

Administrative and Management:
- datensatz_id_einlieferer:
  - Maps to E42_Identifier with P2_has_type "submitter reference"
- einlieferer:
  - Maps to E39_Actor (submitting organization)
- date_created_einlieferer/date_modified_einlieferer:
  - Map to E52_Time-Span for creation/modification events

Documentation and Notes:
- kurzbiografie_de/kurzbiografie_en:
  - Map to E31_Document
  - Use P72_has_language
- kommentar_intern:
  - Map to E62_String as P3_has_note
  - Add E55_Type "internal use only"
- normdaten/andere_normdaten:
  - Map to E42_Identifier
  - Use P2_has_type for authority system type

Related Models Mapping:
AkteurRelation:
- Maps to E7_Activity with participating actors
- Use P107_has_current_or_former_member for groups
- P152_has_parent for hierarchical relations
- P98_brought_into_life/P100_was_death_of for lifecycle events

Rolle:
- Maps to E55_Type for roles/occupations
- Use E28_Conceptual_Object for complex definitions
- P127_has_broader_term for hierarchy

AkteurRolle:
- Use P14_carried_out_by with role qualifier
- P2_has_type for role types

RolleRelation:
- Maps to E5_Event or E7_Activity
- P14_carried_out_by for actor links
- P2_has_type for role specification

Additional CIDOC-CRM Mappings for Missing Fields:

Administrative Fields:
- date_created, last_updated:
  - Map to E52_Time-Span
  - Link via P4_has_time-span to E65_Creation_Event
  - Use P82a_begin_of_the_begin and P82b_end_of_the_begin

- created_by, last_updated_by:
  - Map to E39_Actor
  - Link via P14_carried_out_by to E65_Creation_Event

Demographic Information:
- geschlecht (gender):
  - Map to E55_Type
  - Use P2_has_type "gender"
  - Link via P141_assigned to E13_Attribute_Assignment
"""
