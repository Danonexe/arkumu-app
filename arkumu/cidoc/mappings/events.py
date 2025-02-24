"""
CIDOC-CRM Mappings for Event-related Models
"""

# Ereignis (Event)
# Maps to: E5 Event
# An event represents activities or occurrences in the database
"""
Field mappings:
- id: Technical identifier
- normdatei: P1 is identified by (identifier)
- stimmung_in_hertz: P43 has dimension (maps frequency/pitch)
- date_created: Technical timestamp
- ende_estimated: Qualifier for P4 has time-span
- beginn: P4 has time-span (start)
- last_updated: Technical timestamp
- ende_date: P4 has time-span (end)
- auffuehrungstonart: P2 has type (musical key)
- ereignis_typ: P2 has type (links to event type)
- beginn_estimated: Qualifier for P4 has time-span
- name: P1 is identified by (name)
- beginn_date: P4 has time-span (start date)
- ende: P4 has time-span (end)
- kommentar_de/en: P3 has note
- wikidataid/gndid: P1 is identified by (external identifier)
"""

# EreignisTyp (Event Type)
# Maps to: E55 Type
"""
Field mappings:
- id: Technical identifier
- name_en/de: P1 is identified by (name)
- aatid/gndid/wikidataid: P1 is identified by (external identifier)
- lido_terminologie_link: P71 lists (links to controlled vocabulary)
"""

# EreignisRelation (Event Relation)
# Maps to: E13 Attribute Assignment
"""
Field mappings:
- art_der_relation: P2 has type (type of relation)
- ereignis1/ereignis2: P140 assigned attribute to (related events)
"""

# Zeitpunkt (Time Point)
# Maps to: E52 Time-Span
"""
Field mappings:
- jahr: P82 at some time within (year)
- monat: P82 at some time within (month)
- tag: P82 at some time within (day)
"""

# EreignisTypSynonyme (Event Type Synonyms)
# Maps to: E55 Type
"""
Field mappings:
- ereignis_typ_id: P2 has type
- synonyme_string: P1 is identified by (alternative name)
"""

# EreignisBeschreibung (Event Description)
# Maps to: E33 Linguistic Object
"""
Field mappings:
- ereignis: P67 refers to (event)
- sprache: P72 has language
- beschreibung: P190 has symbolic content
- wertigkeit: P2 has type (priority/significance)
"""

# EreignisPhysischesObjekt (Event Physical Object)
# Maps to: P12 occurred in the presence of
"""
Field mappings:
- physisches_objekt: P12 occurred in the presence of (physical object)
"""

# EreignisDigitalesObjekt (Event Digital Object)
# Maps to: P67 refers to
"""
Field mappings:
- digitales_objekt: P67 refers to (digital object)
"""

# EreignisInformationstraeger (Event Information Carrier)
# Maps to: P12 occurred in the presence of
"""
Field mappings:
- informationstraeger: P12 occurred in the presence of (information carrier)
"""

# EreignisRolle (Event Role)
# Maps to: E7 Activity
"""
Field mappings:
- ereignis: P9 consists of
- akteur: P14 carried out by
- rolle: P14.1 in the role of
- urheber: P14 carried out by (qualifier for creator)
- leistungsschutzrechte: P104 is subject to (rights)
- ungesicherte_zuschreibung: P140 assigned attribute to (attribution qualifier)
"""

# EreignisOrt (Event Place)
# Maps to: P7 took place at
"""
Field mappings:
- ort: P7 took place at (place)
"""

# EreignisEigenschaftswert (Event Property Value)
# Maps to: E13 Attribute Assignment
"""
Field mappings:
- eigenschaft: P140 assigned attribute to
- wert: P141 assigned (value)
"""

# EreignisEquipmentSoftware (Event Equipment/Software)
# Maps to: P12 occurred in the presence of
"""
Field mappings:
- equipment_software: P12 occurred in the presence of (equipment/software)
"""

# EreignisAkteur (Event Actor)
# Maps to: P11 had participant
"""
Field mappings:
- akteur: P11 had participant (actor)
"""
