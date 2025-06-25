# Users Module - Arkumu User Role Access Control

This module provides user authentication, organization management, and a sophisticated permission system that implements the Arkumu user roles for the platform.

> **📚 Related Documentation:** See [`../metadata/README.md`](../metadata/README.md) for detailed implementation of Resource permissions, Guardian integration, and object-level permission methods.

## Table of Contents

- [Overview](#overview)
- [Permission System Architecture](#permission-system-architecture)
- [Models](#models)
- [Arkumu User Roles](#arkumu-user-roles)
- [Public Catalog Access](#public-catalog-access)
- [Usage Examples](#usage-examples)
- [Migration Guide](#migration-guide)

## Overview

The users module implements a **three-layer permission system** that combines:

1. **Django Model Permissions**: Site-wide capabilities *(this module)*
2. **Django Guardian**: Object-level permissions *(metadata module)*
3. **Business Logic Methods**: Arkumu user role rules *(metadata module)*

This module provides the **"who"** (users, organizations, roles) while the metadata module provides the **"what"** (resources and their permissions).

This architecture ensures compliance with the detailed Arkumu user roles while providing:
- **Public catalog access** for anonymous users
- **Cross-university collaboration** for public resources
- **Organization-level isolation** for private data
- **Role-based automatic permissions** via signals

## Permission System Architecture

### Simple Explanation

Think of the permission system like a **three-gate security system**:

```
🚪 Gate 1: Model Permissions
   ↓ "Can this user type access the admin area at all?"
   
🚪 Gate 2: Guardian Permissions  
   ↓ "Does this specific user have rights to this specific resource?"
   
🚪 Gate 3: Business Logic
   ↓ "Are the current conditions right for access? (e.g., not externally linked)"
```

### Layer Details

| Layer | Purpose | Example |
|-------|---------|---------|
| **Django Model Permissions** | Site-wide access rights | `can_access_admin_backend`, `can_approve_public_access` |
| **Guardian Object Permissions** | Per-resource access rights | `view_resource`, `change_resource`, `delete_resource` |
| **Business Logic Methods** | Specification compliance | External linking checks, public access rules |

### Why Three Layers?

**Problem:** Guardian alone can't handle all the Arkumu user role requirements:
- ❌ Anonymous users viewing public catalog
- ❌ Dynamic restrictions (external linking)
- ❌ Cross-university public access

**Solution:** Layer them for complete coverage:
```python
def can_user_edit(self, user):
    # Layer 1: Basic authentication
    if not user or not user.is_authenticated:
        return False
    
    # Layer 2: Arkumu user role restrictions
    if self.is_externally_linked:  # From Arkumu user roles
        return False
    
    # Layer 3: Guardian object-level permissions
    return user.has_perm('change_resource', self)
```

## Models

### Organization Model

```python
class Organization(models.Model):
    name = models.CharField(max_length=255)                    # "Folkwang Universität"
    code = models.CharField(max_length=50, unique=True)        # "FUK" 
    domain = models.CharField(max_length=255, blank=True)      # "folkwang-uni.de"
    shibboleth_entity_id = models.CharField(...)               # For federation
    is_active = models.BooleanField(default=True)
```

### Enhanced User Model

```python
class User(AbstractUser):
    # Organization and Role (Arkumu user roles)
    organization = models.ForeignKey(Organization, ...)
    role = models.CharField(choices=ROLES, default='researcher')
    
    # Shibboleth Integration (for universities)
    auth_source = models.CharField(choices=AUTH_SOURCES, default='local')
    shibboleth_eppn = models.CharField(...)  # University login ID
```

### Resource Model with Public Access

```python
class Resource(UUIDModel):  # Inherits created_by, updated_by from UUIDModel
    # Basic resource info
    uri = models.URLField(...)
    source = models.CharField(...)  # Organization code like "FUK"
    
    # Public access control (NEW)
    public_access_level = models.CharField(choices=[
        ('private', 'Organization only'),
        ('restricted', 'Authenticated users only'), 
        ('public', 'Public catalog allowed')
    ], default='private')
    
    is_public_approved = models.BooleanField(default=False)
    public_approved_by = models.ForeignKey(User, ...)
    
    # Cross-organization tracking
    is_externally_linked = models.BooleanField(default=False)
```

## Arkumu User Roles

### Role Definitions

| Arkumu Role Term | Role Code | Description | What They Can Do |
|-------------|-----------|-------------|------------------|
| **Anonymous User** | N/A | Unauthenticated visitor | View PUBLIC + approved resources (public catalog) |
| **Einfache angemeldete Benutzer:in** | `researcher` | Basic authenticated user | Create own resources, view public/restricted + cross-university data |
| **Mediendokumentar:in** | `archivist` | Media documentarian | Everything researchers can do + manage all org resources |
| **Manager:in** | `manager` | Manager | Everything archivists can do + approve for public transfer |
| **Supermanager:in** | `super_manager` | Super manager | Everything managers can do + manage org users |
| **Technische Administrator:innen** | `system_admin` | Technical admin | Everything across all organizations |

### Automatic Permission Assignment

When a resource is created, **Guardian signals automatically assign permissions** based on Arkumu user roles:

```python
# Creator gets full permissions (Arkumu role: "Eigene Projekte bearbeiten und löschen")
assign_perm('view_resource', creator, resource)
assign_perm('change_resource', creator, resource) 
assign_perm('delete_resource', creator, resource)

# Organization archivists/managers get edit permissions
for archivist in org.users.filter(role__in=['archivist', 'manager']):
    assign_perm('view_resource', archivist, resource)
    assign_perm('change_resource', archivist, resource)

# Organization researchers get view permissions only
for researcher in org.users.filter(role='researcher'):
    assign_perm('view_resource', researcher, resource)
```

### External Linking Protection

**Arkumu User Role Rule:** "Cannot edit/delete if used by other organizations"

```python
# When someone from another university links to a resource:
resource.is_externally_linked = True
resource.save()

# Now edit attempts are blocked by business logic:
def can_user_edit(self, user):
    if self.is_externally_linked:  # Arkumu role protection
        return False
    return user.has_perm('change_resource', self)  # Guardian check
```

## Public Catalog Access

### For Anonymous Users

**Goal:** Allow anyone to browse approved public resources without login - no permissions required!

```python
# ResourceManager automatically handles anonymous access
def for_user(self, user):
    if not user.is_authenticated:
        # Anonymous users automatically see public, approved resources
        return self.filter(
            public_access_level=PublicAccessLevel.PUBLIC,
            is_public_approved=True
        )
    # ... rest of method for authenticated users

# Business logic also handles anonymous users
def can_user_view(self, user):
    # Public access - anyone can view approved public resources
    if self.is_publicly_accessible:  # public_access_level='public' + is_public_approved=True
        return True
    
    # Anonymous users can't see anything else
    if not user or not user.is_authenticated:
        return False
    
    # Continue with Guardian checks for authenticated users...
```

### Cross-University Access

**Arkumu User Roles:** "Users can see and link with public information from other universities"

```python
def can_user_view(self, user):
    # ... (public access check first)
    
    # Cross-university public viewing (Arkumu user role requirement)
    if (self.public_access_level == PublicAccessLevel.PUBLIC and 
        user.has_role_permission('can_view_cross_university_public')):
        return True
    
    # Continue with other checks...
```

### Public Approval Workflow

Only managers and above can approve resources for public catalog:

```python
# In views or admin
if user.has_role_permission('can_approve_public_access'):
    resource.public_access_level = 'public'
    resource.is_public_approved = True
    resource.public_approved_by = user
    resource.save()
```

## Usage Examples

### User Permission Mixins

The users module provides **USER-level** permission mixins:

```python
from arkumu.users.mixins import (
    RoleRequiredMixin, AdminRequiredMixin, ManagerRequiredMixin,
    role_required, admin_required
)

# Class-based views
class UserManagementView(ManagerRequiredMixin, ListView):
    model = User  # Only managers and above can access

class SystemSettingsView(AdminRequiredMixin, UpdateView):
    model = Settings  # Requires admin backend permission

class ArchiveImportView(ArchivistRequiredMixin, CreateView):
    model = ImportJob  # Archivists and above

# Function-based views  
@admin_required
def backup_database(request):
    # Only users with admin backend permission

@role_required(roles=['manager', 'super_manager'])
def approve_users(request):
    # Only managers and super managers

@role_required(permissions=['can_approve_public_access'])
def approve_for_catalog(request):
    # Users with specific permission
```

### Combining USER + RESOURCE Mixins

Combine USER mixins from this module with RESOURCE mixins from metadata module:

```python
from arkumu.users.mixins import AdminRequiredMixin, ManagerRequiredMixin
from arkumu.metadata.mixins import PublicCatalogMixin, OrganizationResourceMixin

# Public catalog view (allows anonymous users)
class PublicResourceListView(PublicCatalogMixin, ListView):
    model = Resource
    template_name = 'catalog/public.html'
    # RESOURCE: Automatically shows only publicly approved resources

# Admin resource management (USER permission + RESOURCE filtering)
class AdminResourceView(AdminRequiredMixin, OrganizationResourceMixin, UpdateView):
    model = Resource
    # USER: Requires admin backend permission
    # RESOURCE: Filters to user's organization

# Manager user management (USER role check only)
class UserManagementView(ManagerRequiredMixin, ListView):
    model = User
    # USER: Only managers and above can access user management
```

> **📚 See [`../metadata/README.md#usage-examples`](../metadata/README.md#usage-examples) for more RESOURCE mixin examples**

### Permission Checking

```python
# Check if user can view specific resource
if resource.can_user_view(request.user):
    # Show resource details
    
# Check if user can edit specific resource  
if resource.can_user_edit(request.user):
    # Show edit form
    
# Check role-based permissions for approval
if request.user.has_role_permission('can_approve_public_access'):
    # Show approval interface
    
# Note: Public catalog access is automatic for everyone
# - Anonymous users get PUBLIC + approved resources
# - Authenticated users get PUBLIC + RESTRICTED + approved + org resources
```

### Queryset Filtering

```python
from arkumu.metadata.utils import get_user_accessible_resources, get_public_catalog_queryset

# Get all resources user can access
resources = get_user_accessible_resources(request.user)

# Get only public catalog resources
public_resources = get_public_catalog_queryset()

# In views with mixins (automatic filtering)
class MyResourceView(PublicCatalogMixin, ListView):
    model = Resource
    # Queryset automatically filtered based on user permissions
```

### Public Approval

```python
from arkumu.metadata.utils import approve_resource_for_public_catalog

# Approve single resource
if user.has_role_permission('can_approve_public_access'):
    approve_resource_for_public_catalog(resource, user)

# Bulk approve resources
from arkumu.metadata.utils import bulk_approve_resources_for_catalog
approved_count = bulk_approve_resources_for_catalog(resource_ids, user)
```

## Migration Guide

### 1. Run Database Migration

```bash
python manage.py makemigrations users
python manage.py makemigrations metadata  
python manage.py migrate
```

### 2. Create Organizations

```python
from arkumu.users.models import Organization

# Create organizations for existing org codes
Organization.objects.create(name="Folkwang Universität", code="FUK")
Organization.objects.create(name="Kunsthochschule für Medien", code="KHM") 
Organization.objects.create(name="Robert Schumann Hochschule", code="RSH")
```

### 3. Assign Users to Organizations

```python
# Update existing users
fuk_org = Organization.objects.get(code="FUK")
User.objects.filter(username__contains='fuk').update(
    organization=fuk_org,
    role='researcher'  # Default role
)
```

### 4. Update Views Gradually

```python
# Before
if request.user.is_authenticated:
    resources = Resource.objects.all()

# After  
resources = get_user_accessible_resources(request.user)
```

## Key Benefits

### ✅ **Arkumu User Role Compliant**
- Implements all role-based access rules
- Handles external linking restrictions
- Supports cross-university collaboration

### ✅ **Public Catalog Ready**
- Anonymous users can browse approved resources automatically
- No permissions required for public catalog access
- Approval workflow for managers
- Public/private/restricted access control

### ✅ **Developer Friendly**
- Simple permission checking methods
- Reusable view mixins
- Automatic permission assignment via signals

### ✅ **Secure by Default**
- Resources are private by default
- Multiple permission layers
- Audit trail for public approvals

### ✅ **University Ready**
- Shibboleth federation support
- Organization-based isolation
- Role-based access control

---

**Summary:** This system combines Django Guardian's object-level permissions with business logic methods to create a flexible, specification-compliant permission system that handles everything from anonymous public access to complex cross-university collaboration rules.