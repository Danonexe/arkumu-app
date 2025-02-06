from django.db import models
from .base import UserTrackedModel


class Ort(models.Model):
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


class AkteurOrt(models.Model):
    akteur_wirkungsorte = models.ForeignKey('Akteur', models.DO_NOTHING)
    ort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'akteur_ort'


class Hochschule(models.Model):
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


class Organisationseinheit(models.Model):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.TextField(blank=True, null=True)
    beschreibung_de = models.TextField(blank=True, null=True)
    name_en = models.CharField(max_length=255)
    name_de = models.CharField(max_length=255)
    hochschule = models.ForeignKey('Hochschule', models.DO_NOTHING)

    class Meta:
        db_table = 'organisationseinheit'

