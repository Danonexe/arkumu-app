from django.db import models


class Schlagwort(models.Model):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(unique=True, max_length=255)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255, blank=True, null=True)
    label_de = models.CharField(max_length=255, blank=True, null=True)
    description_en = models.TextField()
    gnd_item = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort'


class SchlagwortSynonymeDe(models.Model):
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING)
    synonyme_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort_synonyme_de'


class SchlagwortSynonymeEn(models.Model):
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING)
    synonyme_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'schlagwort_synonyme_en'


class Sprache(models.Model):
    id = models.BigAutoField(primary_key=True)
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
        db_table = 'sprache'


class Eigenschaft(models.Model):
    id = models.BigAutoField(primary_key=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    description_de = models.CharField(max_length=512)
    description_en = models.CharField(max_length=512)
    type = models.BigIntegerField(blank=True, null=True)

    class Meta:
        db_table = 'eigenschaft'


class Inhaltswarnung(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    text_de = models.CharField(max_length=255, blank=True, null=True)
    text_en = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'inhaltswarnung'


class Materialschlagwort(models.Model):
    id = models.BigAutoField(primary_key=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidata_item = models.CharField(unique=True, max_length=255)
    description_de = models.TextField()
    label_en = models.CharField(max_length=255)
    label_de = models.CharField(max_length=255)
    description_en = models.TextField()
    gndid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort'


class MaterialschlagwortSynonymEn(models.Model):
    materialschlagwort = models.ForeignKey('Materialschlagwort', models.DO_NOTHING)
    synonym_en_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort_synonym_en'


class MaterialschlagwortSynonymDe(models.Model):
    materialschlagwort = models.ForeignKey('Materialschlagwort', models.DO_NOTHING)
    synonym_de_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'materialschlagwort_synonym_de'

