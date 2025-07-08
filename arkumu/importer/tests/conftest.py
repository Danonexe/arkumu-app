"""
Main pytest configuration for arkumu importer tests.
Provides common fixtures and setup for all importer tests.
"""
import pytest
import os
import django
from django.conf import settings
from django.test.utils import get_runner

# Ensure Django is configured
if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
    django.setup()


@pytest.fixture(scope='session')
def django_db_setup():
    """
    Avoid creating/destroying the test database for each test.
    Use the same database for the entire test session.
    """
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Enable database access for all tests.
    This removes the need to mark each test with @pytest.mark.django_db
    """
    pass


@pytest.fixture(scope='session')
def test_runner():
    """Provide Django test runner"""
    TestRunner = get_runner(settings)
    return TestRunner()


@pytest.fixture
def django_user_model():
    """Provide Django user model"""
    from django.contrib.auth import get_user_model
    return get_user_model()




# Common test markers
pytestmark = [
    pytest.mark.django_db,  # Enable database access for all tests
]