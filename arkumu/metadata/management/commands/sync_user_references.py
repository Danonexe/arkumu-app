from django.core.management.base import BaseCommand
from django.db import models
from arkumu.metadata.models import bak as metadata_models
from arkumu.users.models import User
from datetime import datetime
import os

class Command(BaseCommand):
    help = 'Creates User records for any created_by or last_updated_by references that dont exist'

    def handle(self, *args, **options):
        # Create output directory if it doesn't exist
        output_dir = 'user_sync'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(output_dir, f'user_sync_{timestamp}.txt')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("User Synchronization Report\n")
            f.write("==========================\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # First delete invalid users
            invalid_usernames = ['', ' ', 'n/a', 'na', 'N/A', None]
            User.objects.filter(username__in=invalid_usernames).delete()
            User.objects.filter(username__isnull=True).delete()

            # Then delete duplicate users (keeping lowercase versions)
            usernames_to_delete = []
            for user in User.objects.all():
                # Find users with same username in different case
                if User.objects.filter(username__iexact=user.username).count() > 1:
                    # Keep the lowercase version, mark others for deletion
                    if user.username != user.username.lower():
                        usernames_to_delete.append(user.username)
            
            # Delete the duplicates
            User.objects.filter(username__in=usernames_to_delete).delete()

            # Now collect unique usernames from metadata
            user_references = set()
            for model in [getattr(metadata_models, name) for name in dir(metadata_models)
                         if isinstance(getattr(metadata_models, name), type) 
                         and issubclass(getattr(metadata_models, name), models.Model)
                         and getattr(metadata_models, name) != models.Model]:
                
                for field in model._meta.fields:
                    if isinstance(field, (models.CharField, models.TextField)):
                        if field.name in ['created_by', 'last_updated_by']:
                            values = model.objects.values_list(field.name, flat=True).distinct()
                            # Clean and lowercase usernames, skip invalid ones
                            values = [str(v).strip().lower() for v in values 
                                    if v and v.strip() and v.strip().lower() not in ['n/a', 'na', '']]
                            user_references.update(values)
            
            # Get existing usernames (in lowercase)
            existing_users = {u.lower() for u in User.objects.values_list('username', flat=True)}
            
            # Create missing users
            missing_users = user_references - existing_users
            
            f.write("\n=== Statistics ===\n")
            f.write(f"Total valid user references found: {len(user_references)}\n")
            f.write(f"Existing users: {len(existing_users)}\n")
            f.write(f"Users to create: {len(missing_users)}\n\n")
            
            if missing_users:
                f.write("Creating new users...\n\n")
                for username in missing_users:
                    try:
                        User.objects.create(
                            username=username,
                            email=f"{username}@uni-koeln.de",
                            name=username,
                            role=User.Roles.BASIC_USER,
                            is_active=True
                        )
                        f.write(f"✓ Created user: {username} ({username}@uni-koeln.de)\n")
                    except Exception as e:
                        f.write(f"✗ Failed to create user {username}: {str(e)}\n")
            else:
                f.write("No new users need to be created.\n")
            
            f.write("\n=== Final Status ===\n")
            final_count = User.objects.count()
            f.write(f"Total users in system: {final_count}\n")
            
            f.write("\n=== Complete List of All Users ===\n")
            all_users = User.objects.all().order_by('username')
            for user in all_users:
                f.write(f"Username: {user.username}, Email: {user.email}, Role: {user.role}\n")

        self.stdout.write(self.style.SUCCESS(f'Synchronization completed. Results saved to {filename}'))
