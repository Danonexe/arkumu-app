# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AccountEmailaddress(models.Model):
    email = models.CharField(unique=True, max_length=254)
    verified = models.BooleanField()
    primary = models.BooleanField()
    user = models.ForeignKey('UsersUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'account_emailaddress'
        unique_together = (('user', 'email'), ('user', 'primary'),)


class AccountEmailconfirmation(models.Model):
    created = models.DateTimeField()
    sent = models.DateTimeField(blank=True, null=True)
    key = models.CharField(unique=True, max_length=64)
    email_address = models.ForeignKey(AccountEmailaddress, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'account_emailconfirmation'


class Akteur(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    webseiten = models.CharField(max_length=255, blank=True, null=True)
    kurzbiografie_de = models.CharField(max_length=255, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    kurzbiografie_en = models.CharField(max_length=255, blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    geschlecht = models.BigIntegerField(blank=True, null=True)
    kontakt_emails = models.CharField(max_length=255, blank=True, null=True)
    kontakt_telefon = models.CharField(max_length=255, blank=True, null=True)
    kontakt_postanschrift = models.CharField(max_length=255, blank=True, null=True)
    nicht_oeffentliche_namen = models.CharField(max_length=255, blank=True, null=True)
    nicht_oeffentliche_namen_erlaeuterung = models.CharField(max_length=255, blank=True, null=True)
    alternativer_namen = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    lnccid = models.CharField(max_length=255, blank=True, null=True)
    viafid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'akteur'


class AkteurNormdatenListe(models.Model):
    akteur_id = models.BigIntegerField()
    normdaten_liste_string = models.CharField(max_length=255, blank=True, null=True)
    normdaten_liste_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'akteur_normdaten_liste'


class AkteurOrt(models.Model):
    akteur_wirkungsorte = models.ForeignKey(Akteur, models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'akteur_ort'


class AkteurRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    akteur1 = models.ForeignKey(Akteur, models.DO_NOTHING)
    akteur2 = models.ForeignKey(Akteur, models.DO_NOTHING, related_name='akteurrelation_akteur2_set')
    akteur_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'akteur_relation'


class AkteurRolle(models.Model):
    akteur_berufe_taetigkeiten = models.ForeignKey(Akteur, models.DO_NOTHING)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'akteur_rolle'


class AuditLog(models.Model):
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
        managed = False
        db_table = 'audit_log'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthtokenToken(models.Model):
    key = models.CharField(primary_key=True, max_length=40)
    created = models.DateTimeField()
    user = models.OneToOneField('UsersUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'authtoken_token'


class Base64DecodedMultipartFile(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'base64decoded_multipart_file'


class BestehenderLizenzvertrag(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'bestehender_lizenzvertrag'


class DigitalesObjekt(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    file = models.ForeignKey('FileUpload', models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    lizenzstatus = models.ForeignKey('DigitalesObjektLizenz', models.DO_NOTHING)
    derivat_kopie_nummer = models.CharField(max_length=255, blank=True, null=True)
    objekttyp = models.ForeignKey('Objekttyp', models.DO_NOTHING, blank=True, null=True)
    dateipaket = models.BooleanField(blank=True, null=True)
    medientyp = models.BigIntegerField()
    erhaltungstyp = models.BigIntegerField()
    entstehungstyp = models.BigIntegerField()
    created_by = models.CharField(max_length=255)
    beschreibende_metadaten_untertitelsprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    beschreibende_metadaten_teil_einer_serie = models.BooleanField(blank=True, null=True)
    beschreibende_metadaten_date_updated_einlieferer = models.DateTimeField(blank=True, null=True)
    beschreibende_metadaten_tonmischfassung = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_systemvorraussetzungen = models.TextField(blank=True, null=True)
    beschreibende_metadaten_id_beim_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_sprache = models.ForeignKey('Sprache', models.DO_NOTHING, related_name='digitalesobjekt_beschreibende_metadaten_sprache_set', blank=True, null=True)
    beschreibende_metadaten_bildbeschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_inhalt_de = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_inhalt_en = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_eigenschaften_de = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_eq = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_kommentar_intern = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_eigenschaften_en = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_date_created_einlieferer = models.DateTimeField(blank=True, null=True)
    beschreibende_metadaten_schleife = models.BooleanField(blank=True, null=True)
    beschreibende_metadaten_projektkompilation = models.BigIntegerField(blank=True, null=True)
    beschreibende_metadaten_sprachfassung = models.ForeignKey('Sprache', models.DO_NOTHING, related_name='digitalesobjekt_beschreibende_metadaten_sprachfassung_set', blank=True, null=True)
    beschreibende_metadaten_kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_tonformat = models.CharField(max_length=255, blank=True, null=True)
    beschreibende_metadaten_einlieferndehs = models.ForeignKey('Hochschule', models.DO_NOTHING, blank=True, null=True)
    beschreibende_metadaten_bildbeschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_droidpuid = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_exif_toolxml = models.TextField(blank=True, null=True)
    technische_metadaten_jhovedateistatus = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_jhovexml = models.TextField(blank=True, null=True)
    technische_metadaten_droidpuidlink = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_droidxml = models.TextField(blank=True, null=True)
    technische_metadaten_duration = models.BigIntegerField(blank=True, null=True)
    technische_metadaten_dateifamilie = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_dateityp_kurz = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_hash = models.CharField(max_length=255, blank=True, null=True)
    technische_metadaten_media_infoxml = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'digitales_objekt'


class DigitalesObjektLizenz(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    rechtestatment = models.CharField(max_length=255)
    lizenz_text_en = models.CharField(max_length=255, blank=True, null=True)
    lizenz_text_de = models.CharField(max_length=255, blank=True, null=True)
    bezeichnung_de = models.CharField(max_length=255)
    bezeichnung_en = models.CharField(max_length=255)
    uri = models.CharField(max_length=255, blank=True, null=True)
    anzeige_text_de = models.CharField(max_length=255, blank=True, null=True)
    anzeige_text_en = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'digitales_objekt_lizenz'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey('UsersUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class DjangoSite(models.Model):
    domain = models.CharField(unique=True, max_length=100)
    name = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'django_site'


class EquipmentSoftware(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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

    class Meta:
        managed = False
        db_table = 'equipment_software'


class Equipmentart(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'equipmentart'


class Ereignis(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    von = models.ForeignKey('Zeitpunkt', models.DO_NOTHING, blank=True, null=True)
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING, blank=True, null=True)
    ereignis_typ = models.ForeignKey('EreignisTyp', models.DO_NOTHING)
    name = models.CharField(max_length=255, blank=True, null=True)
    bis = models.ForeignKey('Zeitpunkt', models.DO_NOTHING, related_name='ereignis_bis_set', blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    beginn = models.CharField(max_length=255)
    ende = models.CharField(max_length=255)
    ende_date = models.DateTimeField(blank=True, null=True)
    beginn_date = models.DateTimeField(blank=True, null=True)
    ende_estimated = models.BooleanField(blank=True, null=True)
    beginn_estimated = models.BooleanField(blank=True, null=True)
    normdatei = models.CharField(max_length=255, blank=True, null=True)
    stimmung_in_hertz = models.CharField(max_length=255, blank=True, null=True)
    auffuehrungstonart = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis'


class EreignisBeschreibung(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    beschreibung = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, null=True)
    wertigkeit = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'ereignis_beschreibung'
        unique_together = (('ereignis', 'wertigkeit'),)


class EreignisDigitalesObjekt(models.Model):
    ereignis_digitale_objekte = models.ForeignKey(Ereignis, models.DO_NOTHING)
    digitales_objekt = models.ForeignKey(DigitalesObjekt, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_digitales_objekt'


class EreignisInformationstraeger(models.Model):
    ereignis_informationstraeger = models.ForeignKey(Ereignis, models.DO_NOTHING)
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_informationstraeger'


class EreignisOrt(models.Model):
    ereignis_orte = models.ForeignKey(Ereignis, models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_ort'


class EreignisPhysischesObjekt(models.Model):
    ereignis_physische_objekte = models.ForeignKey(Ereignis, models.DO_NOTHING)
    physisches_objekt = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_physisches_objekt'


class EreignisRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField(blank=True, null=True)
    ereignis2 = models.ForeignKey(Ereignis, models.DO_NOTHING)
    ereignis1 = models.ForeignKey(Ereignis, models.DO_NOTHING, related_name='ereignisrelation_ereignis1_set')
    ereignis_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_relation'


class EreignisRolle(models.Model):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)
    ereignis_rollen_idx = models.BigIntegerField(blank=True, null=True)
    urheber = models.BooleanField(blank=True, null=True)
    leistungsschutzrechte = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_rolle'


class EreignisTyp(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'ereignis_typ'


class EreignisTypSynonyme(models.Model):
    ereignis_typ_id = models.BigIntegerField()
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ereignis_typ_synonyme'


class FileUpload(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    file_uri = models.CharField(max_length=255)
    original_file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    date_created = models.DateTimeField()
    content_type = models.CharField(max_length=255)
    upload_id = models.CharField(unique=True, max_length=255)
    associated_property = models.CharField(max_length=255)
    associated_entity = models.CharField(max_length=255)
    last_modified = models.DateTimeField(blank=True, null=True)
    class_field = models.CharField(db_column='class', max_length=255)  # Field renamed because it was a Python reserved word.

    class Meta:
        managed = False
        db_table = 'file_upload'


class Hochschule(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    signatur = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'hochschule'


class Informationstraeger(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    informationstraegertyp = models.ForeignKey('Informationstraegertyp', models.DO_NOTHING, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.CharField(max_length=255, blank=True, null=True)
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    interner_kommentar = models.CharField(max_length=255, blank=True, null=True)
    kompilationstitel = models.CharField(max_length=255, blank=True, null=True)
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    kompilations_reihennummer = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    kompilation = models.BooleanField(blank=True, null=True)
    originalsprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    measurements = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraeger'


class InformationstraegerAkteur(models.Model):
    informationstraeger_besitzer = models.ForeignKey(Informationstraeger, models.DO_NOTHING, blank=True, null=True)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING)
    informationstraeger_eigentuemer = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegerakteur_informationstraeger_eigentuemer_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraeger_akteur'


class InformationstraegerInformationstraegereigenschaft(models.Model):
    informationstraeger_informationstraeger_eigenschaften = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    informationstraegereigenschaft = models.ForeignKey('Informationstraegereigenschaft', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraeger_informationstraegereigenschaft'


class InformationstraegerSchlagwort(models.Model):
    informationstraeger_material = models.ForeignKey(Informationstraeger, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraeger_schlagwort'


class InformationstraegerSprache(models.Model):
    informationstraeger_untertitelsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING, blank=True, null=True)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_sprachfassungen = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_sprachfassungen_set', blank=True, null=True)
    informationstraeger_originalsprachen = models.ForeignKey(Informationstraeger, models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_originalsprachen_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraeger_sprache'


class Informationstraegereigenschaft(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'informationstraegereigenschaft'


class Informationstraegertyp(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'informationstraegertyp'


class InformationstraegertypSynonyme(models.Model):
    informationstraegertyp = models.ForeignKey(Informationstraegertyp, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informationstraegertyp_synonyme'


class Inhaltswarnung(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    vorgefertigte_inhaltswarnung = models.ForeignKey('VorgefertigteInhaltswarnung', models.DO_NOTHING, blank=True, null=True)
    text_de = models.CharField(max_length=255, blank=True, null=True)
    text_en = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'inhaltswarnung'


class Lizenz(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    rechtestatment = models.CharField(max_length=255)
    lizenz_text_en = models.CharField(max_length=255, blank=True, null=True)
    lizenz_text_de = models.CharField(max_length=255, blank=True, null=True)
    bezeichnung_de = models.CharField(max_length=255)
    bezeichnung_en = models.CharField(max_length=255, blank=True, null=True)
    uri = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'lizenz'


class Materialschlagwort(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(unique=True, max_length=255)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255)
    label_de = models.CharField(max_length=255)
    description_en = models.TextField()

    class Meta:
        managed = False
        db_table = 'materialschlagwort'


class MaterialschlagwortSynomymDe(models.Model):
    materialschlagwort = models.ForeignKey(Materialschlagwort, models.DO_NOTHING)
    synomym_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'materialschlagwort_synomym_de'


class MaterialschlagwortSynomymEn(models.Model):
    materialschlagwort = models.ForeignKey(Materialschlagwort, models.DO_NOTHING)
    synomym_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'materialschlagwort_synomym_en'


class MfaAuthenticator(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=20)
    data = models.JSONField()
    user = models.ForeignKey('UsersUser', models.DO_NOTHING)
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mfa_authenticator'
        unique_together = (('user', 'type'),)


class Nummernart(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'nummernart'


class Objekttyp(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255)
    name = models.CharField(unique=True, max_length=255)
    created_by = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'objekttyp'


class Organisationseinheit(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    beschreibung_en = models.TextField(blank=True, null=True)
    beschreibung_de = models.TextField(blank=True, null=True)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    hochschule = models.ForeignKey(Hochschule, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'organisationseinheit'


class Ort(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
    latitude = models.CharField(max_length=255, blank=True, null=True)
    longitude = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ort'


class PhysischesObjekt(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    kompilationstitel = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    besitzer = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey(Ort, models.DO_NOTHING, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    kompilations_reihennummer = models.CharField(max_length=255, blank=True, null=True)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    eigentuemer = models.ForeignKey(Akteur, models.DO_NOTHING, related_name='physischesobjekt_eigentuemer_set', blank=True, null=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.TextField(blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    kompilation = models.BooleanField(blank=True, null=True)
    measurements = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt'


class PhysischesObjektAkteur(models.Model):
    physisches_objekt_besitzer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING, blank=True, null=True)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING, blank=True, null=True)
    physisches_objekt_eigentuemer = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING, related_name='physischesobjektakteur_physisches_objekt_eigentuemer_set', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt_akteur'


class PhysischesObjektInformationstraegereigenschaft(models.Model):
    physisches_objekt_informationstraeger_eigenschaften = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    informationstraegereigenschaft = models.ForeignKey(Informationstraegereigenschaft, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt_informationstraegereigenschaft'


class PhysischesObjektMaterialschlagwort(models.Model):
    physisches_objekt_materialschlagwort = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    materialschlagwort = models.ForeignKey(Materialschlagwort, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt_materialschlagwort'


class PhysischesObjektProduktId(models.Model):
    physisches_objekt_produkt_id = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    produkt_id = models.ForeignKey('ProduktId', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt_produkt_id'


class PhysischesObjektSchlagwort(models.Model):
    physisches_objekt_klassifizierendes_schlagwort = models.ForeignKey(PhysischesObjekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'physisches_objekt_schlagwort'


class ProduktId(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    nummernart = models.ForeignKey(Nummernart, models.DO_NOTHING)
    last_updated = models.DateTimeField()
    wert = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    informationstraeger = models.ForeignKey(Informationstraeger, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'produkt_id'


class Projekt(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    bevorzugter_titel = models.ForeignKey('Titel', models.DO_NOTHING, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    signatur = models.CharField(max_length=255, blank=True, null=True)
    hochschule = models.ForeignKey(Hochschule, models.DO_NOTHING)
    kategorie = models.ForeignKey('ProjektKategorie', models.DO_NOTHING, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    status = models.BigIntegerField()
    verzeichnisnummern = models.CharField(max_length=255, blank=True, null=True)
    normdatei = models.CharField(max_length=255, blank=True, null=True)
    signatur_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    externe_projekt_webseite = models.CharField(max_length=255, blank=True, null=True)
    letzte_modifikation = models.DateTimeField(blank=True, null=True)
    tonart = models.CharField(max_length=255, blank=True, null=True)
    rechtsstatus = models.CharField(max_length=255)
    art_lizenzvertrag = models.BigIntegerField(blank=True, null=True)
    dateiabfrage_dokument = models.ForeignKey(FileUpload, models.DO_NOTHING, blank=True, null=True)
    weitere_rechtsdokumente = models.ForeignKey(FileUpload, models.DO_NOTHING, related_name='projekt_weitere_rechtsdokumente_set', blank=True, null=True)
    neuer_lizenzvertrag = models.ForeignKey(FileUpload, models.DO_NOTHING, related_name='projekt_neuer_lizenzvertrag_set', blank=True, null=True)
    sonderregelung = models.BigIntegerField(blank=True, null=True)
    dokumentation_lizenzvertrag = models.ForeignKey(FileUpload, models.DO_NOTHING, related_name='projekt_dokumentation_lizenzvertrag_set', blank=True, null=True)
    bestehender_lizenzvertrag = models.ForeignKey(BestehenderLizenzvertrag, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt'


class ProjektAngegebeneNutzungsrechte(models.Model):
    projekt_id = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_angegebene_nutzungsrechte'


class ProjektArt(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_link = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'projekt_art'


class ProjektBeschreibung(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    rang = models.BigIntegerField()
    beschreibung = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, null=True)
    projekt_beschreibungen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_beschreibung'


class ProjektEreignis(models.Model):
    projekt_ereignisse = models.ForeignKey(Projekt, models.DO_NOTHING)
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_ereignis'


class ProjektFileUpload(models.Model):
    projekt_weitere_rechtsdokumente_id = models.BigIntegerField(blank=True, null=True)
    file_upload = models.ForeignKey(FileUpload, models.DO_NOTHING, blank=True, null=True)
    weitere_rechtsdokumente_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_file_upload'


class ProjektKategorie(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'projekt_kategorie'


class ProjektKategorieSynonyme(models.Model):
    projekt_kategorie = models.ForeignKey(ProjektKategorie, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_kategorie_synonyme'


class ProjektOrganisationseinheit(models.Model):
    projekt_organisationseinheit = models.ForeignKey(Projekt, models.DO_NOTHING)
    organisationseinheit = models.ForeignKey(Organisationseinheit, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_organisationseinheit'


class ProjektProjektArt(models.Model):
    projekt_projekt_art = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt_art = models.ForeignKey(ProjektArt, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_projekt_art'


class ProjektProjektKategorie(models.Model):
    kategorii = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt_kategorie = models.ForeignKey(ProjektKategorie, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_projekt_kategorie'


class ProjektRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    projekt2 = models.ForeignKey(Projekt, models.DO_NOTHING)
    projekt1 = models.ForeignKey(Projekt, models.DO_NOTHING, related_name='projektrelation_projekt1_set')
    projekt_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_relation'


class ProjektSchlagwort(models.Model):
    projekt_schlagwort = models.ForeignKey(Projekt, models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'projekt_schlagwort'


class RegistrationCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    username = models.CharField(max_length=255)
    token = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'registration_code'


class Role(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    authority = models.CharField(unique=True, max_length=255)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'role'


class Rolle(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'rolle'


class RolleRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    ereignis = models.ForeignKey(Ereignis, models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    akteur = models.ForeignKey(Akteur, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'rolle_relation'


class RolleRelationRolle(models.Model):
    rolle_relation_rollen = models.ForeignKey(RolleRelation, models.DO_NOTHING)
    rolle = models.ForeignKey(Rolle, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'rolle_relation_rolle'


class RolleSynonyme(models.Model):
    rolle = models.ForeignKey(Rolle, models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'rolle_synonyme'


class Sammlung(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'sammlung'


class SammlungVerknuepfteProjekte(models.Model):
    sammlung = models.OneToOneField(Sammlung, models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, projekt_id) found, that is not supported. The first column is selected.
    projekt = models.ForeignKey(Projekt, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'sammlung_verknuepfte_projekte'
        unique_together = (('sammlung', 'projekt'),)


class Schlagwort(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(max_length=255, blank=True, null=True)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255)
    label_de = models.CharField(max_length=255)
    description_en = models.TextField()

    class Meta:
        managed = False
        db_table = 'schlagwort'


class SchlagwortSynomymDe(models.Model):
    schlagwort = models.ForeignKey(Schlagwort, models.DO_NOTHING)
    synomym_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'schlagwort_synomym_de'


class SchlagwortSynomymEn(models.Model):
    schlagwort = models.ForeignKey(Schlagwort, models.DO_NOTHING)
    synomym_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'schlagwort_synomym_en'


class SocialaccountSocialaccount(models.Model):
    provider = models.CharField(max_length=200)
    uid = models.CharField(max_length=191)
    last_login = models.DateTimeField()
    date_joined = models.DateTimeField()
    extra_data = models.JSONField()
    user = models.ForeignKey('UsersUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'socialaccount_socialaccount'
        unique_together = (('provider', 'uid'),)


class SocialaccountSocialapp(models.Model):
    provider = models.CharField(max_length=30)
    name = models.CharField(max_length=40)
    client_id = models.CharField(max_length=191)
    secret = models.CharField(max_length=191)
    key = models.CharField(max_length=191)
    provider_id = models.CharField(max_length=200)
    settings = models.JSONField()

    class Meta:
        managed = False
        db_table = 'socialaccount_socialapp'


class SocialaccountSocialappSites(models.Model):
    id = models.BigAutoField(primary_key=True)
    socialapp = models.ForeignKey(SocialaccountSocialapp, models.DO_NOTHING)
    site = models.ForeignKey(DjangoSite, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'socialaccount_socialapp_sites'
        unique_together = (('socialapp', 'site'),)


class SocialaccountSocialtoken(models.Model):
    token = models.TextField()
    token_secret = models.TextField()
    expires_at = models.DateTimeField(blank=True, null=True)
    account = models.ForeignKey(SocialaccountSocialaccount, models.DO_NOTHING)
    app = models.ForeignKey(SocialaccountSocialapp, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'socialaccount_socialtoken'
        unique_together = (('app', 'account'),)


class Sprache(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'sprache'


class Titel(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    sprache_titel = models.ForeignKey(Sprache, models.DO_NOTHING)
    untertitel = models.CharField(max_length=255, blank=True, null=True)
    titel = models.CharField(max_length=255)
    projekt_id = models.BigIntegerField()
    sprache_untertitel = models.ForeignKey(Sprache, models.DO_NOTHING, related_name='titel_sprache_untertitel_set', blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'titel'
    
    def __str__(self):
        if self.untertitel:
            return f"{self.titel} - {self.untertitel}"
        return self.titel


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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
        managed = False
        db_table = 'user'


class UserDetail(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
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

    class Meta:
        managed = False
        db_table = 'user_detail'


class UserRole(models.Model):
    user = models.OneToOneField(User, models.DO_NOTHING, primary_key=True)  # The composite primary key (user_id, role_id) found, that is not supported. The first column is selected.
    role = models.ForeignKey(Role, models.DO_NOTHING)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'user_role'
        unique_together = (('user', 'role'),)


class UsersUser(models.Model):
    id = models.BigAutoField(primary_key=True)
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()
    name = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'users_user'


class UsersUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(UsersUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'users_user_groups'
        unique_together = (('user', 'group'),)


class UsersUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(UsersUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'users_user_user_permissions'
        unique_together = (('user', 'permission'),)


class VorgefertigteInhaltswarnung(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    text_de = models.CharField(max_length=255)
    text_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'vorgefertigte_inhaltswarnung'


class Zeitpunkt(models.Model):
    id = models.BigAutoField(primary_key=True)
    version = models.BigIntegerField()
    monat = models.BigIntegerField(blank=True, null=True)
    jahr = models.BigIntegerField()
    tag = models.BigIntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'zeitpunkt'
