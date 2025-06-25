from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from functools import wraps
from .models.resource import Resource, PublicAccessLevel


def public_catalog_required(view_func):
    """
    Decorator to ensure that only resources with public catalog access can be viewed.
    Use this for public catalog/website display views.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Allow public access without authentication for catalog views
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def get_resource_or_403(resource_id, user, require_edit=False):
    """
    Get a resource with proper permission checking.
    
    Args:
        resource_id: The ID of the resource to fetch
        user: The requesting user (can be None for anonymous users)
        require_edit: Whether edit permissions are required
        
    Returns:
        Resource object if user has permissions
        
    Raises:
        PermissionDenied: If user doesn't have required permissions
    """
    resource = get_object_or_404(Resource, id=resource_id)
    
    if require_edit:
        if not resource.can_user_edit(user):
            raise PermissionDenied("You don't have permission to edit this resource.")
    else:
        if not resource.can_user_view(user):
            raise PermissionDenied("You don't have permission to view this resource.")
    
    return resource


def get_public_catalog_queryset():
    """
    Get queryset of resources that are publicly accessible for catalog display.
    """
    return Resource.objects.filter(
        public_access_level=PublicAccessLevel.PUBLIC,
        is_public_approved=True
    )


def get_user_accessible_resources(user):
    """
    Get all resources accessible to a specific user based on new specification.
    """
    if not user or not user.is_authenticated:
        # Anonymous users can only see public catalog resources
        return get_public_catalog_queryset()
    
    # System admins can see everything
    if user.role == 'system_admin':
        return Resource.objects.all()
    
    # Start with fully public resources (accessible to everyone)
    queryset = get_public_catalog_queryset()
    
    # Add cross-university public resources (new requirement)
    if user.has_role_permission('can_view_cross_university_public'):
        cross_university_public = Resource.objects.filter(
            public_access_level=PublicAccessLevel.PUBLIC
        ).exclude(id__in=queryset)  # Avoid duplicates
        queryset = queryset.union(cross_university_public)
    
    # Add restricted resources for authenticated users
    restricted_resources = Resource.objects.filter(
        public_access_level=PublicAccessLevel.RESTRICTED
    )
    queryset = queryset.union(restricted_resources)
    
    # Add user's own resources (regardless of organization)
    own_resources = Resource.objects.filter(created_by=user)
    queryset = queryset.union(own_resources)
    
    # Add private resources from user's organization (if they have org permissions)
    if (user.organization and 
        user.has_role_permission('can_view_org_data')):
        org_private_resources = Resource.objects.filter(
            public_access_level=PublicAccessLevel.PRIVATE,
            source=user.organization.code
        ).exclude(created_by=user)  # Avoid duplicating own resources
        queryset = queryset.union(org_private_resources)
    
    return queryset


def approve_resource_for_public_catalog(resource, approving_user):
    """
    Approve a resource for public catalog display.
    
    Args:
        resource: Resource instance to approve
        approving_user: User performing the approval
        
    Returns:
        bool: True if approval was successful
        
    Raises:
        PermissionDenied: If user doesn't have approval permissions
    """
    if not approving_user.has_role_permission('can_approve_public_access'):
        raise PermissionDenied("You don't have permission to approve resources for public access.")
    
    from django.utils import timezone
    
    resource.is_public_approved = True
    resource.public_approved_at = timezone.now()
    resource.public_approved_by = approving_user
    resource.public_access_level = PublicAccessLevel.PUBLIC
    resource.save()
    
    return True


def bulk_approve_resources_for_catalog(resource_ids, approving_user):
    """
    Bulk approve multiple resources for public catalog display.
    """
    if not approving_user.has_role_permission('can_approve_public_access'):
        raise PermissionDenied("You don't have permission to approve resources for public access.")
    
    from django.utils import timezone
    
    resources = Resource.objects.filter(id__in=resource_ids)
    
    # Only approve resources that the user can access
    accessible_resources = []
    for resource in resources:
        if resource.can_user_edit(approving_user):
            accessible_resources.append(resource)
    
    # Bulk update
    Resource.objects.filter(id__in=[r.id for r in accessible_resources]).update(
        is_public_approved=True,
        public_approved_at=timezone.now(),
        public_approved_by=approving_user,
        public_access_level=PublicAccessLevel.PUBLIC
    )
    
    return len(accessible_resources)


 