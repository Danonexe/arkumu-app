"""
CIDOC CRM Mappings for Collection Models

Sammlung (Collection):
- Maps to E78_Collection
- beschreibung_en (description_en) -> P3_has_note
- beschreibung_de (description_de) -> P3_has_note
- bezeichnung_en (name_en) -> P1_is_identified_by (E41_Appellation)
- bezeichnung_de (name_de) -> P1_is_identified_by (E41_Appellation)
- sammlungs_art (collection_type) -> P2_has_type (E55_Type)
- date_created -> P94i_was_created_by (E65_Creation) P4_has_time-span
- last_updated -> P31i_was_modified_by (E11_Modification) P4_has_time-span
- created_by -> P94i_was_created_by (E65_Creation) P14_carried_out_by (E21_Person)
- last_updated_by -> P31i_was_modified_by (E11_Modification) P14_carried_out_by (E21_Person)

SammlungVerknuepfteDigitaleObjekte (Collection-DigitalObject Links):
- Maps relationship between E78_Collection and E73_Information_Object
- sammlung -> P46_is_composed_of
- digitales_objekt -> E73_Information_Object

SammlungVerknuepfteEreignisse (Collection-Event Links):
- Maps relationship between E78_Collection and E5_Event
- sammlung -> P12i_was_present_at
- ereignis -> E5_Event

SammlungVerknuepfteInformationstraeger (Collection-InformationCarrier Links):
- Maps relationship between E78_Collection and E84_Information_Carrier
- sammlung -> P46_is_composed_of
- informationstraeger -> E84_Information_Carrier

SammlungVerknuepftePhysischeObjekte (Collection-PhysicalObject Links):
- Maps relationship between E78_Collection and E19_Physical_Object
- sammlung -> P46_is_composed_of
- physisches_objekt -> E19_Physical_Object

SammlungVerknuepfteProjekte (Collection-Project Links):
- Maps relationship between E78_Collection and E7_Activity
- sammlung -> P16i_was_used_for
- projekt -> E7_Activity

SammlungVerknuepftesEquipment (Collection-Equipment Links):
- Maps relationship between E78_Collection and E22_Human-Made_Object
- sammlung -> P46_is_composed_of
- equipment_software -> E22_Human-Made_Object
"""
