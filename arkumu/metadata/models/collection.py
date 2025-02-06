from django.db import models
from .base import UserTrackedModel


class Sammlung(models.Model):
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


class SammlungVerknuepfteDigitaleObjekte(models.Model):
    sammlung = models.OneToOneField('Sammlung', models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, digitales_objekt_id) found, that is not supported. The first column is selected.
    digitales_objekt = models.ForeignKey('DigitalesObjekt', models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_digitale_objekte'
        unique_together = (('sammlung', 'digitales_objekt'),)


class SammlungVerknuepfteEreignisse(models.Model):
    sammlung = models.OneToOneField('Sammlung', models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, ereignis_id) found, that is not supported. The first column is selected.
    ereignis = models.ForeignKey('Ereignis', models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_ereignisse'
        unique_together = (('sammlung', 'ereignis'),)


class SammlungVerknuepfteInformationstraeger(models.Model):
    sammlung = models.OneToOneField('Sammlung', models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, informationstraeger_id) found, that is not supported. The first column is selected.
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_informationstraeger'
        unique_together = (('sammlung', 'informationstraeger'),)


class SammlungVerknuepftePhysischeObjekte(models.Model):
    sammlung = models.OneToOneField('Sammlung', models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, physisches_objekt_id) found, that is not supported. The first column is selected.
    physisches_objekt = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_physische_objekte'
        unique_together = (('sammlung', 'physisches_objekt'),)


class SammlungVerknuepfteProjekte(models.Model):
    sammlung = models.OneToOneField('Sammlung', models.DO_NOTHING, primary_key=True)  # The composite primary key (sammlung_id, projekt_id) found, that is not supported. The first column is selected.
    projekt = models.ForeignKey('Projekt', models.DO_NOTHING)

    class Meta:
        db_table = 'sammlung_verknuepfte_projekte'
        unique_together = (('sammlung', 'projekt'),)


class SammlungVerknuepftesEquipment(models.Model):
    sammlung = models.ForeignKey('Sammlung', models.DO_NOTHING)
    equipment_software = models.ForeignKey('EquipmentSoftware', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'sammlung_verknuepftes_equipment'

