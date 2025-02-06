from django.db import models
from django.conf import settings
from django.utils.timezone import now
from django.db import models
from arkumu.metadata.models.base import UserTrackedModel

class Akteur(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    name_de = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    aufloesungort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)
    geburtsort = models.ForeignKey('Ort', models.DO_NOTHING, related_name='akteur_geburtsort_set', blank=True, null=True)
    sterbeort = models.ForeignKey('Ort', models.DO_NOTHING, related_name='akteur_sterbeort_set', blank=True, null=True)
    gruendungsort = models.ForeignKey('Ort', models.DO_NOTHING, related_name='akteur_gruendungsort_set', blank=True, null=True)
    orcid = models.CharField(max_length=255, blank=True, null=True)
    normdaten = models.TextField(blank=True, null=True)
    webseiten = models.TextField(blank=True, null=True)
    kurzbiografie_de = models.TextField(blank=True, null=True)
    kommentar_de = models.TextField(blank=True, null=True)
    kurzbiografie_en = models.TextField(blank=True, null=True)
    kommentar_en = models.TextField(blank=True, null=True)
    geschlecht = models.BigIntegerField(blank=True, null=True)
    kontakt_emails = models.CharField(max_length=255, blank=True, null=True)
    kontakt_telefon = models.CharField(max_length=255, blank=True, null=True)
    kontakt_postanschrift = models.CharField(max_length=255, blank=True, null=True)
    nicht_oeffentliche_namen = models.CharField(max_length=255, blank=True, null=True)
    nicht_oeffentliche_namen_erlaeuterung = models.CharField(max_length=255, blank=True, null=True)
    alternativer_namen = models.TextField(blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    lccnid = models.CharField(max_length=255, blank=True, null=True)
    viafid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    spaetster_wirkungsbegin = models.CharField(max_length=255, blank=True, null=True)
    spaetestes_geburtsdatum = models.CharField(max_length=255, blank=True, null=True)
    fruehstes_sterbedatum = models.CharField(max_length=255, blank=True, null=True)
    fruehstes_wirkungsende = models.CharField(max_length=255, blank=True, null=True)
    fruehstes_geburtsdatum = models.CharField(max_length=255, blank=True, null=True)
    spaetestes_sterbedatum = models.CharField(max_length=255, blank=True, null=True)
    fruehster_wirkungsbegin = models.CharField(max_length=255, blank=True, null=True)
    spaetstes_wirkungsende = models.CharField(max_length=255, blank=True, null=True)
    vorangestellter_titel = models.CharField(max_length=255, blank=True, null=True)
    nachgestellter_titel = models.CharField(max_length=255, blank=True, null=True)
    datensatz_id_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    einlieferer = models.ForeignKey('Organisationseinheit', models.DO_NOTHING, blank=True, null=True)
    date_created_einlieferer = models.DateTimeField(blank=True, null=True)
    date_modified_einlieferer = models.DateTimeField(blank=True, null=True)
    kommentar_intern = models.TextField(blank=True, null=True)
    andere_normdaten = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'akteur'


class AkteurMitwirkungsRolle(UserTrackedModel):
    akteur_berufe_taetigkeiten_id = models.BigIntegerField()
    mitwirkungs_rolle_id = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'akteur_mitwirkungs_rolle'


class AkteurOrt(UserTrackedModel):
    akteur_wirkungsorte = models.ForeignKey(Akteur, models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'akteur_ort'


class AkteurRelation(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    akteur1 = models.ForeignKey(Akteur, models.DO_NOTHING)
    akteur2 = models.ForeignKey(Akteur, models.DO_NOTHING, related_name='akteurrelation_akteur2_set')
    akteur_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'akteur_relation'


class AkteurRolle(UserTrackedModel):
    akteur_berufe_taetigkeiten = models.ForeignKey(Akteur, models.DO_NOTHING)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'akteur_rolle'


class AuditLog(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    persisted_object_id = models.CharField(max_length=255, blank=True, null=True)
    property_name = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    event_name = models.CharField(max_length=255, blank=True, null=True)
    actor = models.CharField(max_length=255, blank=True, null=True)
    new_value = models.CharField(max_length=255, blank=True, null=True)
    class_name = models.CharField(max_length=255, blank=True, null=True)
    old_value = models.CharField(max_length=255, blank=True, null=True)
    persisted_object_version = models.BigIntegerField(blank=True, null=True)
    uri = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'audit_log'


class Base64DecodedMultipartFile(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)

    class Meta:
        db_table = 'base64decoded_multipart_file'


class BestehenderLizenzvertrag(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    lizenz_status = models.CharField(max_length=255, blank=True, null=True)
    pdf = models.ForeignKey('FileUpload', models.DO_NOTHING, blank=True, null=True)
    vertrags_text_de = models.CharField(max_length=255, blank=True, null=True)
    hochschule = models.ForeignKey('Hochschule', models.DO_NOTHING)
    bezeichnung_de = models.CharField(max_length=255)
    bezeichnung_en = models.CharField(max_length=255, blank=True, null=True)
    anzeige_status = models.CharField(max_length=255, blank=True, null=True)
    vertrags_text_en = models.CharField(max_length=255, blank=True, null=True)
    uri = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'bestehender_lizenzvertrag'


class DataImporter(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    source_table = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    data_destination_id = models.CharField(max_length=255, blank=True, null=True)
    data_source_id = models.CharField(max_length=255)
    destination_table = models.CharField(max_length=255)
    last_updated = models.DateTimeField()
    contributor = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'data_importer'


class DigitalesObjekt(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    file = models.ForeignKey('FileUpload', models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    lizenzstatus = models.ForeignKey('DigitalesObjektLizenz', models.DO_NOTHING)
    derivat_kopie_nummer = models.CharField(max_length=255, blank=True, null=True)
    dateipaket = models.BooleanField(blank=True, null=True)
    medientyp = models.BigIntegerField()
    erhaltungstyp = models.BigIntegerField(blank=True, null=True)
    entstehungstyp = models.BigIntegerField()
    created_by = models.CharField(max_length=255)
    beschreibende_metadaten_untertitelsprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    beschreibende_metadaten_teil_einer_serie = models.BooleanField(blank=True, null=True)
    beschreibende_metadaten_date_updated_einlieferer = models.DateTimeField(blank=True, null=True)
    beschreibende_metadaten_last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_tonmischfassung = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_systemvorraussetzungen = models.TextField(blank=True, null=True)
    beschreibende_metadaten_id_beim_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_sprache = models.ForeignKey('Sprache', models.DO_NOTHING, related_name='digitalesobjekt_beschreibende_metadaten_sprache_set', blank=True, null=True)
    beschreibende_metadaten_bildbeschreibung_de = models.TextField(blank=True, null=True)
    beschreibende_metadaten_inhalt_de = models.TextField(blank=True, null=True)
    beschreibende_metadaten_inhalt_en = models.TextField(blank=True, null=True)
    beschreibende_metadaten_kommentar_de = models.TextField(blank=True, null=True)
    beschreibende_metadaten_eigenschaften_de = models.TextField(blank=True, null=True)
    beschreibende_metadaten_eq = models.TextField(blank=True, null=True)
    beschreibende_metadaten_kommentar_intern = models.TextField(blank=True, null=True)
    beschreibende_metadaten_eigenschaften_en = models.TextField(blank=True, null=True)
    beschreibende_metadaten_date_created_einlieferer = models.DateTimeField(blank=True, null=True)
    beschreibende_metadaten_schleife = models.BooleanField(blank=True, null=True)
    beschreibende_metadaten_projektkompilation = models.BigIntegerField(blank=True, null=True)
    beschreibende_metadaten_sprachfassung = models.ForeignKey('Sprache', models.DO_NOTHING, related_name='digitalesobjekt_beschreibende_metadaten_sprachfassung_set', blank=True, null=True)
    beschreibende_metadaten_kommentar_en = models.TextField(blank=True, null=True)
    beschreibende_metadaten_tonformat = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_einlieferndehs = models.ForeignKey('Hochschule', models.DO_NOTHING, blank=True, null=True)
    beschreibende_metadaten_bildbeschreibung_en = models.TextField(blank=True, null=True)
    technische_metadaten_droidpuid = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_exif_toolxml = models.TextField(blank=True, null=True)
    technische_metadaten_jhovedateistatus = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_jhovexml = models.TextField(blank=True, null=True)
    technische_metadaten_droidxml = models.TextField(blank=True, null=True)
    technische_metadaten_duration = models.BigIntegerField(blank=True, null=True)
    technische_metadaten_dateifamilie = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_dateityp_kurz = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_hash = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_media_infoxml = models.TextField(blank=True, null=True)
    is_encrypted = models.BooleanField()
    use_preview = models.BooleanField(blank=True, null=True)
    last_modified = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'digitales_objekt'


class DigitalesObjektLizenz(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    anzeige_text_de = models.CharField(max_length=255, blank=True, null=True)
    rechtestatment = models.CharField(max_length=255)
    lizenz_text_en = models.TextField(blank=True, null=True)
    lizenz_text_de = models.TextField(blank=True, null=True)
    bezeichnung_de = models.CharField(max_length=255)
    bezeichnung_en = models.CharField(max_length=255)
    uri = models.CharField(max_length=255, blank=True, null=True)
    anzeige_text_en = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'digitales_objekt_lizenz'


class DigitalesObjektSchlagwort(UserTrackedModel):
    digitales_objekt_objekttypen = models.ForeignKey(DigitalesObjekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'digitales_objekt_schlagwort'


class Eigenschaft(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    description_de = models.CharField(max_length=512)
    description_en = models.CharField(max_length=512)
    type = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'eigenschaft'


class EquipmentSoftware(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    hersteller = models.CharField(max_length=255, blank=True, null=True)
    equipmentart = models.ForeignKey('Equipmentart', models.DO_NOTHING)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'equipment_software'


class Equipmentart(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    aatid = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        db_table = 'equipmentart'


class Ereignis(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    normdatei = models.CharField(max_length=255, blank=True, null=True)
    stimmung_in_hertz = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    ende_estimated = models.BooleanField(blank=True, null=True)
    beginn = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    ende_date = models.DateTimeField(blank=True, null=True)
    auffuehrungstonart = models.CharField(max_length=255, blank=True, null=True)
    ereignis_typ = models.ForeignKey('EreignisTyp', models.DO_NOTHING)
    beginn_estimated = models.BooleanField(blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    beginn_date = models.DateTimeField(blank=True, null=True)
    ende = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    kommentar_de = models.TextField(blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    kommentar_intern = models.TextField(blank=True, null=True)
    kommentar_en = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ereignis'


class EreignisAkteur(UserTrackedModel):
    ereignis_akteure = models.ForeignKey(Ereignis, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_akteur'


class EreignisBeschreibung(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    beschreibung = models.TextField()
    wertigkeit = models.BigIntegerField()
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_beschreibung'


class EreignisDigitalesObjekt(UserTrackedModel):
    ereignis_digitale_objekte = models.ForeignKey(Ereignis, models.DO_NOTHING)
    digitales_objekt = models.ForeignKey(DigitalesObjekt, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_digitales_objekt'


class EreignisEigenschaftswert(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    eigenschaft = models.ForeignKey(Eigenschaft, models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    ereignis_eigenschaften_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'ereignis_eigenschaftswert'


class EreignisEquipmentSoftware(UserTrackedModel):
    ereignis_equipment_software = models.ForeignKey(Ereignis, models.DO_NOTHING)
    equipment_software = models.ForeignKey(EquipmentSoftware, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_equipment_software'


class EreignisInformationstraeger(UserTrackedModel):
    ereignis_informationstraeger = models.ForeignKey(Ereignis, models.DO_NOTHING)
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_informationstraeger'


class EreignisOrt(UserTrackedModel):
    ereignis_orte = models.ForeignKey(Ereignis, models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_ort'


class EreignisPhysischesObjekt(UserTrackedModel):
    physisches_objekt = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING, blank=True, null=True)
    ereignis_physische_objekte_id = models.BigIntegerField()

    class Meta:
        db_table = 'ereignis_physisches_objekt'


class EreignisRelation(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    ereignis2 = models.ForeignKey(Ereignis, models.DO_NOTHING)
    ereignis1 = models.ForeignKey(Ereignis, models.DO_NOTHING, related_name='ereignisrelation_ereignis1_set')
    ereignis_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'ereignis_relation'


class EreignisRolle(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    urheber = models.BooleanField(blank=True, null=True)
    leistungsschutzrechte = models.BooleanField(blank=True, null=True)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING)
    ereignis_rollen_idx = models.BigIntegerField(blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    ungesicherte_zuschreibung = models.BooleanField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_rolle'


class EreignisTyp(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    aatid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    lido_terminologie_link = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)

    class Meta:
        db_table = 'ereignis_typ'


class EreignisTypSynonyme(UserTrackedModel):
    ereignis_typ_id = models.BigIntegerField()
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_typ_synonyme'


class FileUpload(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    file_uri = models.CharField(max_length=255)
    original_file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    date_created = models.DateTimeField()
    content_type = models.CharField(max_length=255)
    upload_id = models.CharField(unique=True, max_length=255)
    associated_property = models.CharField(max_length=255)
    associated_entity = models.CharField(max_length=255)

    class Meta:
        db_table = 'file_upload'


class Hochschule(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    signatur = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'hochschule'


class Informationstraeger(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    kompilationstitel = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    measurements = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    kompilations_reihennummer = models.CharField(max_length=255, blank=True, null=True)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    informationstraegertyp = models.ForeignKey('Informationstraegertyp', models.DO_NOTHING)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.CharField(max_length=255, blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    interner_kommentar = models.CharField(max_length=255, blank=True, null=True)
    kompilation = models.BigIntegerField(blank=True, null=True)
    aatid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    pbcore_link = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger'


class InformationstraegerAkteur(UserTrackedModel):
    informationstraeger_besitzer = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)
    informationstraeger_eigentuemer = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegerakteur_informationstraeger_eigentuemer_set')

    class Meta:
        db_table = 'informationstraeger_akteur'


class InformationstraegerBesitzer(UserTrackedModel):
    informationstraeger_besitzer = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_besitzer'


class InformationstraegerEigenschaftswert(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    eigenschaft = models.ForeignKey(Eigenschaft, models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    informationstraeger = models.ForeignKey(Informationstraeger, models.DO_NOTHING)

    class Meta:
        db_table = 'informationstraeger_eigenschaftswert'


class InformationstraegerEigentuemer(UserTrackedModel):
    informationstraeger_eigentuemer = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_eigentuemer'


class InformationstraegerOriginalsprachen(UserTrackedModel):
    informationstraeger_originalsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_originalsprachen'


class InformationstraegerSchlagwort(UserTrackedModel):
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_materialschlagwort = models.ForeignKey(Informationstraeger, models.DO_NOTHING)

    class Meta:
        db_table = 'informationstraeger_schlagwort'


class InformationstraegerSprache(UserTrackedModel):
    informationstraeger_untertitelsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_originalsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_originalsprachen_set')
    informationstraeger_sprachfassungen = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_sprachfassungen_set')

    class Meta:
        db_table = 'informationstraeger_sprache'


class InformationstraegerSprachfassungen(UserTrackedModel):
    informationstraeger_sprachfassungen = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_sprachfassungen'


class InformationstraegerUntertitelsprachen(UserTrackedModel):
    informationstraeger_untertitelsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_untertitelsprachen'


class Informationstraegereigenschaft(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        db_table = 'informationstraegereigenschaft'


class Informationstraegertyp(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    aatid = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    pbcore_link = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraegertyp'


class InformationstraegertypSynonyme(UserTrackedModel):
    informationstraegertyp = models.ForeignKey(Informationstraegertyp, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraegertyp_synonyme'


class Inhaltswarnung(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    text_de = models.CharField(max_length=255, blank=True, null=True)
    text_en = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'inhaltswarnung'


class Materialschlagwort(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(unique=True, max_length=255)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255)
    label_de = models.CharField(max_length=255)
    description_en = models.TextField()
    gndid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort'


class MaterialschlagwortSynonymDe(UserTrackedModel):
    materialschlagwort = models.ForeignKey(Materialschlagwort, models.DO_NOTHING)
    synonym_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort_synonym_de'


class MaterialschlagwortSynonymEn(UserTrackedModel):
    materialschlagwort = models.ForeignKey(Materialschlagwort, models.DO_NOTHING)
    synonym_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort_synonym_en'


class Nummernart(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        db_table = 'nummernart'


class Organisationseinheit(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.TextField(blank=True, null=True)
    beschreibung_de = models.TextField(blank=True, null=True)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    hochschule = models.ForeignKey(Hochschule, models.DO_NOTHING)

    class Meta:
        db_table = 'organisationseinheit'


class Ort(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    wikidata_item = models.CharField(max_length=255)
    kategorie = models.BigIntegerField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    viafid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.CharField(max_length=255)
    longitude = models.CharField(max_length=255)

    class Meta:
        db_table = 'ort'


class PhysischesObjekt(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey(Ort, models.DO_NOTHING, blank=True, null=True)
    beschreibung_de = models.TextField(blank=True, null=True)
    beschreibung_en = models.TextField(blank=True, null=True)
    kommentar_de = models.TextField(blank=True, null=True)
    kommentar_en = models.TextField(blank=True, null=True)
    kommentar_intern = models.TextField(blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    measurements = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.TextField(blank=True, null=True)
    persistenter_identifikator = models.CharField(max_length=255, blank=True, null=True)
    kommentar_technik_de = models.TextField(blank=True, null=True)
    kommentar_technik_en = models.TextField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()

    class Meta:
        db_table = 'physisches_objekt'


class PhysischesObjektAkteur(UserTrackedModel):
    physisches_objekt_besitzer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)
    physisches_objekt_eigentuemer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING, related_name='physischesobjektakteur_physisches_objekt_eigentuemer_set')

    class Meta:
        db_table = 'physisches_objekt_akteur'


class PhysischesObjektBesitzer(UserTrackedModel):
    physisches_objekt_besitzer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_besitzer'


class PhysischesObjektEigentuemer(UserTrackedModel):
    physisches_objekt_eigentuemer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_eigentuemer'


class PhysischesObjektMaterialschlagworte(UserTrackedModel):
    physisches_objekt_materialschlagworte = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_materialschlagworte'


class PhysischesObjektProduktId(UserTrackedModel):
    physisches_objekt_produkt_id = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    produkt_id = models.ForeignKey('ProduktId', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_produkt_id'


class PhysischesObjektSchlagworte(UserTrackedModel):
    physisches_objekt_schlagworte = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_schlagworte'


class PhysischesObjektTechnikschlagworte(UserTrackedModel):
    physisches_objekt_technikschlagworte = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_technikschlagworte'


class ProduktId(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    nummernart = models.ForeignKey(Nummernart, models.DO_NOTHING)
    last_updated = models.DateTimeField()
    wert = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    informationstraeger = models.ForeignKey(Informationstraeger, models.DO_NOTHING)

    class Meta:
        db_table = 'produkt_id'


class Projekt(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    normdatei = models.TextField(blank=True, null=True)
    dateiabfrage_dokument = models.ForeignKey(FileUpload, models.DO_NOTHING, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    bestehender_lizenzvertrag = models.ForeignKey(BestehenderLizenzvertrag, models.DO_NOTHING, blank=True, null=True)
    date_created = models.DateTimeField()
    signatur = models.CharField(max_length=255, blank=True, null=True)
    rechtsstatus = models.BigIntegerField()
    letzte_modifikation = models.DateTimeField(blank=True, null=True)
    kommentar_de = models.TextField(blank=True, null=True)
    art_lizenzvertrag = models.BigIntegerField(blank=True, null=True)
    neuer_lizenzvertrag = models.ForeignKey(FileUpload, models.DO_NOTHING, related_name='projekt_neuer_lizenzvertrag_set', blank=True, null=True)
    kommentar_en = models.TextField(blank=True, null=True)
    tonart = models.CharField(max_length=255, blank=True, null=True)
    sonderregelung = models.BigIntegerField(blank=True, null=True)
    bevorzugter_titel = models.ForeignKey(
        'Titel', 
        on_delete=models.DO_NOTHING,
        related_name='preferred_for_projects',
        blank=True, 
        null=True
    )
    dokumentation_lizenzvertrag = models.ForeignKey(FileUpload, models.DO_NOTHING, related_name='projekt_dokumentation_lizenzvertrag_set', blank=True, null=True)
    externe_projekt_webseite = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField()
    signatur_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    hochschule = models.ForeignKey(Hochschule, models.DO_NOTHING)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    status = models.BigIntegerField()
    verzeichnisnummern = models.CharField(max_length=255, blank=True, null=True)
    dauer = models.CharField(max_length=255, blank=True, null=True)
    kommentar_intern = models.TextField(blank=True, null=True)
    erstellungs_datum_einlieferer = models.DateTimeField(blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt'


class ProjektAngegebeneNutzungsrechte(UserTrackedModel):
    projekt_id = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_angegebene_nutzungsrechte'


class ProjektArt(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)

    class Meta:
        db_table = 'projekt_art'


class ProjektBeschreibung(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    rang = models.BigIntegerField()
    beschreibung = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt_beschreibung'


class ProjektEigenschaftswert(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)
    eigenschaft = models.ForeignKey(Eigenschaft, models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    projekt_eigenschaften_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_eigenschaftswert'


class ProjektEreignis(UserTrackedModel):
    projekt_ereignisse = models.ForeignKey(Projekt, models.DO_NOTHING)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_ereignis'


class ProjektFileUpload(UserTrackedModel):
    projekt_weitere_rechtsdokumente_id = models.BigIntegerField(blank=True, null=True)
    file_upload = models.ForeignKey(FileUpload, models.DO_NOTHING, blank=True, null=True)
    weitere_rechtsdokumente_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_file_upload'


class ProjektInhaltswarnung(UserTrackedModel):
    projekt_id = models.BigIntegerField()
    inhaltswarnung = models.ForeignKey(Inhaltswarnung, models.DO_NOTHING, blank=True, null=True)
    inhaltswarnungen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_inhaltswarnung'


class ProjektKategorie(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    aatid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt_kategorie'


class ProjektKategorieSynonyme(UserTrackedModel):
    projekt_kategorie = models.ForeignKey(ProjektKategorie, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt_kategorie_synonyme'


class ProjektOrganisationseinheit(UserTrackedModel):
    projekt_organisationseinheit = models.ForeignKey(Projekt, models.DO_NOTHING)
    organisationseinheit = models.ForeignKey(Organisationseinheit, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_organisationseinheit'


class ProjektProjektArt(UserTrackedModel):
    projekt_projekt_art = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt_art = models.ForeignKey(ProjektArt, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_projekt_art'


class ProjektProjektKategorie(UserTrackedModel):
    kategorii = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt_kategorie = models.ForeignKey(ProjektKategorie, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_projekt_kategorie'


class ProjektRelation(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    projekt2 = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt1 = models.ForeignKey(Projekt, models.DO_NOTHING, related_name='projektrelation_projekt1_set')
    projekt_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_relation'


class ProjektSchlagworte(UserTrackedModel):
    projekt_schlagworte = models.ForeignKey(Projekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_schlagworte'


class RegistrationCode(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    username = models.CharField(max_length=255)
    token = models.CharField(max_length=255)

    class Meta:
        db_table = 'registration_code'


class Role(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    authority = models.CharField(unique=True, max_length=255)

    class Meta:
        db_table = 'role'


class Rolle(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    gndidg = models.CharField(max_length=255, blank=True, null=True)
    aatid = models.CharField(max_length=255, blank=True, null=True)
    gndidm = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    gndidw = models.CharField(max_length=255, blank=True, null=True)
    preselect_leistungsschutzrechte = models.BooleanField()
    preselect_urheber = models.BooleanField()

    class Meta:
        db_table = 'rolle'


class RolleRelation(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING)

    class Meta:
        db_table = 'rolle_relation'


class RolleRelationRolle(UserTrackedModel):
    rolle_relation_rollen = models.ForeignKey(RolleRelation, models.DO_NOTHING)
    rolle = models.ForeignKey(Rolle, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'rolle_relation_rolle'


class RolleSynonyme(UserTrackedModel):
    rolle = models.ForeignKey(Rolle, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'rolle_synonyme'


class Sammlung(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.TextField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    sammlungs_art = models.CharField(max_length=255)
    bezeichnung_de = models.CharField(max_length=255)
    bezeichnung_en = models.CharField(max_length=255)
    beschreibung_de = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'sammlung'


class SammlungVerknuepfteDigitaleObjekte(UserTrackedModel):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, digitales_objekt_id) found, that is not supported. The first column is selected.
    digitales_objekt = models.ForeignKey(DigitalesObjekt, models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_digitale_objekte'
        unique_together = (('sammlung', 'digitales_objekt'),)


class SammlungVerknuepfteEreignisse(UserTrackedModel):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, ereignis_id) found, that is not supported. The first column is selected.
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_ereignisse'
        unique_together = (('sammlung', 'ereignis'),)


class SammlungVerknuepfteInformationstraeger(UserTrackedModel):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, informationstraeger_id) found, that is not supported. The first column is selected.
    informationstraeger = models.ForeignKey(Informationstraeger, models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_informationstraeger'
        unique_together = (('sammlung', 'informationstraeger'),)


class SammlungVerknuepftePhysischeObjekte(UserTrackedModel):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, physisches_objekt_id) found, that is not supported. The first column is selected.
    physisches_objekt = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_physische_objekte'
        unique_together = (('sammlung', 'physisches_objekt'),)


class SammlungVerknuepfteProjekte(UserTrackedModel):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, projekt_id) found, that is not supported. The first column is selected.
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_projekte'
        unique_together = (('sammlung', 'projekt'),)


class SammlungVerknuepftesEquipment(UserTrackedModel):
    sammlung = models.ForeignKey(Sammlung, models.DO_NOTHING)
    equipment_software = models.ForeignKey(EquipmentSoftware, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'sammlung_verknuepftes_equipment'


class Schlagwort(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(unique=True, max_length=255)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255, blank=True, null=True)
    label_de = models.CharField(max_length=255, blank=True, null=True)
    description_en = models.TextField()
    gnd_item = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort'


class SchlagwortSynonymeDe(UserTrackedModel):
    schlagwort = models.ForeignKey(Schlagwort, models.DO_NOTHING)
    synonyme_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort_synonyme_de'


class SchlagwortSynonymeEn(UserTrackedModel):
    schlagwort = models.ForeignKey(Schlagwort, models.DO_NOTHING)
    synonyme_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort_synonyme_en'


class Sprache(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    iso_639_2_b_code = models.CharField(max_length=255)
    iso_639_1_code = models.CharField(max_length=255)
    iso_639_2_t_code = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'sprache'


class Titel(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    sprache_titel = models.ForeignKey(Sprache, models.DO_NOTHING)
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)
    untertitel = models.CharField(max_length=255, blank=True, null=True)
    titel = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    sprache_untertitel = models.ForeignKey(Sprache, models.DO_NOTHING, related_name='titel_sprache_untertitel_set', blank=True, null=True)
    rang = models.BigIntegerField()

    class Meta:
        db_table = 'titel'


class Tooltip(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    tt_text_en = models.CharField(max_length=1024, blank=True, null=True)
    tt_text_de = models.CharField(max_length=1024, blank=True, null=True)
    view = models.CharField(max_length=255)
    field = models.CharField(max_length=255)

    class Meta:
        db_table = 'tooltip'
        unique_together = (('view', 'field'),)


class User(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    password_expired = models.BooleanField()
    last_updated = models.DateTimeField()
    account_expired = models.BooleanField()
    username = models.CharField(unique=True, max_length=255)
    account_locked = models.BooleanField()
    password = models.CharField(max_length=255)
    enabled = models.BooleanField()
    email = models.CharField(max_length=255)
    last_login = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'user'


class UserDetail(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    anrede = models.CharField(max_length=255)
    date_created = models.DateTimeField()
    vorname = models.CharField(max_length=255)
    newsletter = models.BooleanField(blank=True, null=True)
    ort = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    nachname = models.CharField(max_length=255)
    user = models.ForeignKey(User, models.DO_NOTHING)
    avatar = models.ForeignKey(FileUpload, models.DO_NOTHING, blank=True, null=True)
    hochschule = models.ForeignKey(Hochschule, models.DO_NOTHING, blank=True, null=True)
    max_rows = models.BigIntegerField(blank=True, null=True)
    color_mode = models.CharField(max_length=8, blank=True, null=True)
    email = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'user_detail'


class UserRole(UserTrackedModel):
    user = models.OneToOneField(User, models.DO_NOTHING, primary_key=True)  # The composite primary key (user_id, role_id) found, that is not supported. The first column is selected.
    role = models.ForeignKey(Role, models.DO_NOTHING)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()

    class Meta:
        db_table = 'user_role'
        unique_together = (('user', 'role'),)


class Zeitpunkt(UserTrackedModel):
    id = models.BigAutoField(primary_key=True)
    monat = models.BigIntegerField(blank=True, null=True)
    jahr = models.BigIntegerField()
    tag = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'zeitpunkt'
