from django.db import models
from .base import UserTrackedModel


class BestehenderLizenzvertrag(models.Model):
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


class ProduktId(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    nummernart = models.ForeignKey('Nummernart', models.DO_NOTHING)
    last_updated = models.DateTimeField()
    wert = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING)

    class Meta:
        db_table = 'produkt_id'


class Nummernart(models.Model):
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

