from django.db import models
from .base import UserTrackedModel


class DigitalesObjekt(models.Model):
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


class DigitalesObjektLizenz(models.Model):
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


class FileUpload(models.Model):
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


class Base64DecodedMultipartFile(models.Model):
    id = models.BigAutoField(primary_key=True)

    class Meta:
        db_table = 'base64decoded_multipart_file'


class DigitalesObjektSchlagwort(models.Model):
    digitales_objekt_objekttypen = models.ForeignKey('DigitalesObjekt', models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'digitales_objekt_schlagwort'

