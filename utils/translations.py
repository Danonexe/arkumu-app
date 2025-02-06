from modeltranslation.translator import register, TranslationOptions
from .models import *

@register(Akteur)
class AkteurTranslation(TranslationOptions):
    fields = ('kommentar', 'kurzbiografie', 'name')

@register(BestehenderLizenzvertrag)
class BestehenderLizenzvertragTranslation(TranslationOptions):
    fields = ('bezeichnung', 'vertrags_text')

@register(DigitalesObjekt)
class DigitalesObjektTranslation(TranslationOptions):
    fields = ('beschreibende_metadaten_bildbeschreibung', 'beschreibende_metadaten_eigenschaften', 'beschreibende_metadaten_inhalt', 'beschreibende_metadaten_kommentar')

@register(DigitalesObjektLizenz)
class DigitalesObjektLizenzTranslation(TranslationOptions):
    fields = ('anzeige_text', 'bezeichnung', 'lizenz_text')

@register(Eigenschaft)
class EigenschaftTranslation(TranslationOptions):
    fields = ('description', 'name')

@register(EquipmentSoftware)
class EquipmentSoftwareTranslation(TranslationOptions):
    fields = ('beschreibung', 'name')

@register(Equipmentart)
class EquipmentartTranslation(TranslationOptions):
    fields = ('name')

@register(Ereignis)
class EreignisTranslation(TranslationOptions):
    fields = ('kommentar')

@register(EreignisTyp)
class EreignisTypTranslation(TranslationOptions):
    fields = ('name')

@register(Hochschule)
class HochschuleTranslation(TranslationOptions):
    fields = ('name')

@register(Informationstraeger)
class InformationstraegerTranslation(TranslationOptions):
    fields = ('beschreibung', 'erhaltungszustand', 'kommentar', 'name')

@register(Informationstraegereigenschaft)
class InformationstraegereigenschaftTranslation(TranslationOptions):
    fields = ('name')

@register(Informationstraegertyp)
class InformationstraegertypTranslation(TranslationOptions):
    fields = ('name')

@register(Inhaltswarnung)
class InhaltswarnungTranslation(TranslationOptions):
    fields = ('text')

@register(Materialschlagwort)
class MaterialschlagwortTranslation(TranslationOptions):
    fields = ('description', 'label')

@register(Nummernart)
class NummernartTranslation(TranslationOptions):
    fields = ('name')

@register(Organisationseinheit)
class OrganisationseinheitTranslation(TranslationOptions):
    fields = ('beschreibung', 'name')

@register(Ort)
class OrtTranslation(TranslationOptions):
    fields = ('name')

@register(PhysischesObjekt)
class PhysischesObjektTranslation(TranslationOptions):
    fields = ('beschreibung', 'erhaltungszustand', 'kommentar', 'kommentar_technik', 'name')

@register(Projekt)
class ProjektTranslation(TranslationOptions):
    fields = ('kommentar')

@register(ProjektArt)
class ProjektArtTranslation(TranslationOptions):
    fields = ('name')

@register(ProjektKategorie)
class ProjektKategorieTranslation(TranslationOptions):
    fields = ('name')

@register(Rolle)
class RolleTranslation(TranslationOptions):
    fields = ('name')

@register(Sammlung)
class SammlungTranslation(TranslationOptions):
    fields = ('beschreibung', 'bezeichnung')

@register(Schlagwort)
class SchlagwortTranslation(TranslationOptions):
    fields = ('description', 'label')

@register(Sprache)
class SpracheTranslation(TranslationOptions):
    fields = ('name')

@register(Tooltip)
class TooltipTranslation(TranslationOptions):
    fields = ('tt_text')
