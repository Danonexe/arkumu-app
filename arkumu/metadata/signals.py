from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(post_save, sender='metadata.Resource')
def assign_resource_permissions(sender, instance, created, **kwargs):
    """
    Automatically assign Guardian permissions when a Resource is created.
    Implements the German specification rules through object-level permissions.
    """
    # Only handle Resource creation
    if not created or not instance.organization:
        return
    
    # 1. Creator always gets full permissions (Specification: "Eigene Projekte sehen, bearbeiten und löschen")
    if instance.created_by:
        assign_perm('view_resource', instance.created_by, instance)
        assign_perm('change_resource', instance.created_by, instance)  
        assign_perm('delete_resource', instance.created_by, instance)
        assign_perm('share_resource', instance.created_by, instance)
    
    # 2. Organization-level permissions based on roles (German specification)
    org_users = User.objects.filter(organization=instance.organization)
    
    for user in org_users:
        if user == instance.created_by:
            continue  # Already handled above
        
        # Mediendokumentar:in can view/edit/delete all organization resources
        # Manager:in can view/edit/delete all organization resources  
        if user.role in ['archivist', 'manager', 'super_manager']:
            assign_perm('view_resource', user, instance)
            assign_perm('change_resource', user, instance)
            assign_perm('delete_resource', user, instance)
        
        # Einfache angemeldete Benutzer:in can view organization resources
        # (Specification: "Projekte von anderen Benutzer:innen...sehen")
        elif user.role == 'researcher':
            assign_perm('view_resource', user, instance)
    
    # 3. System admins get all permissions everywhere
    # (Specification: "Aus technischen Gründen: Alles, auch über Hochschulgrenzen hinweg")
    system_admins = User.objects.filter(role='system_admin')
    for admin in system_admins:
        assign_perm('view_resource', admin, instance)
        assign_perm('change_resource', admin, instance)
        assign_perm('delete_resource', admin, instance)
        assign_perm('share_resource', admin, instance)


def handle_role_change(user):
    """Handle permission updates when a user's role changes."""
    from guardian.shortcuts import get_objects_for_user
    from arkumu.metadata.models.base_models import OwnedModel
    
    # Get all models that inherit from OwnedModel
    # This would need to be populated with your actual models
    owned_models = []  # [Project, Event, Actor, Equipment, etc.]
    
    for model_class in owned_models:
        model_name = model_class._meta.model_name
        
        # Get objects in user's organization
        org_objects = model_class.objects.filter(organization=user.organization)
        
        for obj in org_objects:
            # Remove existing permissions
            remove_perm(f'view_{model_name}', user, obj)
            remove_perm(f'change_{model_name}', user, obj)
            remove_perm(f'delete_{model_name}', user, obj)
            
            # Skip if user is the creator (they always keep permissions)
            if obj.created_by == user:
                assign_perm(f'view_{model_name}', user, obj)
                assign_perm(f'change_{model_name}', user, obj)
                assign_perm(f'delete_{model_name}', user, obj)
                assign_perm(f'share_{model_name}', user, obj)
                continue
            
            # Reassign based on new role
            if user.role in ['archivist', 'manager']:
                assign_perm(f'view_{model_name}', user, obj)
                assign_perm(f'change_{model_name}', user, obj)
                assign_perm(f'delete_{model_name}', user, obj)
            elif user.role == 'researcher':
                assign_perm(f'view_{model_name}', user, obj)


@receiver(post_save, sender=User)
def handle_user_role_change(sender, instance, created, **kwargs):
    """Handle user role changes."""
    if not created and 'role' in (kwargs.get('update_fields') or []):
        handle_role_change(instance)


def check_external_linkage(instance):
    """
    Check if an object is being referenced by users from other organizations.
    This should be called when someone from another org links to this object.
    """
    from guardian.shortcuts import get_users_with_perms
    
    users_with_perms = get_users_with_perms(instance)
    external_users = users_with_perms.exclude(organization=instance.organization)
    
    if external_users.exists():
        instance.is_externally_linked = True
        instance.save(update_fields=['is_externally_linked'])


def share_object_with_user(obj, target_user, sharing_user, permission_level='view'):
    """
    Handle sharing an object with another user.
    Implements collaboration rules from the specification.
    """
    model_name = obj._meta.model_name
    
    # Check if sharing user has permission to share
    if not sharing_user.has_perm(f'share_{model_name}', obj):
        raise PermissionError("User does not have permission to share this object")
    
    # Assign permissions based on level
    assign_perm(f'view_{model_name}', target_user, obj)
    
    if permission_level in ['edit', 'change']:
        assign_perm(f'change_{model_name}', target_user, obj)
    
    # Mark as externally linked if sharing across organizations
    if target_user.organization != obj.organization:
        check_external_linkage(obj) 