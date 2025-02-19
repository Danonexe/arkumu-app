# E53_Place: Represents geographical locations and positions in space
# Maps to physical locations and their hierarchical relationships

# Fields mapping for Ort:
# id -> E42_Identifier
# date_created -> P4_has_time-span (creation date)
# last_updated -> P4_has_time-span (last modification date)
# last_updated_by -> P14_carried_out_by (for modification)
# created_by -> P14_carried_out_by (for creation)
# wikidata_item -> P1_is_identified_by (Wikidata identifier)
# kategorie -> P2_has_type (classification of place type)
# name_en -> P1_is_identified_by (E41_Appellation in English)
# name_de -> P1_is_identified_by (E41_Appellation in German)
# parent -> P89_falls_within (hierarchical relationship between places)
# viafid -> P1_is_identified_by (VIAF identifier)
# gndid -> P1_is_identified_by (GND identifier)
# latitude -> P168_place_is_defined_by (spatial coordinates)
# longitude -> P168_place_is_defined_by (spatial coordinates)

# AkteurOrt represents:
# akteur_wirkungsorte -> P74_has_current_or_former_residence (linking to E39_Actor)
# ort -> P53_has_former_or_current_location (linking to E53_Place)

# E74_Group (Institution/Organization)
# Hochschule maps to E74_Group (specifically educational institution)
# Fields mapping:
# id -> E42_Identifier
# date_created -> P4_has_time-span (creation date)
# last_updated -> P4_has_time-span (last modification date)
# signatur -> P1_is_identified_by (institutional identifier/signature)
# name_en -> P1_is_identified_by (E41_Appellation in English)
# name_de -> P1_is_identified_by (E41_Appellation in German)
# gndid -> P1_is_identified_by (GND identifier)
# wikidataid -> P1_is_identified_by (Wikidata identifier)

# E74_Group (Organizational Unit)
# Organisationseinheit maps to E74_Group (department/unit within institution)
# Fields mapping:
# id -> E42_Identifier
# beschreibung_en -> P3_has_note (description in English)
# beschreibung_de -> P3_has_note (description in German)
# name_en -> P1_is_identified_by (E41_Appellation in English)
# name_de -> P1_is_identified_by (E41_Appellation in German)
# hochschule -> P107_has_current_or_former_member (relationship to parent institution)
