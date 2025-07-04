"""
Django management command to create a test user for Playwright tests.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a test user for Playwright tests'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='testuser',
            help='Username for the test user (default: testuser)'
        )
        parser.add_argument(
            '--password',
            default='testpassword123',
            help='Password for the test user (default: testpassword123)'
        )
        parser.add_argument(
            '--email',
            default='test@example.com',
            help='Email for the test user (default: test@example.com)'
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']

        # Create or update test user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created test user: {username}')
            )
        else:
            # Update password in case it changed
            user.set_password(password)
            user.email = email
            user.save()
            self.stdout.write(
                self.style.WARNING(f'⚠️  Updated existing test user: {username}')
            )

        self.stdout.write(
            self.style.SUCCESS(f'🔐 Test user ready - Username: {username}, Password: {password}')
        )