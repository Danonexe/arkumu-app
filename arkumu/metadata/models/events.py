from django.db import models
from .base import UserTrackedModel


class Ereignis(models.Model):
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


class EreignisTyp(models.Model):
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


class EreignisRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    ereignis2 = models.ForeignKey('Ereignis', models.DO_NOTHING)
    ereignis1 = models.ForeignKey('Ereignis', models.DO_NOTHING, related_name='ereignisrelation_ereignis1_set')
    ereignis_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'ereignis_relation'


class Zeitpunkt(models.Model):
    id = models.BigAutoField(primary_key=True)
    monat = models.BigIntegerField(blank=True, null=True)
    jahr = models.BigIntegerField()
    tag = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'zeitpunkt'


class EreignisTypSynonyme(models.Model):
    ereignis_typ_id = models.BigIntegerField()
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_typ_synonyme'


class EreignisBeschreibung(models.Model):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    beschreibung = models.TextField()
    wertigkeit = models.BigIntegerField()
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_beschreibung'


class EreignisPhysischesObjekt(models.Model):
    physisches_objekt = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING, blank=True, null=True)
    ereignis_physische_objekte_id = models.BigIntegerField()

    class Meta:
        db_table = 'ereignis_physisches_objekt'


class EreignisDigitalesObjekt(models.Model):
    ereignis_digitale_objekte = models.ForeignKey('Ereignis', models.DO_NOTHING)
    digitales_objekt = models.ForeignKey('DigitalesObjekt', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_digitales_objekt'


class EreignisInformationstraeger(models.Model):
    ereignis_informationstraeger = models.ForeignKey('Ereignis', models.DO_NOTHING)
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_informationstraeger'


class EreignisRolle(models.Model):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING)
    urheber = models.BooleanField(blank=True, null=True)
    leistungsschutzrechte = models.BooleanField(blank=True, null=True)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING)
    ereignis_rollen_idx = models.BigIntegerField(blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField(blank=True, null=True)
    ungesicherte_zuschreibung = models.BooleanField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_rolle'


class EreignisOrt(models.Model):
    ereignis_orte = models.ForeignKey('Ereignis', models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_ort'


class EreignisEigenschaftswert(models.Model):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING)
    eigenschaft = models.ForeignKey('Eigenschaft', models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    ereignis_eigenschaften_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'ereignis_eigenschaftswert'


class EreignisEquipmentSoftware(models.Model):
    ereignis_equipment_software = models.ForeignKey('Ereignis', models.DO_NOTHING)
    equipment_software = models.ForeignKey('EquipmentSoftware', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_equipment_software'


class EreignisAkteur(models.Model):
    ereignis_akteure = models.ForeignKey('Ereignis', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ereignis_akteur'

