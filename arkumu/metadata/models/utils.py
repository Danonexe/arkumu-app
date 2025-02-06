from django.db import models
from .base import UserTrackedModel


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
        db_table = 'audit_log'


class DataImporter(models.Model):
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


class Tooltip(models.Model):
    id = models.BigAutoField(primary_key=True)
    tt_text_en = models.CharField(max_length=1024, blank=True, null=True)
    tt_text_de = models.CharField(max_length=1024, blank=True, null=True)
    view = models.CharField(max_length=255)
    field = models.CharField(max_length=255)

    class Meta:
        db_table = 'tooltip'
        unique_together = (('view', 'field'),)

