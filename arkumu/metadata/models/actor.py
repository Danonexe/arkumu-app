from django.db import models
from .base import UserTrackedModel


class Akteur(models.Model):
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


class AkteurRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    akteur1 = models.ForeignKey('Akteur', models.DO_NOTHING)
    akteur2 = models.ForeignKey('Akteur', models.DO_NOTHING, related_name='akteurrelation_akteur2_set')
    akteur_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'akteur_relation'


class Rolle(models.Model):
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


class AkteurRolle(models.Model):
    akteur_berufe_taetigkeiten = models.ForeignKey('Akteur', models.DO_NOTHING)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'akteur_rolle'


class AkteurMitwirkungsRolle(models.Model):
    akteur_berufe_taetigkeiten_id = models.BigIntegerField()
    mitwirkungs_rolle_id = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'akteur_mitwirkungs_rolle'


class RolleRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING)
    last_updated_by = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING)

    class Meta:
        db_table = 'rolle_relation'


class RolleSynonyme(models.Model):
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'rolle_synonyme'


class RolleRelationRolle(models.Model):
    rolle_relation_rollen = models.ForeignKey('RolleRelation', models.DO_NOTHING)
    rolle = models.ForeignKey('Rolle', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'rolle_relation_rolle'

