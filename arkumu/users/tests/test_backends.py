import pytest
from unittest.mock import Mock, patch
from django.test import RequestFactory
from datetime import datetime, timezone as dt_timezone

from arkumu.users.models import User, Organization
from arkumu.users.backends import ShibbolethRemoteUserBackend
from arkumu.users.tests.factories import (
    UserFactory,
    OrganizationFactory,
    ShibbolethUserFactory,
)


@pytest.mark.django_db
class TestShibbolethRemoteUserBackend:
    """Test cases for ShibbolethRemoteUserBackend"""

    def setup_method(self):
        """Set up test fixtures"""
        self.backend = ShibbolethRemoteUserBackend()
        self.factory = RequestFactory()

    def test_authenticate_no_remote_user(self):
        """Test authentication with no remote user"""
        request = self.factory.get('/')
        user = self.backend.authenticate(request, None)
        assert user is None

    def test_authenticate_existing_user_by_username(self):
        """Test authentication with existing user found by username"""
        existing_user = UserFactory(username="testuser")
        request = self.factory.get('/')
        request.META = {'mail': 'test@example.com'}
        
        user = self.backend.authenticate(request, "testuser")
        
        assert user == existing_user
        assert user.shibboleth_eppn == "testuser"
        assert user.auth_source == "shibboleth"
        assert user.is_federated_user is True

    def test_authenticate_existing_user_by_eppn(self):
        """Test authentication with existing user found by EPPN"""
        existing_user = ShibbolethUserFactory(
            username="oldusername",
            shibboleth_eppn="user@example.edu"
        )
        request = self.factory.get('/')
        request.META = {'eppn': 'user@example.edu'}
        
        user = self.backend.authenticate(request, "newusername")
        
        assert user == existing_user

    def test_authenticate_existing_user_by_email(self):
        """Test authentication with existing user found by email"""
        existing_user = UserFactory(email="test@example.com")
        request = self.factory.get('/')
        request.META = {
            'mail': 'test@example.com',
            'eppn': 'user@example.edu'
        }
        
        user = self.backend.authenticate(request, "newusername")
        
        assert user == existing_user
        assert user.username == "newusername"
        assert user.shibboleth_eppn == "user@example.edu"
        assert user.auth_source == "shibboleth"

    def test_create_new_shibboleth_user(self):
        """Test creation of new Shibboleth user"""
        org = OrganizationFactory(domain="example.edu")
        request = self.factory.get('/')
        request.META = {
            'mail': 'newuser@example.edu',
            'eppn': 'newuser@example.edu',
            'givenName': 'John',
            'sn': 'Doe',
            'eduPersonScopedAffiliation': 'staff@example.edu'
        }
        
        user = self.backend.authenticate(request, "newuser")
        
        assert user is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.edu"
        assert user.name == "John Doe"
        assert user.shibboleth_eppn == "newuser@example.edu"
        assert user.auth_source == "shibboleth"
        assert user.is_federated_user is True
        assert user.organization == org
        assert user.role == "archivist"  # staff affiliation

    def test_determine_organization_by_domain(self):
        """Test organization determination by email domain"""
        org = OrganizationFactory(domain="uni-koeln.de")
        request = self.factory.get('/')
        request.META = {'mail': 'user@uni-koeln.de'}
        
        determined_org = self.backend._determine_organization(request)
        assert determined_org == org

    def test_determine_organization_by_home_org(self):
        """Test organization determination by schacHomeOrganization"""
        org = OrganizationFactory(code="uni-koeln.de")
        request = self.factory.get('/')
        request.META = {'schacHomeOrganization': 'uni-koeln.de'}
        
        determined_org = self.backend._determine_organization(request)
        assert determined_org == org

    def test_determine_organization_by_entity_id(self):
        """Test organization determination by Shibboleth entity ID"""
        entity_id = "https://idp.uni-koeln.de/idp/shibboleth"
        org = OrganizationFactory(shibboleth_entity_id=entity_id)
        request = self.factory.get('/')
        request.META = {'Shib-Identity-Provider': entity_id}
        
        determined_org = self.backend._determine_organization(request)
        assert determined_org == org

    def test_determine_organization_no_match(self):
        """Test organization determination when no match found"""
        request = self.factory.get('/')
        request.META = {'mail': 'user@unknown.edu'}
        
        determined_org = self.backend._determine_organization(request)
        assert determined_org is None

    def test_determine_initial_role_staff(self):
        """Test role determination for staff affiliation"""
        request = self.factory.get('/')
        request.META = {'eduPersonScopedAffiliation': 'staff@example.edu'}
        
        role = self.backend._determine_initial_role(request, None)
        assert role == "archivist"

    def test_determine_initial_role_faculty(self):
        """Test role determination for faculty affiliation"""
        request = self.factory.get('/')
        request.META = {'eduPersonScopedAffiliation': 'faculty@example.edu'}
        
        role = self.backend._determine_initial_role(request, None)
        assert role == "data_admin"

    def test_determine_initial_role_default(self):
        """Test role determination for unknown affiliation"""
        request = self.factory.get('/')
        request.META = {'eduPersonScopedAffiliation': 'student@example.edu'}
        
        role = self.backend._determine_initial_role(request, None)
        assert role == "researcher"

    @patch('django.utils.timezone.now')
    def test_update_user_from_shibboleth(self, mock_now):
        """Test updating user attributes from Shibboleth"""
        mock_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        mock_now.return_value = mock_time
        
        user = UserFactory(name="Old Name", email="old@example.com")
        request = self.factory.get('/')
        request.META = {
            'givenName': 'John',
            'sn': 'Doe',
            'mail': 'john.doe@example.com',
            'eduPersonScopedAffiliation': 'staff@example.edu'
        }
        
        self.backend.update_user_from_shibboleth(request, user)
        
        user.refresh_from_db()
        assert user.name == "John Doe"
        assert user.email == "john.doe@example.com"
        assert user.shibboleth_affiliation == "staff@example.edu"
        assert user.last_shibboleth_login == mock_time

    def test_update_user_from_shibboleth_no_request(self):
        """Test updating user with no request object"""
        user = UserFactory()
        original_name = user.name
        
        self.backend.update_user_from_shibboleth(None, user)
        
        user.refresh_from_db()
        assert user.name == original_name

    def test_update_user_from_shibboleth_assign_organization(self):
        """Test assigning organization to user without one"""
        org = OrganizationFactory(domain="example.edu")
        user = UserFactory(organization=None)
        request = self.factory.get('/')
        request.META = {'mail': 'user@example.edu'}
        
        self.backend.update_user_from_shibboleth(request, user)
        
        user.refresh_from_db()
        assert user.organization == org

    def test_create_unknown_user_disabled(self):
        """Test authentication when create_unknown_user is False"""
        self.backend.create_unknown_user = False
        request = self.factory.get('/')
        request.META = {'mail': 'newuser@example.com'}
        
        user = self.backend.authenticate(request, "nonexistent")
        assert user is None

    def test_legacy_update_user_attributes_method(self):
        """Test legacy update_user_attributes method for backward compatibility"""
        user = UserFactory()
        request = self.factory.get('/')
        request.META = {'givenName': 'Jane', 'sn': 'Smith'}
        
        result = self.backend.update_user_attributes(request, user)
        
        user.refresh_from_db()
        assert user.name == "Jane Smith"
        assert result is None  # Method doesn't return anything

    def test_authenticate_full_flow_new_user(self):
        """Test complete authentication flow for new user"""
        org = OrganizationFactory(domain="example.edu")
        request = self.factory.get('/')
        request.META = {
            'mail': 'newuser@example.edu',
            'eppn': 'newuser@example.edu',
            'givenName': 'Alice',
            'sn': 'Johnson',
            'eduPersonScopedAffiliation': 'faculty@example.edu',
            'schacHomeOrganization': org.code
        }
        
        # Ensure user doesn't exist
        assert not User.objects.filter(username="newuser").exists()
        
        user = self.backend.authenticate(request, "newuser")
        
        assert user is not None
        assert user.username == "newuser"
        assert user.email == "newuser@example.edu"
        assert user.name == "Alice Johnson"
        assert user.shibboleth_eppn == "newuser@example.edu"
        assert user.auth_source == "shibboleth"
        assert user.is_federated_user is True
        assert user.role == "data_admin"  # faculty affiliation
        assert user.shibboleth_affiliation == "faculty@example.edu"
        assert user.last_shibboleth_login is not None
        assert not user.has_usable_password()

    def test_find_existing_user_priority_order(self):
        """Test that user finding follows correct priority order"""
        # Create users with different identifiers
        user_by_eppn = ShibbolethUserFactory(
            username="old_username",
            shibboleth_eppn="user@example.edu"
        )
        user_by_username = UserFactory(username="user123", email="different@example.com")
        user_by_email = UserFactory(email="user@example.edu", username="another_user")
        
        request = self.factory.get('/')
        request.META = {'mail': 'user@example.edu', 'eppn': 'user@example.edu'}
        
        # Should find by EPPN first (highest priority)
        found_user = self.backend._find_existing_user("user123", "user@example.edu", request)
        assert found_user == user_by_eppn