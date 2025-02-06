from django.core.management.base import BaseCommand
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Modifies models to inherit from UserTrackedModel where appropriate'


    def process_model_block(self, lines):
        """Process a complete model block to inherit from UserTrackedModel"""
        new_lines = []
        model_name = None
        meta_content = []
        in_meta = False

        for line in lines:
            if line.strip().startswith('class ') and 'models.Model' in line:
                # Skip if already inheriting from UserTrackedModel
                if 'UserTrackedModel' in line:
                    return lines, False, None
                
                model_name = line.split('(')[0].split()[-1]
                # Replace models.Model with UserTrackedModel
                line = line.replace('models.Model', 'UserTrackedModel')
                new_lines.append(line)
                continue
            
            if line.strip().startswith('class Meta:'):
                in_meta = True
                meta_content.append(line)
                continue
                
            if in_meta:
                if line.strip() and not line.startswith('    class'):
                    meta_content.append(line)
                    continue
                else:
                    in_meta = False
                    new_lines.extend(meta_content)
                    meta_content = []
            
            new_lines.append(line)

        # Add Meta content if we collected any and haven't added it yet
        if meta_content:
            new_lines.extend(meta_content)

        return new_lines, True, model_name

    def handle(self, *args, **options):
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        models_path = os.path.join(current_dir, 'models', 'models.py')
        new_models_path = os.path.join(current_dir, 'models', 'models_with_user_fields.py')

        self.stdout.write(f'Reading models.py from: {models_path}')

        try:
            with open(models_path, 'r') as file:
                lines = file.readlines()
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Could not find models.py at {models_path}'))
            return

        new_lines = []
        current_model_lines = []
        models_modified = []
        in_model = False

        # Add imports at the top
        new_lines.extend([
            'from django.db import models\n',
            'from django.conf import settings\n',
            'from django.utils.timezone import now\n',
            'from .base import UserTrackedModel\n',
            '\n'
        ])

        for line in lines:
            if line.strip().startswith('class ') and 'models.Model' in line:
                # Process previous model if it exists
                if current_model_lines:
                    processed_lines, was_modified, model_name = self.process_model_block(current_model_lines)
                    new_lines.extend(processed_lines)
                    if was_modified:
                        models_modified.append(model_name)
                
                # Start new model
                current_model_lines = [line]
                in_model = True
                
            elif in_model:
                current_model_lines.append(line)
                
                # Check if model definition is complete
                if line.strip() == '' and not any(next_line.strip().startswith(('class Meta:', 'db_table')) for next_line in lines[lines.index(line)+1:lines.index(line)+3]):
                    processed_lines, was_modified, model_name = self.process_model_block(current_model_lines)
                    new_lines.extend(processed_lines)
                    if was_modified:
                        models_modified.append(model_name)
                    current_model_lines = []
                    in_model = False
            else:
                new_lines.append(line)

        # Process last model if exists
        if current_model_lines:
            processed_lines, was_modified, model_name = self.process_model_block(current_model_lines)
            new_lines.extend(processed_lines)
            if was_modified:
                models_modified.append(model_name)

        try:
            with open(new_models_path, 'w') as file:
                file.writelines(new_lines)
            
            if models_modified:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully generated new model file at: {new_models_path}\n'
                    f'Modified models: {", ".join(models_modified)}\n'
                    '\nNext steps:'
                    '\n1. Review the changes in models_with_user_fields.py'
                    '\n2. If satisfied, copy the content to models.py'
                    '\n3. Make migrations'
                    '\n4. Run migrations'
                ))
            else:
                self.stdout.write(self.style.WARNING('No models found with created_by field'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error writing new file: {str(e)}')) 