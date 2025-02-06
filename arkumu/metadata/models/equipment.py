from django.db import models
from .base import UserTrackedModel


class PhysischesObjekt(models.Model):
    id = models.BigAutoField(primary_key=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)
    beschreibung_de = models.TextField(blank=True, null=True)
    beschreibung_en = models.TextField(blank=True, null=True)
    kommentar_de = models.TextField(blank=True, null=True)
    kommentar_en = models.TextField(blank=True, null=True)
    kommentar_intern = models.TextField(blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    measurements = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.TextField(blank=True, null=True)
    persistenter_identifikator = models.CharField(max_length=255, blank=True, null=True)
    kommentar_technik_de = models.TextField(blank=True, null=True)
    kommentar_technik_en = models.TextField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()

    class Meta:
        db_table = 'physisches_objekt'


class EquipmentSoftware(models.Model):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    hersteller = models.CharField(max_length=255, blank=True, null=True)
    equipmentart = models.ForeignKey('Equipmentart', models.DO_NOTHING)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'equipment_software'


class Equipmentart(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    aatid = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        db_table = 'equipmentart'


class Informationstraeger(models.Model):
    id = models.BigAutoField(primary_key=True)
    beschreibung_en = models.CharField(max_length=255, blank=True, null=True)
    kompilationstitel = models.CharField(max_length=255, blank=True, null=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    measurements = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    normdaten = models.CharField(max_length=255, blank=True, null=True)
    aufbewahrungsort = models.ForeignKey('Ort', models.DO_NOTHING, blank=True, null=True)
    kommentar_de = models.CharField(max_length=255, blank=True, null=True)
    kompilations_reihennummer = models.CharField(max_length=255, blank=True, null=True)
    beschreibung_de = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_en = models.CharField(max_length=255, blank=True, null=True)
    name_en = models.CharField(max_length=255, blank=True, null=True)
    erhaltungszustand_de = models.CharField(max_length=255, blank=True, null=True)
    externe_inventar_signaturnummern = models.CharField(max_length=255, blank=True, null=True)
    informationstraegertyp = models.ForeignKey('Informationstraegertyp', models.DO_NOTHING)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    provenienz = models.CharField(max_length=255, blank=True, null=True)
    kommentar_en = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255, blank=True, null=True)
    label = models.CharField(max_length=255, blank=True, null=True)
    interner_kommentar = models.CharField(max_length=255, blank=True, null=True)
    kompilation = models.BigIntegerField(blank=True, null=True)
    aatid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255, blank=True, null=True)
    gndid = models.CharField(max_length=255, blank=True, null=True)
    pbcore_link = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger'


class Informationstraegertyp(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    aatid = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField()
    gndid = models.CharField(max_length=255, blank=True, null=True)
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    pbcore_link = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraegertyp'


class PhysischesObjektProduktId(models.Model):
    physisches_objekt_produkt_id = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    produkt_id = models.ForeignKey('ProduktId', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_produkt_id'


class PhysischesObjektAkteur(models.Model):
    physisches_objekt_besitzer = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)
    physisches_objekt_eigentuemer = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING, related_name='physischesobjektakteur_physisches_objekt_eigentuemer_set')

    class Meta:
        db_table = 'physisches_objekt_akteur'


class PhysischesObjektEigentuemer(models.Model):
    physisches_objekt_eigentuemer = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_eigentuemer'


class PhysischesObjektBesitzer(models.Model):
    physisches_objekt_besitzer = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_besitzer'


class PhysischesObjektMaterialschlagworte(models.Model):
    physisches_objekt_materialschlagworte = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_materialschlagworte'


class PhysischesObjektSchlagworte(models.Model):
    physisches_objekt_schlagworte = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_schlagworte'


class PhysischesObjektTechnikschlagworte(models.Model):
    physisches_objekt_technikschlagworte = models.ForeignKey('PhysischesObjekt', models.DO_NOTHING)
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'physisches_objekt_technikschlagworte'


class Informationstraegereigenschaft(models.Model):
    id = models.BigAutoField(primary_key=True)
    last_updated_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField()
    last_updated = models.DateTimeField()
    wikidataid = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    name_de = models.CharField(max_length=255)

    class Meta:
        db_table = 'informationstraegereigenschaft'


class InformationstraegerEigentuemer(models.Model):
    informationstraeger_eigentuemer = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_eigentuemer'


class InformationstraegerOriginalsprachen(models.Model):
    informationstraeger_originalsprachen = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_originalsprachen'


class InformationstraegerUntertitelsprachen(models.Model):
    informationstraeger_untertitelsprachen = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_untertitelsprachen'


class InformationstraegerEigenschaftswert(models.Model):
    id = models.BigAutoField(primary_key=True)
    eigenschaft = models.ForeignKey('Eigenschaft', models.DO_NOTHING)
    wert = models.CharField(max_length=255)
    informationstraeger = models.ForeignKey('Informationstraeger', models.DO_NOTHING)

    class Meta:
        db_table = 'informationstraeger_eigenschaftswert'


class InformationstraegerSprache(models.Model):
    informationstraeger_untertitelsprachen = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_originalsprachen = models.ForeignKey('Informationstraeger', models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_originalsprachen_set')
    informationstraeger_sprachfassungen = models.ForeignKey('Informationstraeger', models.DO_NOTHING, related_name='informationstraegersprache_informationstraeger_sprachfassungen_set')

    class Meta:
        db_table = 'informationstraeger_sprache'


class InformationstraegertypSynonyme(models.Model):
    informationstraegertyp = models.ForeignKey('Informationstraegertyp', models.DO_NOTHING)
    synonyme_string = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'informationstraegertyp_synonyme'


class InformationstraegerSprachfassungen(models.Model):
    informationstraeger_sprachfassungen = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    sprache = models.ForeignKey('Sprache', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_sprachfassungen'


class InformationstraegerSchlagwort(models.Model):
    schlagwort = models.ForeignKey('Schlagwort', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_materialschlagwort = models.ForeignKey('Informationstraeger', models.DO_NOTHING)

    class Meta:
        db_table = 'informationstraeger_schlagwort'


class InformationstraegerBesitzer(models.Model):
    informationstraeger_besitzer = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'informationstraeger_besitzer'


class InformationstraegerAkteur(models.Model):
    informationstraeger_besitzer = models.ForeignKey('Informationstraeger', models.DO_NOTHING)
    akteur = models.ForeignKey('Akteur', models.DO_NOTHING, blank=True, null=True)
    informationstraeger_eigentuemer = models.ForeignKey('Informationstraeger', models.DO_NOTHING, related_name='informationstraegerakteur_informationstraeger_eigentuemer_set')

    class Meta:
        db_table = 'informationstraeger_akteur'

