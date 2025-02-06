from django.db import models
from .base import UserTrackedModel


class User(models.Model):
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


class UserDetail(models.Model):
    id = models.BigAutoField(primary_key=True)
    anrede = models.CharField(max_length=255)
    date_created = models.DateTimeField()
    vorname = models.CharField(max_length=255)
    newsletter = models.BooleanField(blank=True, null=True)
    ort = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    nachname = models.CharField(max_length=255)
    user = models.ForeignKey('User', models.DO_NOTHING)
    avatar = models.ForeignKey('FileUpload', models.DO_NOTHING, blank=True, null=True)
    hochschule = models.ForeignKey('Hochschule', models.DO_NOTHING, blank=True, null=True)
    max_rows = models.BigIntegerField(blank=True, null=True)
    color_mode = models.CharField(max_length=8, blank=True, null=True)
    email = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'user_detail'


class UserRole(models.Model):
    user = models.OneToOneField('User', models.DO_NOTHING, primary_key=True)  # The composite primary key (user_id, role_id) found, that is not supported. The first column is selected.
    role = models.ForeignKey('Role', models.DO_NOTHING)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()

    class Meta:
        db_table = 'user_role'
        unique_together = (('user', 'role'),)


class Role(models.Model):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    authority = models.CharField(unique=True, max_length=255)

    class Meta:
        db_table = 'role'


class RegistrationCode(models.Model):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    username = models.CharField(max_length=255)
    token = models.CharField(max_length=255)

    class Meta:
        db_table = 'registration_code'

