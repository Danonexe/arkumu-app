from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from functools import wraps


class RoleRequiredMixin(UserPassesTestMixin):
    """Mixin to require specific roles for view access."""
    required_roles = []
    required_permissions = []
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        # Check roles
        if self.required_roles and self.request.user.role not in self.required_roles:
            return False
        
        # Check permissions  
        if self.required_permissions:
            for permission in self.required_permissions:
                if not self.request.user.has_role_permission(permission):
                    return False
        
        return True


class AdminRequiredMixin(LoginRequiredMixin):
    """
    Mixin requiring admin backend access.
    This is a USER-level permission check.
    """
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role_permission('can_access_admin_backend'):
            raise PermissionDenied("Administrative access required.")
        return super().dispatch(request, *args, **kwargs)


class PublicApprovalMixin(AdminRequiredMixin):
    """
    Mixin for views that handle public approval workflow.
    Only managers and above can approve resources for public catalog.
    """
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role_permission('can_approve_public_access'):
            raise PermissionDenied("You don't have permission to approve resources for public access.")
        return super().dispatch(request, *args, **kwargs)


class SystemAdminRequiredMixin(LoginRequiredMixin):
    """Mixin requiring system admin role."""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.role != 'system_admin':
            raise PermissionDenied("System administrator access required.")
        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin(LoginRequiredMixin):
    """Mixin requiring manager role or above."""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in ['manager', 'super_manager', 'system_admin']:
            raise PermissionDenied("Manager access required.")
        return super().dispatch(request, *args, **kwargs)


class ArchivistRequiredMixin(LoginRequiredMixin):
    """Mixin requiring archivist role or above."""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in ['archivist', 'manager', 'super_manager', 'system_admin']:
            raise PermissionDenied("Archivist access required.")
        return super().dispatch(request, *args, **kwargs)


# Decorators for function-based views
def role_required(roles=None, permissions=None):
    """Decorator for function-based views requiring specific roles/permissions."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            if roles and request.user.role not in roles:
                raise PermissionDenied(f"Role {request.user.role} not authorized")
            
            if permissions:
                for permission in permissions:
                    if not request.user.has_role_permission(permission):
                        raise PermissionDenied(f"Permission {permission} required")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    """Decorator requiring admin backend access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        if not request.user.has_role_permission('can_access_admin_backend'):
            raise PermissionDenied("Administrative access required")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def manager_required(view_func):
    """Decorator requiring manager role or above."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        if request.user.role not in ['manager', 'super_manager', 'system_admin']:
            raise PermissionDenied("Manager access required")
        
        return view_func(request, *args, **kwargs)
    return wrapper

 