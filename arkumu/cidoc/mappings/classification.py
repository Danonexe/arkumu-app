"""
CIDOC-CRM Mappings for Classification Models

Schlagwort (Subject Heading/Keyword):
E55_Type
    Properties:
    - id → P48_has_preferred_identifier (E42_Identifier)
    - wikidata_item → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "Wikidata ID"
    - description_de → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "de")
    - description_en → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "en")
    - label_de → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "de")
    - label_en → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "en")
    - gnd_item → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "GND ID"
    Temporal Properties:
    - date_created → P94i_was_created_by (E65_Creation) → P4_has_time-span (E52_Time-Span)
    - last_updated → P93i_was_taken_out_of_existence_by (E64_End_of_Existence) → P4_has_time-span (E52_Time-Span)

SchlagwortSynonymeDe/SchlagwortSynonymeEn:
E41_Appellation
    Properties:
    - synonyme_de/en_string → P190_has_symbolic_content (literal)
    - schlagwort → P139i_is_alternative_form_of → E55_Type (Schlagwort)
    - P72_has_language → E56_Language ("de"/"en")

Sprache (Language):
E56_Language (subclass of E55_Type)
    Properties:
    - id → P48_has_preferred_identifier (E42_Identifier)
    - name_en → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "en")
    - name_de → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "de")
    - iso_639_1_code → P1_is_identified_by (E42_Identifier) + P2_has_type "ISO 639-1"
    - iso_639_2_b_code → P1_is_identified_by (E42_Identifier) + P2_has_type "ISO 639-2/B"
    - iso_639_2_t_code → P1_is_identified_by (E42_Identifier) + P2_has_type "ISO 639-2/T"
    Actor Properties:
    - created_by → P94i_was_created_by (E65_Creation) → P14_carried_out_by (E21_Person)
    - last_updated_by → P31i_was_modified_by (E11_Modification) → P14_carried_out_by (E21_Person)
    Temporal Properties:
    - date_created → P94i_was_created_by (E65_Creation) → P4_has_time-span (E52_Time-Span)
    - last_updated → P31i_was_modified_by (E11_Modification) → P4_has_time-span (E52_Time-Span)

Eigenschaft (Property/Characteristic):
E55_Type
    Properties:
    - id → P48_has_preferred_identifier (E42_Identifier)
    - name_en → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "en")
    - name_de → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "de")
    - description_de → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "de")
    - description_en → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "en")
    - wikidataid → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "Wikidata ID"
    - gndid → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "GND ID"
    - type → P2_has_type (E55_Type) [for hierarchical typing]

Inhaltswarnung (Content Warning):
E73_Information_Object
    Properties:
    - id → P48_has_preferred_identifier (E42_Identifier)
    - text_de → P190_has_symbolic_content (literal) + P72_has_language (E56_Language "de")
    - text_en → P190_has_symbolic_content (literal) + P72_has_language (E56_Language "en")
    Actor Properties:
    - created_by → P94i_was_created_by (E65_Creation) → P14_carried_out_by (E21_Person)
    - last_updated_by → P31i_was_modified_by (E11_Modification) → P14_carried_out_by (E21_Person)
    Temporal Properties:
    - date_created → P94i_was_created_by (E65_Creation) → P4_has_time-span (E52_Time-Span)
    - last_updated → P31i_was_modified_by (E11_Modification) → P4_has_time-span (E52_Time-Span)

Materialschlagwort (Material Keyword):
E57_Material (subclass of E55_Type)
    Properties:
    - id → P48_has_preferred_identifier (E42_Identifier)
    - wikidata_item → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "Wikidata ID"
    - description_de → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "de")
    - description_en → P67i_is_referred_to_by (E33_Linguistic_Object) + P72_has_language (E56_Language "en")
    - label_de → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "de")
    - label_en → P1_is_identified_by (E41_Appellation) + P72_has_language (E56_Language "en")
    - gndid → P67i_is_referred_to_by (E33_Linguistic_Object) + P2_has_type "GND ID"
    Temporal Properties:
    - date_created → P94i_was_created_by (E65_Creation) → P4_has_time-span (E52_Time-Span)
    - last_updated → P31i_was_modified_by (E11_Modification) → P4_has_time-span (E52_Time-Span)

MaterialschlagwortSynonymDe/MaterialschlagwortSynonymEn:
E41_Appellation
    Properties:
    - synonym_de/en_string → P190_has_symbolic_content (literal)
    - materialschlagwort → P139i_is_alternative_form_of → E57_Material (Materialschlagwort)
    - P72_has_language → E56_Language ("de"/"en")
"""
