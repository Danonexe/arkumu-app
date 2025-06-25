# Arkumu Metadata Permission System

This directory contains the core metadata models with **integrated three-layer permission management** that implements the Arkumu user roles.

> **📚 Related Documentation:** See [`../users/README.md`](../users/README.md) for the complete permission system overview, user roles, and organization management.

## Quick Overview

This module provides the **"what"** (resources and their permissions) while the users module provides the **"who"** (users, organizations, roles). Together they implement a comprehensive permission system:

**Three-Layer Architecture:**
1. **Django Model Permissions** *(users module)* - Site-wide capabilities  
2. **Django Guardian** *(this module)* - Object-level permissions via signals
3. **Business Logic Methods** *(this module)* - Arkumu user role compliance

## Core Models

### Resource Model (`models/resource.py`)

The central model that represents RDF resources with **public catalog support**:

```python
class Resource(UUIDModel):  # Inherits created_by, updated_by from UUIDModel
    # Core RDF fields
    uri = models.URLField(...)
    resource_type = models.CharField(...)  # IRI, CLASS, PROPERTY, LITERAL  
    value = models.TextField(...)  # For literals
    source = models.CharField(...)  # Organization code like "FUK"

    # Organization & Permission fields  
    organization = models.ForeignKey('users.Organization', ...)
    
    # Public catalog access (NEW - see users/README.md)
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

### Three-Layer Permission Methods

Each resource has permission methods that integrate all three layers:

```python
def can_user_view(self, user):
    """Integrates Guardian + business logic + public access"""
    # Layer 1: Public catalog access (bypasses Guardian for anonymous)
    if self.is_publicly_accessible:  # public + approved
        return True  # ANYONE can view public resources (no permissions needed!)
    
    if not user or not user.is_authenticated:
        return False
    
    # Layer 2: Guardian object-level permissions  
    if user.has_perm('view_resource', self):
        return True
    
    # Layer 3: Cross-university public viewing (Arkumu user roles)
    if (self.public_access_level == 'public' and 
        user.has_role_permission('can_view_cross_university_public')):
        return True
    
    # Authenticated users can view RESTRICTED resources
    if self.public_access_level == 'restricted':
        return True
    
    return False

def can_user_edit(self, user):
    """Guardian permissions + specification restrictions"""
    if not user or not user.is_authenticated:
        return False
    
         # Arkumu user roles: Cannot edit if externally linked
    if self.is_externally_linked:
        return False
    
    # Guardian object-level permission check
    return user.has_perm('change_resource', self)
```

## Guardian Integration (Layer 2)

### Automatic Permission Assignment

Permissions are **automatically assigned via signals** when resources are created (`signals.py`):

```python
@receiver(post_save, sender='metadata.Resource')
def assign_resource_permissions(sender, instance, created, **kwargs):
    """Implements Arkumu user roles through Guardian permissions"""
    
    # Creator gets full permissions (Arkumu role: "Eigene Projekte bearbeiten")
    if instance.created_by:
        assign_perm('view_resource', instance.created_by, instance)
        assign_perm('change_resource', instance.created_by, instance) 
        assign_perm('delete_resource', instance.created_by, instance)

    # Organization users get role-based permissions
    org_users = User.objects.filter(organization=instance.organization)
    for user in org_users:
        if user.role in ['archivist', 'manager', 'super_manager']:
            # Mediendokumentar:in can edit all organization resources
            assign_perm('view_resource', user, instance)
            assign_perm('change_resource', user, instance)
        elif user.role == 'researcher':
            # Einfache Benutzer:in can only view organization resources
            assign_perm('view_resource', user, instance)
    
    # System admins get everything everywhere
    system_admins = User.objects.filter(role='system_admin')
    for admin in system_admins:
        assign_perm('view_resource', admin, instance)
        assign_perm('change_resource', admin, instance)
```

### Guardian Permission Usage

```python
from guardian.shortcuts import get_objects_for_user

# Get all resources user can view (via Guardian)
viewable_resources = get_objects_for_user(
    request.user, 'view_resource', Resource
)

# Check specific Guardian permission
if request.user.has_perm('change_resource', resource):
    # User has Guardian permission, but also check business logic
    if resource.can_user_edit(request.user):  # Includes external linking check
        # Now safe to edit
```

## Arkumu User Role Compliance (Layer 3)

### Role-Based Access Rules

> **📚 See [`../users/README.md#arkumu-user-roles`](../users/README.md#arkumu-user-roles) for complete role definitions**

| Role | Guardian Permissions Assigned | Business Logic Restrictions |
|------|------------------------------|----------------------------|
| **Researcher** | `view_resource` on org resources | Can edit own resources only (if not externally linked) |
| **Archivist** | `view_resource`, `change_resource` on org resources | Cannot edit externally linked resources |
| **Manager** | Same as archivist + can approve public access | Can transfer resources to public catalog |
| **System Admin** | All permissions on all resources | No restrictions |

### External Linking Protection

**Arkumu User Role Rule:** "Cannot edit/delete if used by other organizations"

```python
# When someone from another university links to a resource:
def share_across_organizations(resource, external_user):
    # Mark as externally linked
    resource.is_externally_linked = True
    resource.save()
    
    # Grant Guardian permission
    assign_perm('view_resource', external_user, resource)

# Now edit attempts are blocked by business logic:
resource.can_user_edit(original_creator)  # Returns False due to external linking
```

## Public Catalog Integration (Layer 1)

### Anonymous User Access

Resources can be made publicly accessible for the catalog website - **no permissions required**:

```python
# ResourceManager automatically handles anonymous access
def for_user(self, user):
    """Return resources accessible by the given user."""
    if not user.is_authenticated:
        # Anonymous users automatically see public, approved resources
        return self.filter(
            public_access_level=PublicAccessLevel.PUBLIC,
            is_public_approved=True
        )
    # ... rest of method for authenticated users

# Usage in views - automatic filtering
from arkumu.metadata.utils import get_public_catalog_queryset
public_resources = get_public_catalog_queryset()  # No permissions needed!
```

### Approval Workflow

Only managers and above can approve resources for public display:

```python
from arkumu.metadata.utils import approve_resource_for_public_catalog

# Check role-based permission (Layer 1)
if user.has_role_permission('can_approve_public_access'):
    # Approve for public catalog
    approve_resource_for_public_catalog(resource, user)
```

## View Integration

### Using Permission Mixins

Combine **USER mixins** (from users module) with **RESOURCE mixins** (from this module):

```python
from arkumu.users.mixins import AdminRequiredMixin, ManagerRequiredMixin, PublicApprovalMixin
from arkumu.metadata.mixins import (
    PublicCatalogMixin, OrganizationResourceMixin, 
    EditPermissionMixin, DeletePermissionMixin, BulkActionMixin
)

# Public catalog view (anonymous users allowed)
class PublicResourceListView(PublicCatalogMixin, ListView):
    model = Resource
    # RESOURCE: Automatically filters to publicly approved resources

# Admin resource list (USER permission + RESOURCE filtering)  
class AdminResourceListView(AdminRequiredMixin, OrganizationResourceMixin, ListView):
    model = Resource
    # USER: Requires admin backend access
    # RESOURCE: Filters to organization resources

# Admin resource edit (USER permission + RESOURCE permission + edit checks)
class AdminResourceEditView(AdminRequiredMixin, EditPermissionMixin, UpdateView):
    model = Resource
    # USER: Admin backend required
    # RESOURCE: Edit permission check (includes org filtering + external linking)

# Admin resource delete (USER permission + RESOURCE permission + delete checks)
class AdminResourceDeleteView(AdminRequiredMixin, DeletePermissionMixin, DeleteView):
    model = Resource
    # USER: Admin backend required  
    # RESOURCE: Delete permission check (includes org filtering + external linking)

# Manager approval workflow (USER role + USER permission + RESOURCE actions)
class ResourceApprovalView(PublicApprovalMixin, OrganizationResourceMixin, BulkActionMixin, ListView):
    model = Resource
    # USER: Manager role + public approval permission
    # RESOURCE: Organization filtering + bulk approval actions
```

> **📚 See [`../users/README.md#usage-examples`](../users/README.md#usage-examples) for more USER mixin examples**

### Direct Permission Checking

```python
# Three-layer permission checking
if resource.can_user_view(request.user):
    # Safe to display resource details
    
if resource.can_user_edit(request.user):
    # Safe to show edit form
    
if resource.can_user_delete(request.user):
    # Safe to allow deletion
```

### Queryset Filtering

```python
from arkumu.metadata.utils import get_user_accessible_resources

# Get all resources user can access (integrates all three layers)
resources = get_user_accessible_resources(request.user)
# Returns: own resources + org resources + public cross-university resources

# For organization-specific queries
org_resources = Resource.objects.for_organization('FUK')
```

## Cross-University Collaboration

### Public Resource Sharing

**Arkumu User Roles:** "Users can see and link with public information from other universities"

```python
# FUK user viewing KHM public resource
fuk_user = User.objects.get(organization__code='FUK')
khm_resource = Resource.objects.get(organization__code='KHM', public_access_level='public')

# This works due to cross-university permissions
if khm_resource.can_user_view(fuk_user):  # True for public resources
    # User can see and link with this resource
    if khm_resource.can_user_link_with(fuk_user, my_resource):
        # Create relationship between FUK and KHM resources
```

### Collaboration Tracking

```python
# Check if resource is being used across organizations
if resource.is_externally_linked:
    # Show warning: "This resource is used by other organizations"
    # Disable edit/delete options

# Get collaboration users
collaborators = resource.get_collaboration_users()
external_collaborators = collaborators.exclude(
    organization=resource.organization
)
```

## Migration Guide

### From Simple to Three-Layer System

```python
# 1. Assign organizations to existing resources
for resource in Resource.objects.filter(organization__isnull=True):
    if resource.source:
        try:
            org = Organization.objects.get(code=resource.source)
            resource.organization = org
            resource.save()
            # Guardian permissions will be assigned automatically via signals
        except Organization.DoesNotExist:
            # Handle orphaned resources
            pass

# 2. Approve existing public resources
public_resources = Resource.objects.filter(is_public=True)
for resource in public_resources:
    resource.public_access_level = 'public'
    resource.is_public_approved = True
    # Set public_approved_by to a manager if available
    resource.save()
```

## Performance Considerations

- **Guardian permissions** are stored in separate tables - use `prefetch_related()` 
- **Business logic methods** are simple Python checks - very fast
- **Public catalog queries** use database indexes - efficient filtering
- Use `select_related('organization', 'created_by')` for efficient queries

```python
# Efficient query example
resources = Resource.objects.select_related(
    'organization', 'created_by', 'public_approved_by'
).filter(
    public_access_level='public',
    is_public_approved=True
)
```

## Testing Three-Layer Permissions

```python
# Test all three layers
def test_resource_permissions(self):
    # Layer 1: Public access
    assert resource.can_user_view(None)  # Anonymous user
    
    # Layer 2: Guardian permissions  
    assert user.has_perm('view_resource', resource)
    
    # Layer 3: Business logic
    resource.is_externally_linked = True
    assert not resource.can_user_edit(user)  # Blocked by business logic
```

## Integration with Users Module

This metadata module **requires** the users module for:

- **Organization model** - Resource.organization foreign key
- **User roles** - Permission assignment via signals  
- **Role permissions** - `user.has_role_permission()` method
- **Cross-university rules** - Business logic implementation

> **📚 Complete Setup:** See [`../users/README.md#migration-guide`](../users/README.md#migration-guide) for full system setup instructions.

---

**Summary:** This module provides the object-level permission infrastructure that combines with the users module's role-based system to create comprehensive Arkumu user role compliance with public catalog support.
