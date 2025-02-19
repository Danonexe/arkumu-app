"""
CIDOC-CRM Mappings for Equipment Models

PhysischesObjekt (Physical Object)
- E22_Human-Made_Object
  - name_de/name_en → P1_is_identified_by (E41_Appellation)
  - externe_inventar_signaturnummern → P1_is_identified_by (E42_Identifier)
  - aufbewahrungsort → P55_has_current_location (E53_Place)
  - beschreibung_de/beschreibung_en → P3_has_note
  - erhaltungszustand_de/erhaltungszustand_en → P44_has_condition (E3_Condition_State)
  - measurements → P43_has_dimension (E54_Dimension)
  - provenienz → P24_transferred_title_of (E8_Acquisition)
  - persistenter_identifikator → P48_has_preferred_identifier (E42_Identifier)
  - kommentar_technik_de/en → P3_has_note

EquipmentSoftware
- E29_Design_or_Procedure
  - name_de/name_en → P1_is_identified_by (E41_Appellation)
  - beschreibung_de/en → P3_has_note
  - hersteller → P108_has_produced_by (E12_Production)
  - wikidataid → P1_is_identified_by (E42_Identifier)

Equipmentart
- E55_Type
  - name_de/name_en → P1_is_identified_by (E41_Appellation)
  - aatid/gndid/wikidataid → P1_is_identified_by (E42_Identifier)

Informationstraeger (Information Carrier)
- E84_Information_Carrier
  - name_de/name_en → P1_is_identified_by (E41_Appellation)
  - beschreibung_de/en → P3_has_note
  - measurements → P43_has_dimension (E54_Dimension)
  - aufbewahrungsort → P55_has_current_location (E53_Place)
  - erhaltungszustand_de/en → P44_has_condition (E3_Condition_State)
  - externe_inventar_signaturnummern → P1_is_identified_by (E42_Identifier)
  - provenienz → P24_transferred_title_of (E8_Acquisition)
  - aatid/gndid/wikidataid → P1_is_identified_by (E42_Identifier)

Informationstraegertyp
- E55_Type
  - name_de/name_en → P1_is_identified_by (E41_Appellation)
  - aatid/gndid/wikidataid → P1_is_identified_by (E42_Identifier)
  - parent → P127_has_broader_term (E55_Type)

Relationship Models:
PhysischesObjektProduktId
- P128_carries (E90_Symbolic_Object)

PhysischesObjektAkteur/Eigentuemer/Besitzer
- P52_has_current_owner (E39_Actor)
- P50_has_current_keeper (E39_Actor)

PhysischesObjektMaterialschlagworte
- P45_consists_of (E57_Material)

PhysischesObjektSchlagworte
- P2_has_type (E55_Type)

PhysischesObjektTechnikschlagworte
- P32_used_general_technique (E55_Type)

InformationstraegerEigenschaft
- E55_Type
  - name_de/name_en → P1_is_identified_by (E41_Appellation)

InformationstraegerSprache related models
- P72_has_language (E56_Language)

InformationstraegerEigenschaftswert
- P2_has_type (E55_Type)
"""
