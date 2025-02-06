from django.core.management.base import BaseCommand
import os
import re
import shutil

class Command(BaseCommand):
    help = 'Splits models.py into separate files in models_split directory (to be renamed to models)'

    MODEL_GROUPS = {
        'base': [], # base.py will be copied directly
        'user': ['User', 'UserDetail', 'UserRole', 'Role', 'RegistrationCode'],
        'core': [
            'Projekt', 'ProjektArt', 'ProjektKategorie', 'Titel', 'ProjektBeschreibung',
            'ProjektRelation', 'ProjektEigenschaftswert', 'ProjektProjektArt',
            'ProjektProjektKategorie', 'ProjektSchlagworte', 'ProjektInhaltswarnung',
            'ProjektFileUpload', 'ProjektEreignis', 'ProjektOrganisationseinheit',
            'ProjektAngegebeneNutzungsrechte', 'ProjektKategorieSynonyme'
        ],
        'actor': [
            'Akteur', 'AkteurRelation', 'Rolle', 'AkteurRolle',
            'AkteurMitwirkungsRolle', 'RolleRelation', 'RolleSynonyme',
            'RolleRelationRolle'
        ],
        'location': ['Ort', 'AkteurOrt', 'Hochschule', 'Organisationseinheit'],
        'media': [
            'DigitalesObjekt', 'DigitalesObjektLizenz', 'FileUpload',
            'Base64DecodedMultipartFile', 'DigitalesObjektSchlagwort'
        ],
        'equipment': [
            'PhysischesObjekt', 'EquipmentSoftware', 'Equipmentart',
            'Informationstraeger', 'Informationstraegertyp',
            'PhysischesObjektProduktId', 'PhysischesObjektAkteur',
            'PhysischesObjektEigentuemer', 'PhysischesObjektBesitzer',
            'PhysischesObjektMaterialschlagworte', 'PhysischesObjektSchlagworte',
            'PhysischesObjektTechnikschlagworte',
            'Informationstraegereigenschaft', 'InformationstraegerEigentuemer',
            'InformationstraegerOriginalsprachen', 'InformationstraegerUntertitelsprachen',
            'InformationstraegerEigenschaftswert', 'InformationstraegerSprache',
            'InformationstraegertypSynonyme', 'InformationstraegerSprachfassungen',
            'InformationstraegerSchlagwort', 'InformationstraegerBesitzer',
            'InformationstraegerAkteur'
        ],
        'events': [
            'Ereignis', 'EreignisTyp', 'EreignisRelation', 'Zeitpunkt',
            'EreignisTypSynonyme', 'EreignisBeschreibung', 'EreignisPhysischesObjekt',
            'EreignisDigitalesObjekt', 'EreignisInformationstraeger', 'EreignisRolle',
            'EreignisOrt', 'EreignisEigenschaftswert', 'EreignisEquipmentSoftware',
            'EreignisAkteur'
        ],
        'classification': [
            'Schlagwort', 'SchlagwortSynonymeDe', 'SchlagwortSynonymeEn',
            'Sprache', 'Eigenschaft', 'Inhaltswarnung', 'Materialschlagwort',
            'MaterialschlagwortSynonymEn', 'MaterialschlagwortSynonymDe'
        ],
        'collection': [
            'Sammlung', 'SammlungVerknuepfteDigitaleObjekte',
            'SammlungVerknuepfteEreignisse', 'SammlungVerknuepfteInformationstraeger',
            'SammlungVerknuepftePhysischeObjekte', 'SammlungVerknuepfteProjekte',
            'SammlungVerknuepftesEquipment'
        ],
        'licensing': ['BestehenderLizenzvertrag', 'ProduktId', 'Nummernart'],
        'utils': ['AuditLog', 'DataImporter', 'Tooltip']
    }

    def find_all_models(self, content):
        pattern = r"class\s+(\w+)\s*\([^)]*(?:models\.Model|UserTrackedModel)[^)]*\)"
        abstract_pattern = r"class\s+(\w+).*?\n\s+class\s+Meta:.*?\n\s+abstract\s+=\s+True"
        models = re.findall(pattern, content)
        abstract_models = re.findall(abstract_pattern, content, re.DOTALL)
        return set(models) - set(abstract_models)

    def extract_model_definition(self, content, model_name):
        pattern = f"class\\s+{re.escape(model_name)}\\s*\\([^)]*\\):.*?(?=\\n(?:class\\s+\\w+\\(|$))"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            model_code = match.group(0).rstrip()
            
            # Add quotes to ForeignKey references that don't have them
            model_code = re.sub(
                r'models\.ForeignKey\((\w+),',
                r"models.ForeignKey('\1',",
                model_code
            )
            # Also handle OneToOneField
            model_code = re.sub(
                r'models\.OneToOneField\((\w+),',
                r"models.OneToOneField('\1',",
                model_code
            )
            # Also handle ManyToManyField
            model_code = re.sub(
                r'models\.ManyToManyField\((\w+),',
                r"models.ManyToManyField('\1',",
                model_code
            )
            
            return model_code + '\n'
        return None

    def handle(self, *args, **options):
        base_dir = 'arkumu/metadata/models'
        split_dir = f'{base_dir}/models_split'
        models_file = f'{base_dir}/models.py'
        base_file = f'{base_dir}/base.py'

        if not os.path.exists(split_dir):
            os.makedirs(split_dir)
        shutil.copy2(base_file, f'{split_dir}/base.py')

        with open(models_file, 'r') as f:
            content = f.read()

        # Verify models
        existing_models = self.find_all_models(content)
        mapped_models = {model for models in self.MODEL_GROUPS.values() for model in models}
        
        missing_models = existing_models - mapped_models
        if missing_models:
            self.stdout.write(self.style.WARNING(f'Missing models in MODEL_GROUPS: {", ".join(missing_models)}'))
            return

        # Create split files
        for group, models in self.MODEL_GROUPS.items():
            if group != 'base' and models:
                # Only these three imports needed during transition
                group_content = [
                    'from django.db import models',
                    'from .base import UserTrackedModel',
                    '\n'
                ]
                
                for model in models:
                    model_def = self.extract_model_definition(content, model)
                    if model_def:
                        group_content.append(model_def + '\n')
                    else:
                        self.stdout.write(self.style.ERROR(f'Model {model} not found in models.py'))
                        return

                with open(os.path.join(split_dir, f'{group}.py'), 'w') as f:
                    f.write('\n'.join(group_content))

        # Create __init__.py in models_split
        init_content = ['"""Django models for the metadata app."""',
                       'from .base import UserTrackedModel']
        
        # Add imports for each group's models
        for group, models in self.MODEL_GROUPS.items():
            if group != 'base' and models:
                init_content.append(f'from .{group} import {", ".join(models)}')
        
        init_content.extend(['', '__all__ = ['])
        init_content.append('    "UserTrackedModel",')
        for models in self.MODEL_GROUPS.values():
            for model in models:
                init_content.append(f'    "{model}",')
        init_content.append(']')

        with open(os.path.join(split_dir, '__init__.py'), 'w') as f:
            f.write('\n'.join(init_content))

        self.stdout.write(self.style.SUCCESS('Successfully split models into separate files in models_split/'))
