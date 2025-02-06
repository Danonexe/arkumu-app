from django.db import models
from .base import UserTrackedModel


class Projekt(models.Model):
    id = models.BigAutoField(primary_key=True)
    normdatei = models.TextField(blank=True, null=True)
    dateiabfrage_dokument = models.ForeignKey('FileUpload', models.DO_NOTHING, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    bestehender_lizenzvertrag = models.ForeignKey('BestehenderLizenzvertrag', models.DO_NOTHING, blank=True, null=True)
    date_created = models.DateTimeField()
    signatur = models.CharField(max_length=255, blank=True, null=True)
    rechtsstatus = models.BigIntegerField()
    letzte_modifikation = models.DateTimeField(blank=True, null=True)
    kommentar_de = models.TextField(blank=True, null=True)
    art_lizenzvertrag = models.BigIntegerField(blank=True, null=True)
    neuer_lizenzvertrag = models.ForeignKey('FileUpload', models.DO_NOTHING, related_name='projekt_neuer_lizenzvertrag_set', blank=True, null=True)
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
    dokumentation_lizenzvertrag = models.ForeignKey('FileUpload', models.DO_NOTHING, related_name='projekt_dokumentation_lizenzvertrag_set', blank=True, null=True)
    externe_projekt_webseite = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField()
    signatur_einlieferer = models.CharField(max_length=255, blank=True, null=True)
    hochschule = models.ForeignKey('Hochschule', models.DO_NOTHING)
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


class ProjektArt(models.Model):
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


class ProjektKategorie(models.Model):
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


class Titel(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    sprache_titel = models.ForeignKey('Sprache', models.DO_NOTHING)
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING)
    untertitel = models.CharField(max_length=255, blank=True, null=True)
    titel = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    sprache_untertitel = models.ForeignKey('Sprache', models.DO_NOTHING, related_name='titel_sprache_untertitel_set', blank=True, null=True)
    rang = models.BigIntegerField()

    class Meta:
        db_table = 'titel'


class ProjektBeschreibung(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING)
    rang = models.BigIntegerField()
    beschreibung = models.TextField()
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt_beschreibung'


class ProjektRelation(models.Model):
    id = models.BigAutoField(primary_key=True)
    art_der_relation = models.BigIntegerField()
    projekt2 = models.ForeignKey('Projekt', models.DO_NOTHING)
    projekt1 = models.ForeignKey('Projekt', models.DO_NOTHING, related_name='projektrelation_projekt1_set')
    projekt_relationen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_relation'


class ProjektEigenschaftswert(models.Model):
    id = models.BigAutoField(primary_key=True)
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING)
    eigenschaft = models.ForeignKey('Eigenschaft', models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    projekt_eigenschaften_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_eigenschaftswert'


class ProjektProjektArt(models.Model):
    projekt_projekt_art = models.ForeignKey('Projekt', models.DO_NOTHING)
    projekt_art = models.ForeignKey('ProjektArt', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_projekt_art'


class ProjektProjektKategorie(models.Model):
    kategorii = models.ForeignKey('Projekt', models.DO_NOTHING)
    projekt_kategorie = models.ForeignKey('ProjektKategorie', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_projekt_kategorie'


class ProjektSchlagworte(models.Model):
    projekt_schlagworte = models.ForeignKey('Projekt', models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_schlagworte'


class ProjektInhaltswarnung(models.Model):
    projekt_id = models.BigIntegerField()
    inhaltswarnung = models.ForeignKey('Inhaltswarnung', models.DO_NOTHING, blank=True, null=True)
    inhaltswarnungen_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_inhaltswarnung'


class ProjektFileUpload(models.Model):
    projekt_weitere_rechtsdokumente_id = models.BigIntegerField(blank=True, null=True)
    file_upload = models.ForeignKey('FileUpload', models.DO_NOTHING, blank=True, null=True)
    weitere_rechtsdokumente_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_file_upload'


class ProjektEreignis(models.Model):
    projekt_ereignisse = models.ForeignKey('Projekt', models.DO_NOTHING)
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_ereignis'


class ProjektOrganisationseinheit(models.Model):
    projekt_organisationseinheit = models.ForeignKey('Projekt', models.DO_NOTHING)
    organisationseinheit = models.ForeignKey('Organisationseinheit', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'projekt_organisationseinheit'


class ProjektAngegebeneNutzungsrechte(models.Model):
    projekt_id = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte = models.BigIntegerField(blank=True, null=True)
    angegebene_nutzungsrechte_idx = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'projekt_angegebene_nutzungsrechte'


class ProjektKategorieSynonyme(models.Model):
    projekt_kategorie = models.ForeignKey('ProjektKategorie', models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'projekt_kategorie_synonyme'

