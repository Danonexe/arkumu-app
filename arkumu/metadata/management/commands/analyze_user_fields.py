from django.core.management.base import BaseCommand
from django.db import models
from arkumu.metadata.models import bak as metadata_models
from datetime import datetime
import os

class Command(BaseCommand):
    help = 'Collects all unique user references from created_by and last_updated_by fields in metadata models'

    def handle(self, *args, **options):
        # Create output directory if it doesn't exist
        output_dir = 'user_analysis'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(output_dir, f'user_references_{timestamp}.txt')
        
        user_references = set()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("User References Analysis\n")
            f.write("======================\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Get all models from metadata app
            metadata_model_classes = [
                getattr(metadata_models, name) for name in dir(metadata_models)
                if isinstance(getattr(metadata_models, name), type) 
                and issubclass(getattr(metadata_models, name), models.Model)
                and getattr(metadata_models, name) != models.Model
            ]

            for model in metadata_model_classes:
                # Check each field in the model
                for field in model._meta.fields:
                    if isinstance(field, (models.CharField, models.TextField)):
                        if field.name in ['created_by', 'last_updated_by']:
                            values = model.objects.values_list(field.name, flat=True).distinct()
                            values = [str(value) for value in values if value is not None]
                            
                            if values:
                                f.write(f"\nModel: {model.__name__}\n")
                                f.write(f"Field: {field.name}\n")
                                f.write(f"Unique users found: {len(values)}\n")
                                f.write("User references: " + ", ".join(values) + "\n")
                                
                                user_references.update(values)
            
            # Get all existing usernames from User model
            existing_usernames = set(metadata_models.User.objects.values_list('username', flat=True))
            
            # Summary
            f.write("\n=== Summary ===\n")
            f.write(f"Total unique user references found: {len(user_references)}\n")
            f.write("\nAll unique user references:\n")
            for ref in sorted(user_references):
                exists = ref in existing_usernames
                f.write(f"- {ref} {'(exists in User table)' if exists else '(not found in User table)'}\n")
            
            # Statistics
            f.write("\n=== Statistics ===\n")
            matching_users = user_references.intersection(existing_usernames)
            missing_users = user_references.difference(existing_usernames)
            f.write(f"Total user references: {len(user_references)}\n")
            f.write(f"References matching User table: {len(matching_users)}\n")
            f.write(f"References not found in User table: {len(missing_users)}\n")

            if missing_users:
                f.write("\nUser references not found in User table:\n")
                for user in sorted(missing_users):
                    f.write(f"- {user}\n")

        self.stdout.write(self.style.SUCCESS(f'Analysis completed. Results saved to {filename}')) 