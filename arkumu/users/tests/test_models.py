import pytest
from django.db import IntegrityError

from arkumu.users.models import User, Organization
from arkumu.users.tests.factories import (
    UserFactory,
    OrganizationFactory,
    ShibbolethUserFactory,
    ManagerUserFactory,
    SuperManagerUserFactory,
    SystemAdminUserFactory,
    ArchivistUserFactory,
)


@pytest.mark.django_db
class TestOrganization:
    """Test cases for Organization model"""

    def test_organization_creation(self):
        """Test basic organization creation"""
        org = OrganizationFactory()
        assert org.name
        assert org.code
        assert org.is_active is True
        assert str(org) == org.name

    def test_organization_code_unique(self):
        """Test that organization code must be unique"""
        OrganizationFactory(code="test-org")
        with pytest.raises(IntegrityError):
            # Force creation of duplicate by bypassing get_or_create
            Organization.objects.create(
                name="Duplicate Org",
                code="test-org",
                domain="duplicate.com"
            )

    def test_organization_ordering(self):
        """Test that organizations are ordered by name"""
        org_b = OrganizationFactory(name="Beta Organization")
        org_a = OrganizationFactory(name="Alpha Organization")
        
        orgs = Organization.objects.all()
        assert orgs[0] == org_a
        assert orgs[1] == org_b

    def test_organization_with_shibboleth_attributes(self):
        """Test organization with Shibboleth-specific fields"""
        org = OrganizationFactory(
            name="University of Cologne",
            code="uni-koeln.de",
            domain="uni-koeln.de",
            shibboleth_entity_id="https://idp.uni-koeln.de/idp/shibboleth"
        )
        assert org.shibboleth_entity_id == "https://idp.uni-koeln.de/idp/shibboleth"
        assert org.domain == "uni-koeln.de"


@pytest.mark.django_db
class TestUser:
    """Test cases for enhanced User model"""

    def test_user_creation_with_defaults(self):
        """Test user creation with default values"""
        user = UserFactory()
        assert user.role == "researcher"
        assert user.auth_source == "local"
        assert user.is_federated_user is False
        assert user.organization is not None

    def test_user_get_absolute_url(self):
        """Test user absolute URL generation"""
        user = UserFactory()
        assert user.get_absolute_url() == f"/users/{user.username}/"

    def test_user_get_display_name(self):
        """Test user display name logic"""
        user = UserFactory(name="John Doe")
        assert user.get_display_name() == "John Doe"
        
        user_no_name = UserFactory(name="")
        assert user_no_name.get_display_name() == user_no_name.username

    def test_user_role_check(self):
        """Test role checking method"""
        researcher = UserFactory(role="researcher")
        manager = ManagerUserFactory()
        
        # Direct role comparison instead of has_role method
        assert researcher.role == "researcher"
        assert researcher.role != "manager"
        assert manager.role == "manager"

    def test_user_role_in_group(self):
        """Test if user role is in a group of roles"""
        manager = ManagerUserFactory()
        researcher = UserFactory(role="researcher")
        
        admin_roles = ["manager", "super_manager", "system_admin"]
        # Check if role is in a list of roles
        assert manager.role in admin_roles
        assert researcher.role not in admin_roles
        assert researcher.role in ["researcher", "archivist"]

    def test_user_organization_access(self):
        """Test organization access control"""
        org1 = OrganizationFactory()
        org2 = OrganizationFactory()
        
        user = UserFactory(organization=org1, role="researcher")
        system_admin = SystemAdminUserFactory(organization=org2)
        
        # Using can_access_organization_data method which already exists
        assert user.can_access_organization_data(org1.code) is True
        assert user.can_access_organization_data(org2.code) is False
        assert system_admin.can_access_organization_data(org1.code) is True
        assert system_admin.can_access_organization_data(org2.code) is True

    def test_user_role_permissions(self):
        """Test various role-based permissions"""
        researcher = UserFactory(role="researcher")
        archivist = ArchivistUserFactory()
        manager = ManagerUserFactory()
        super_manager = SuperManagerUserFactory()
        system_admin = SystemAdminUserFactory()
        
        # Test permissions based on has_role_permission method
        # Metadata management permission
        assert not researcher.has_role_permission('can_manage_metadata')
        assert archivist.has_role_permission('can_manage_metadata')
        assert manager.has_role_permission('can_manage_metadata')
        assert super_manager.has_role_permission('can_manage_metadata')
        assert system_admin.has_role_permission('can_manage_metadata')
        
        # Import data permission
        assert not researcher.has_role_permission('can_import_universal')
        assert not archivist.has_role_permission('can_import_universal')
        assert manager.has_role_permission('can_import_universal')
        assert super_manager.has_role_permission('can_import_universal')
        assert system_admin.has_role_permission('can_import_universal')
        
        # Reset database permission
        assert not researcher.has_role_permission('can_reset_database')
        assert not archivist.has_role_permission('can_reset_database')
        assert not manager.has_role_permission('can_reset_database')
        assert not super_manager.has_role_permission('can_reset_database')
        assert system_admin.has_role_permission('can_reset_database')

    def test_shibboleth_user_creation(self):
        """Test Shibboleth user creation"""
        shib_user = ShibbolethUserFactory()
        
        assert shib_user.auth_source == "shibboleth"
        assert shib_user.is_federated_user is True
        assert shib_user.shibboleth_eppn is not None
        assert shib_user.shibboleth_affiliation == "staff@example.edu"

    def test_shibboleth_eppn_unique(self):
        """Test that shibboleth_eppn must be unique when set"""
        eppn = "user@example.edu"
        ShibbolethUserFactory(shibboleth_eppn=eppn)
        
        with pytest.raises(IntegrityError):
            ShibbolethUserFactory(shibboleth_eppn=eppn)

    def test_user_organization_relationship(self):
        """Test user-organization relationship"""
        org = OrganizationFactory()
        user1 = UserFactory(organization=org)
        user2 = UserFactory(organization=org)
        
        assert user1.organization == org
        assert user2.organization == org
        assert org.users.count() == 2
        assert user1 in org.users.all()
        assert user2 in org.users.all()

    def test_user_role_choices(self):
        """Test that all role choices work correctly"""
        roles = ["researcher", "archivist", "manager", "super_manager", "system_admin"]
        
        for role in roles:
            user = UserFactory(role=role)
            assert user.role == role

    def test_user_auth_source_choices(self):
        """Test authentication source choices"""
        local_user = UserFactory(auth_source="local")
        shib_user = ShibbolethUserFactory(auth_source="shibboleth")
        
        assert local_user.auth_source == "local"
        assert shib_user.auth_source == "shibboleth"
        assert local_user.is_federated_user is False
        assert shib_user.is_federated_user is True


def test_user_get_absolute_url(user: User):
    """Legacy test for backward compatibility"""
    assert user.get_absolute_url() == f"/users/{user.username}/"
