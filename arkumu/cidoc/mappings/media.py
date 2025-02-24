"""
CIDOC CRM Mappings for Digital Object Models

DigitalesObjekt (Digital Object) Mappings:
- Maps to E36_Visual_Item (for visual media) or E73_Information_Object (for other digital content)
- id -> P48_has_preferred_identifier
- file -> P67_refers_to (links to FileUpload)
- last_updated_by -> P14_carried_out_by
- date_created -> P94_has_created (E65_Creation event)
- last_updated -> P31_has_modified (E11_Modification event)
- lizenzstatus -> P104_is_subject_to (links to license rights)
- medientyp -> P2_has_type
- erhaltungstyp -> P2_has_type (preservation type)
- entstehungstyp -> P2_has_type (creation type)
- beschreibende_metadaten_* fields -> P3_has_note for descriptive metadata
- technische_metadaten_* fields -> P43_has_dimension for technical specifications

DigitalesObjektLizenz (Digital Object License) Mappings:
- Maps to E30_Right
- id -> P48_has_preferred_identifier
- rechtestatment -> P3_has_note
- lizenz_text_* -> P3_has_note (language-specific)
- uri -> P67_refers_to (reference to external license)

FileUpload Mappings:
- Maps to E31_Document
- id -> P48_has_preferred_identifier
- file_uri -> P1_is_identified_by
- file_size -> P43_has_dimension
- content_type -> P2_has_type
- upload_id -> P48_has_preferred_identifier

DigitalesObjektSchlagwort (Digital Object Keywords) Mappings:
- Maps to E55_Type
- Represents P2_has_type relationship between DigitalesObjekt and keywords

Base64DecodedMultipartFile Mappings:
- Maps to E73_Information_Object
- Represents temporary digital content during upload process
"""