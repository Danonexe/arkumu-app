from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Organization(models.Model):
    """Organization model for multi-tenant support"""
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)  # For Shibboleth mapping
    domain = models.CharField(max_length=255, blank=True)  # Email domain
    shibboleth_entity_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['domain']),
        ]
    
    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Enhanced user model with Shibboleth support and role-based access.
    Uses Django's built-in permissions for simpler organization-based access control.
    """
    
    ROLES = [
        ('researcher', _('Researcher')),  # Einfache angemeldete Benutzer:in
        ('archivist', _('Media Documentarian')),  # Mediendokumentar:in
        ('manager', _('Manager')),  # Manager:in
        ('super_manager', _('Super Manager')),  # Supermanager:in
        ('system_admin', _('System Administrator')),  # Technische Administrator:innen
    ]
    
    AUTH_SOURCES = [
        ('local', _('Local Authentication')),
        ('shibboleth', _('Shibboleth Federation')),
    ]

    # First and last name do not cover name patterns around the globe
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    
    # Organization and role
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='users'
    )
    role = models.CharField(
        max_length=20, 
        choices=ROLES, 
        default='researcher'
    )
    
    # Shibboleth integration fields
    auth_source = models.CharField(
        max_length=20, 
        choices=AUTH_SOURCES, 
        default='local'
    )
    shibboleth_eppn = models.CharField(
        max_length=255, 
        blank=True, 
        unique=True, 
        null=True,
        help_text="eduPersonPrincipalName from Shibboleth"
    )
    shibboleth_persistent_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True
    )
    shibboleth_affiliation = models.CharField(
        max_length=255, 
        blank=True,
        help_text="eduPersonScopedAffiliation from Shibboleth"
    )
    
    # Metadata
    last_shibboleth_login = models.DateTimeField(null=True, blank=True)
    is_federated_user = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['shibboleth_eppn']),
            models.Index(fields=['organization', 'role']),
            models.Index(fields=['auth_source']),
        ]
        permissions = [
            # Global application permissions (not object-specific)
            ('can_access_admin_backend', 'Can access admin backend'),
            ('can_import_universal', 'Can import via universal importer'), 
            ('can_manage_metadata', 'Can manage global metadata'),
            ('can_reset_database', 'Can reset database'),
            ('can_manage_org_users', 'Can manage organization users'),
            ('can_transfer_to_public', 'Can transfer data to public'),
            # Public catalog permissions (site-wide)
            # Note: Public catalog is accessible to everyone, including anonymous users
            ('can_approve_public_access', 'Can approve resources for public catalog display'),
            # Cross-university permissions (site-wide, from specification)
            ('can_view_cross_university_public', 'Can view public information from other universities'),
            ('can_link_cross_university', 'Can link own resources with public resources from other universities'),
        ]

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view."""
        return reverse("users:detail", kwargs={"username": self.username})
    
    def get_display_name(self):
        """Get user's display name."""
        return self.name or self.username
    
    @property
    def organization_code(self):
        """Get the organization code for this user."""
        return self.organization.code if self.organization else None
    
    def can_access_organization_data(self, source_code=None):
        """Check if user can access data from a specific organization source."""
        if not self.organization:
            return False
        
        # System admins can access all data
        if self.role == 'system_admin':
            return True
            
        # Users can only access their own organization's data
        if source_code:
            return self.organization.code == source_code
        
        return True  # Can access own org data by default
    
    def has_role_permission(self, permission):
        """Check if user's role grants a specific permission."""
        role_permissions = {
            # Einfache angemeldete Benutzer:in - Access to create resources, see cross-university public data
            'researcher': [
                # Note: Public catalog access is automatic for all authenticated users
                'can_access_admin_backend',        # Need backend access to create resources
                'can_view_cross_university_public', # See public info from other universities
                'can_link_cross_university'        # Link own projects with public resources from other universities
            ],
            # Mediendokumentar:in - Everything researchers can do + manage metadata
            'archivist': [
                # Note: Public catalog access is automatic for all authenticated users
                'can_access_admin_backend', 
                'can_view_cross_university_public',
                'can_link_cross_university',
                'can_manage_metadata',             # Create roles, event types, etc.
            ],
            # Manager:in - Everything archivists can do + public transfer rights
            'manager': [
                # Note: Public catalog access is automatic for all authenticated users
                'can_access_admin_backend', 
                'can_view_cross_university_public',
                'can_link_cross_university',
                'can_manage_metadata',
                'can_transfer_to_public',          # Transfer university projects to public website
                'can_approve_public_access',       # Approve digital objects for public sharing
                'can_import_universal'             # Import via universal importer
            ],
            # Supermanager:in - Everything managers can do + user management
            'super_manager': [
                # Note: Public catalog access is automatic for all authenticated users
                'can_access_admin_backend',
                'can_view_cross_university_public',
                'can_link_cross_university',
                'can_manage_metadata',
                'can_transfer_to_public', 
                'can_approve_public_access',
                'can_import_universal',
                'can_manage_org_users'             # Create/delete users, promote/demote roles within university
            ],
            # Technische Administrator:innen - Everything across all universities
            'system_admin': [
                # Note: Public catalog access is automatic for all authenticated users
                'can_access_admin_backend', 
                'can_view_cross_university_public',
                'can_link_cross_university',
                'can_manage_metadata',
                'can_transfer_to_public', 
                'can_approve_public_access',
                'can_import_universal',
                'can_manage_org_users',
                'can_reset_database',              # Technical operations
            ],
        }
        
        return permission in role_permissions.get(self.role, [])
        
    # Methods for backward compatibility with tests
    def has_role(self, role):
        """Check if user has a specific role."""
        return self.role == role
        
    def has_any_role(self, roles):
        """Check if user has any of the specified roles."""
        return self.role in roles
        
    def can_access_organization(self, organization):
        """Check if user can access data from a specific organization."""
        # System admins can access all organizations
        if self.role == 'system_admin':
            return True
            
        # Users can only access their own organization
        return self.organization == organization
        
    def can_edit_mappings(self):
        """Check if user can edit mappings."""
        return self.role in ['data_admin', 'org_admin', 'system_admin']
        
    def can_import_data(self):
        """Check if user can import data."""
        return self.role in ['archivist', 'data_admin', 'org_admin', 'system_admin']
        
    def can_reset_database(self):
        """Check if user can reset database."""
        return self.role == 'system_admin'
