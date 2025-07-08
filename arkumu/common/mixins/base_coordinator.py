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
from django.utils import timezone

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
    
    # Shared session keys (no prefix, used across all coordinators)
    SHARED_CURRENT_ORGANIZATION_KEY = 'current_organization'
    SHARED_CURRENT_MAPPING_KEY = 'current_mapping'
    
    def get_session_key(self, base_key, organization_id=None):
        """
        Generate standardized session key with organization ID.
        
        This ensures consistent session key patterns across all coordinators:
        - With org: 'csv_mapping_workspace_columns_123'
        - Without org: 'csv_mapping_selected_mapping'
        
        Args:
            base_key (str): Base key name (e.g., 'workspace_columns', 'selected_files')
            organization_id (int, optional): Organization numeric ID to append
            
        Returns:
            str: Standardized session key
        """
        key = f"{self.SESSION_PREFIX}_{base_key}"
        
        if organization_id:
            # Always use numeric ID for consistency
            key = f"{key}_{organization_id}"
            
        return key
    
    def _get_shared_session_key(self, base_key):
        """
        Generate shared session key (no prefix) for cross-coordinator state.
        
        Args:
            base_key (str): Base key name
            
        Returns:
            str: Shared session key
        """
        return base_key
    
    def get_current_organization(self, request):
        """
        Get the currently selected organization from session.
        
        Args:
            request: Django request object
            
        Returns:
            dict: Organization data with keys: id, code, name
            None: If no organization is selected
        """
        session_key = self._get_shared_session_key(self.SHARED_CURRENT_ORGANIZATION_KEY)
        return request.session.get(session_key)
    
    def set_current_organization(self, request, organization_identifier):
        """
        Set the current organization in session.
        
        Args:
            request: Django request object
            organization_identifier: Organization ID (numeric) or code (string)
            
        Returns:
            dict: Organization data that was set
            None: If organization not found
        """
        try:
            # Try to parse as numeric ID first
            if str(organization_identifier).isdigit():
                organization = Organization.objects.get(id=int(organization_identifier))
            else:
                # Treat as organization code
                organization = Organization.objects.get(code=organization_identifier)
            
            org_data = {
                'id': organization.id,
                'code': organization.code,
                'name': organization.name
            }
            
            session_key = self._get_shared_session_key(self.SHARED_CURRENT_ORGANIZATION_KEY)
            request.session[session_key] = org_data
            request.session.modified = True
            
            logger.info(f"BASE_COORDINATOR: Set current organization to {org_data['name']} (code: {org_data['code']}, id: {org_data['id']}) with key: {session_key}")
            return org_data
            
        except (Organization.DoesNotExist, ValueError) as e:
            logger.warning(f"BASE_COORDINATOR: Organization '{organization_identifier}' not found: {e}")
            return None
    
    def clear_current_organization(self, request):
        """
        Clear the current organization from session.
        
        Args:
            request: Django request object
        """
        session_key = self._get_shared_session_key(self.SHARED_CURRENT_ORGANIZATION_KEY)
        if session_key in request.session:
            del request.session[session_key]
            request.session.modified = True
            logger.info(f"BASE_COORDINATOR: Cleared current organization from key: {session_key}")
    
    def get_current_mapping(self, request):
        """
        Get the currently selected mapping from session (shared across all coordinators).
        
        Args:
            request: Django request object
            
        Returns:
            dict: Mapping data with keys: id, name, organization_id, loaded_at
            None: If no mapping is selected
        """
        session_key = self._get_shared_session_key(self.SHARED_CURRENT_MAPPING_KEY)
        return request.session.get(session_key)
    
    def set_current_mapping(self, request, mapping_id, mapping_name=None, organization_id=None):
        """
        Set the current mapping in session (shared across all coordinators).
        
        Args:
            request: Django request object
            mapping_id: Mapping ID
            mapping_name: Mapping name (optional)
            organization_id: Organization ID (optional, uses current if not provided)
            
        Returns:
            dict: Mapping data that was set
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("BASE_COORDINATOR: Cannot set mapping without organization")
                return None
            organization_id = current_org['id']
        
        mapping_data = {
            'id': mapping_id,
            'name': mapping_name or f"Mapping {mapping_id}",
            'organization_id': organization_id,
            'loaded_at': timezone.now().isoformat()
        }
        
        session_key = self._get_shared_session_key(self.SHARED_CURRENT_MAPPING_KEY)
        request.session[session_key] = mapping_data
        request.session.modified = True
        
        logger.info(f"BASE_COORDINATOR: Set current mapping to '{mapping_data['name']}' (id: {mapping_id}) for org ID {organization_id}")
        return mapping_data
    
    def clear_current_mapping(self, request):
        """
        Clear the current mapping from session.
        
        Args:
            request: Django request object
            
        Returns:
            dict: The mapping data that was cleared, or None
        """
        session_key = self._get_shared_session_key(self.SHARED_CURRENT_MAPPING_KEY)
        if session_key in request.session:
            mapping_data = request.session[session_key]
            del request.session[session_key]
            request.session.modified = True
            logger.info(f"BASE_COORDINATOR: Cleared current mapping '{mapping_data.get('name', 'unknown')}' (id: {mapping_data.get('id', 'unknown')})")
            return mapping_data
        return None
    
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
    
    def handle_organization_change(self, request, new_organization_identifier):
        """
        Handle organization change with proper state cleanup.
        
        SAFER IMPLEMENTATION: Sets new organization first, then clears old state.
        This prevents data loss if setting the new organization fails.
        
        Args:
            request: Django request object
            new_organization_identifier: New organization ID or code
            
        Returns:
            tuple: (org_data, old_org_data) - New organization data and old organization data
        """
        logger.info(f"BASE_COORDINATOR: Handling organization change to {new_organization_identifier}")
        
        # Get current organization for cleanup
        old_org = self.get_current_organization(request)
        
        # Set new organization FIRST (safer - prevents data loss on failure)
        new_org_data = self.set_current_organization(request, new_organization_identifier)
        
        if not new_org_data:
            logger.error(f"BASE_COORDINATOR: Failed to set new organization {new_organization_identifier}")
            return None, old_org
        
        # Only clear old state AFTER successfully setting new organization
        if old_org and old_org['id'] != new_org_data['id']:
            logger.info(f"BASE_COORDINATOR: Clearing old organization state for {old_org['code']} (ID: {old_org['id']})")
            self.clear_organization_specific_state(request, old_org['id'])
            
            # Only clear the current mapping if it belongs to the old organization
            current_mapping = self.get_current_mapping(request)
            if current_mapping and current_mapping.get('organization_id') == old_org['id']:
                logger.info(f"BASE_COORDINATOR: Clearing mapping '{current_mapping.get('name')}' that belongs to old organization")
                self.clear_current_mapping(request)
            else:
                logger.info(f"BASE_COORDINATOR: Preserving mapping - it doesn't belong to old organization or no mapping exists")
        
        # Also store this organization for cross-view persistence (if OrganizationMixin is available)
        if hasattr(self, 'set_last_selected_organization'):
            self.set_last_selected_organization(request, new_organization_identifier)
        
        return new_org_data, old_org
    
    def get_base_template_context(self, request, additional_context=None):
        """
        Get base template context that all coordinators can use.
        
        This provides common context items like organization info, mapping info,
        CSRF token, and any additional context passed in.
        
        Args:
            request: Django request object
            additional_context (dict, optional): Additional context to merge
            
        Returns:
            dict: Base template context
        """
        context = {
            **self.get_organization_context(request),
            'current_mapping': self.get_current_mapping(request),
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
        
        IMPORTANT: Subclasses MUST implement this method to clear their
        specific organization-related session data.
        
        Args:
            request: Django request object
            organization_id (int): Organization numeric ID to clear state for
        """
        logger.info(f"BASE_COORDINATOR: Clearing organization-specific state for org ID {organization_id}")
        # Subclasses should implement specific state clearing
        # This is intentionally a no-op in the base class
    
    def clear_all_coordinator_state(self, request):
        """
        Clear ALL coordinator-related session data for the current user.
        
        This is a "nuclear option" that clears:
        1. Current organization selection
        2. All coordinator-prefixed session keys
        3. Organization-specific state for all coordinators
        
        Use this for logout, session reset, or debugging.
        
        Args:
            request: Django request object
            
        Returns:
            dict: Summary of what was cleared
        """
        logger.info("BASE_COORDINATOR: GLOBAL COORDINATOR STATE RESET")
        
        # Get current organization and mapping before clearing
        current_org = self.get_current_organization(request)
        current_mapping = self.get_current_mapping(request)
        
        # Clear current organization and mapping selection
        self.clear_current_organization(request)
        self.clear_current_mapping(request)
        
        # Find all coordinator-related session keys
        coordinator_keys = []
        for key in list(request.session.keys()):
            if ('_mapping' in key or '_ingest' in key or '_base' in key or 
                key.startswith('csv_') or key.startswith('ingest_') or key.startswith('base_')):
                coordinator_keys.append(key)
        
        # Remove all coordinator session keys
        for key in coordinator_keys:
            del request.session[key]
            logger.info(f"BASE_COORDINATOR: Cleared session key: {key}")
        
        request.session.modified = True
        
        summary = {
            'organization_cleared': current_org is not None,
            'organization_name': current_org['name'] if current_org else None,
            'session_keys_cleared': len(coordinator_keys),
            'cleared_keys': coordinator_keys
        }
        
        logger.info(f"BASE_COORDINATOR: GLOBAL RESET COMPLETE - {summary}")
        return summary
    
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
        
        # Get all shared keys
        shared_sessions = {
            key: value for key, value in request.session.items()
            if key in [self.SHARED_CURRENT_ORGANIZATION_KEY]
        }
        
        return {
            'coordinator_type': self.__class__.__name__,
            'session_prefix': self.SESSION_PREFIX,
            'current_organization': current_org,
            'coordinator_sessions': coordinator_sessions,
            'shared_sessions': shared_sessions,
            'total_session_keys': len(request.session.keys()),
            'coordinator_session_count': len(coordinator_sessions)
        }