"""
Base Coordinator Mixin

Provides shared functionality for all coordinator mixins including:
- Organization management and session handling
- Standardized session key generation
- Common state management patterns

This base class eliminates code duplication between CSV mapping and ingest coordinators
while maintaining clean separation of their specific responsibilities.
"""

import logging
from arkumu.users.models import Organization
from django.middleware.csrf import get_token

logger = logging.getLogger(__name__)


class BaseCoordinatorMixin:
    """
    Base coordinator mixin for shared session and organization management.
    
    This mixin provides:
    - Centralized organization state management
    - Standardized session key generation with prefixes
    - Base organization change handling
    - Common template context preparation
    
    Subclasses should implement their own specific state management
    while leveraging these shared utilities.
    """
    
    # Subclasses should override this to provide their own prefix
    SESSION_PREFIX = 'base'
    
    def get_session_key(self, base_key, organization_id=None, include_prefix=True):
        """
        Generate standardized session key with optional organization ID and prefix.
        
        This ensures consistent session key patterns across all coordinators:
        - With org: 'csv_mapping_workspace_columns_{org_id}'
        - Without org: 'csv_mapping_current_organization'
        - No prefix: 'workspace_columns_{org_id}'
        
        Args:
            base_key (str): Base key name (e.g., 'workspace_columns', 'selected_files')
            organization_id (str, optional): Organization ID to append
            include_prefix (bool): Whether to include the SESSION_PREFIX
            
        Returns:
            str: Standardized session key
        """
        if include_prefix:
            key = f"{self.SESSION_PREFIX}_{base_key}"
        else:
            key = base_key
            
        if organization_id:
            key = f"{key}_{organization_id}"
            
        return key
    
    def get_current_organization(self, request):
        """
        Get the currently selected organization from session.
        
        Args:
            request: Django request object
            
        Returns:
            dict: Organization data with keys: id, code, name
            None: If no organization is selected
        """
        session_key = self.get_session_key('current_organization')
        return request.session.get(session_key)
    
    def set_current_organization(self, request, organization_id):
        """
        Set the current organization in session.
        
        Args:
            request: Django request object
            organization_id: Organization ID (can be numeric ID or code string)
            
        Returns:
            dict: Organization data that was set
            None: If organization not found
        """
        try:
            # Try to parse as numeric ID first
            if str(organization_id).isdigit():
                organization = Organization.objects.get(id=int(organization_id))
            else:
                # Treat as organization code
                organization = Organization.objects.get(code=organization_id)
            
            org_data = {
                'id': organization.id,
                'code': organization.code,
                'name': organization.name
            }
            
            session_key = self.get_session_key('current_organization')
            request.session[session_key] = org_data
            request.session.modified = True
            
            logger.info(f"BASE_COORDINATOR: Set current organization to {org_data['name']} (code: {org_data['code']}, id: {org_data['id']}) with key: {session_key}")
            return org_data
            
        except (Organization.DoesNotExist, ValueError) as e:
            logger.warning(f"BASE_COORDINATOR: Organization '{organization_id}' not found: {e}")
            return None
    
    def clear_current_organization(self, request):
        """
        Clear the current organization from session.
        
        Args:
            request: Django request object
        """
        session_key = self.get_session_key('current_organization')
        if session_key in request.session:
            del request.session[session_key]
            request.session.modified = True
            logger.info(f"BASE_COORDINATOR: Cleared current organization from key: {session_key}")
    
    def get_organization_context(self, request):
        """
        Get organization context for templates.
        
        This provides a standardized organization context that all coordinators
        can use for template rendering, ensuring consistency across interfaces.
        
        Args:
            request: Django request object
            
        Returns:
            dict: Context with organization_id, organization_code, etc.
        """
        current_org = self.get_current_organization(request)
        if current_org:
            return {
                'organization_id': current_org['code'],  # Use code for mapping compatibility
                'organization_code': current_org['code'],
                'organization_name': current_org['name'],
                'organization_numeric_id': current_org['id'],
                'has_organization': True
            }
        else:
            return {
                'organization_id': None,
                'organization_code': None,
                'organization_name': None,
                'organization_numeric_id': None,
                'has_organization': False
            }
    
    def handle_organization_change(self, request, new_organization_id):
        """
        Handle organization change with proper state cleanup.
        
        Base implementation sets the new organization. Subclasses should
        override this to add their own state cleanup logic.
        
        Args:
            request: Django request object
            new_organization_id: New organization ID
            
        Returns:
            dict: New organization data
        """
        logger.info(f"BASE_COORDINATOR: Handling organization change to {new_organization_id}")
        
        # Set new organization
        org_data = self.set_current_organization(request, new_organization_id)
        
        # Also store this organization for cross-view persistence (if OrganizationMixin is available)
        if hasattr(self, 'set_last_selected_organization'):
            self.set_last_selected_organization(request, new_organization_id)
        
        return org_data
    
    def get_base_template_context(self, request, additional_context=None):
        """
        Get base template context that all coordinators can use.
        
        This provides common context items like organization info, CSRF token,
        and any additional context passed in.
        
        Args:
            request: Django request object
            additional_context (dict, optional): Additional context to merge
            
        Returns:
            dict: Base template context
        """
        context = {
            **self.get_organization_context(request),
            'csrf_token': get_token(request),
        }
        
        if additional_context:
            context.update(additional_context)
            
        return context
    
    def validate_organization_required(self, request):
        """
        Validate that an organization is currently selected.
        
        Args:
            request: Django request object
            
        Returns:
            tuple: (is_valid, error_message, organization_data)
        """
        organization = self.get_current_organization(request)
        if not organization:
            return False, "No organization selected", None
        
        return True, None, organization
    
    def clear_organization_specific_state(self, request, organization_id):
        """
        Clear all session state specific to an organization.
        
        Base implementation does nothing. Subclasses should override
        to clear their specific organization-related session data.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID to clear state for
        """
        logger.info(f"BASE_COORDINATOR: Clearing organization-specific state for {organization_id}")
        # Subclasses should implement specific state clearing
        pass
    
    def get_coordinator_debug_info(self, request):
        """
        Get debug information about the current coordinator state.
        
        Useful for troubleshooting session issues and state management.
        
        Args:
            request: Django request object
            
        Returns:
            dict: Debug information about current state
        """
        current_org = self.get_current_organization(request)
        
        # Get all session keys that match our prefix
        prefix = f"{self.SESSION_PREFIX}_"
        coordinator_sessions = {
            key: value for key, value in request.session.items()
            if key.startswith(prefix)
        }
        
        return {
            'coordinator_type': self.__class__.__name__,
            'session_prefix': self.SESSION_PREFIX,
            'current_organization': current_org,
            'coordinator_sessions': coordinator_sessions,
            'total_session_keys': len(request.session.keys()),
            'coordinator_session_count': len(coordinator_sessions)
        }