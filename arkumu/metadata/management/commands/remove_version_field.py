from django.core.management.base import BaseCommand
from django.apps import apps
import os
import re

class Command(BaseCommand):
    help = 'Removes version field from metadata app model definitions in models directory'

    def modify_file(self, file_path):
        try:
            # Read the model file
            with open(file_path, 'r') as file:
                lines = file.readlines()

            # Pattern to match version field definition
            version_pattern = re.compile(r'^\s*version\s*=\s*models\..*Field.*$')
            
            # Keep all lines that don't match the version field pattern
            new_lines = [line for line in lines if not version_pattern.match(line)]

            # Only write if we actually removed something
            if len(new_lines) != len(lines):
                with open(file_path, 'w') as file:
                    file.writelines(new_lines)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully removed version field from {os.path.basename(file_path)}'
                    )
                )
                return True
            return False

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Failed to modify {file_path}: {str(e)}'
                )
            )
            return False

    def handle(self, *args, **options):
        # Get the metadata app config
        metadata_app = apps.get_app_config('metadata')
        models_dir = os.path.join(metadata_app.path, 'models')

        if not os.path.exists(models_dir):
            self.stdout.write(
                self.style.ERROR(
                    f'Models directory not found at {models_dir}'
                )
            )
            return

        files_modified = 0
        # Process all Python files in the models directory
        for filename in os.listdir(models_dir):
            if filename.endswith('.py') and filename != '__init__.py':
                file_path = os.path.join(models_dir, filename)
                if self.modify_file(file_path):
                    files_modified += 1

        if files_modified > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully processed {files_modified} model files'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'No version fields found in any model files'
                )
            )
