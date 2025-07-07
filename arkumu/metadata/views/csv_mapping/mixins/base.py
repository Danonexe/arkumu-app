"""
Base Mixins for CSV Mapping

Contains fundamental mixins that other views inherit from:
- OrganizationMixin: Organization discovery and parameter extraction
"""

import logging
from django.core.cache import cache
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


class OrganizationMixin:
    """
    Mixin for handling organization discovery and parameter extraction.
    Provides methods for getting organization from request and discovering available organizations.
    """
    
    # Session key for storing the last selected organization
    LAST_ORGANIZATION_SESSION_KEY = 'last_selected_organization'
    
    def get_organization_id_from_request(self, request):
        """Get the organization ID from the request (following the same pattern as other views)."""
        # Extract organization from GET or POST parameters, following the same pattern as other views
        # Support both 'organization' (used by CSV mapping/ingestion) and 'org' (used by archivist dashboard)
        organization = (request.GET.get('organization') or request.POST.get('organization') or 
                       request.GET.get('org') or request.POST.get('org'))
        
        # Handle both cases where organization might be passed
        if organization:
            org_id = organization.strip()
            # Store this as the last selected organization
            self.set_last_selected_organization(request, org_id)
            return org_id
        
        # For HTMX requests, try to extract organization from referrer URL
        if 'HX-Request' in request.headers:
            referrer = request.headers.get('Referer', '')
            if '?organization=' in referrer or '?org=' in referrer or '&organization=' in referrer or '&org=' in referrer:
                # Extract organization from URL like "...?organization=rsh" or "...?org=rsh"
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed_url = urlparse(referrer)
                    query_params = parse_qs(parsed_url.query)
                    # Check both parameter names
                    org_param = query_params.get('organization', [None])[0] or query_params.get('org', [None])[0]
                    if org_param:
                        org_id = org_param.strip()
                        self.set_last_selected_organization(request, org_id)
                        return org_id
                except Exception as e:
                    logger.warning(f"Could not extract organization from referrer URL: {e}")
        
        # If no organization in request, try to get the last selected organization from session
        last_org = self.get_last_selected_organization(request)
        if last_org:
            logger.info(f"ORGANIZATION_MIXIN: Using last selected organization from session: {last_org}")
            return last_org
        
        # Fallback: try to get from user if available (for future authentication integration)
        if hasattr(request, 'user') and hasattr(request.user, 'organization_id'):
            return getattr(request.user, 'organization_id', None)
        
        # Default fallback - you may want to raise an exception here instead
        return 'default-org'
    
    def get_available_organizations(self, use_cache=True):
        """
        Discover available organizations from S3 buckets.
        
        Args:
            use_cache (bool): Whether to use cached results
            
        Returns:
            list: List of organization dictionaries with id, name, status
        """
        cache_key = "available_organizations_s3"
        
        if use_cache:
            available_organizations = cache.get(cache_key)
            if available_organizations is not None:
                logger.info(f"ORGANIZATION_MIXIN: Using cached organization list")
                return available_organizations
        
        logger.info(f"ORGANIZATION_MIXIN: Discovering available organizations (not cached)")
        
        try:
            analyzer = S3DirectDataAnalyzer()
            available_organizations = self._discover_available_organizations(analyzer)
            
            if use_cache:
                cache.set(cache_key, available_organizations, timeout=300)  # Cache for 5 minutes
                
            return available_organizations
            
        except Exception as e:
            logger.error(f"ORGANIZATION_MIXIN: Error discovering organizations: {e}")
            return []
    
    def validate_organization_exists(self, organization_id, available_organizations=None):
        """
        Check if the specified organization exists in S3.
        
        Args:
            organization_id (str): Organization ID to validate
            available_organizations (list, optional): Pre-fetched org list to avoid extra call
            
        Returns:
            bool: True if organization exists, False otherwise
        """
        if not organization_id or organization_id == 'default-org':
            return False
            
        if available_organizations is None:
            available_organizations = self.get_available_organizations()
            
        return any(org['id'] == organization_id for org in available_organizations)
    
    def get_organization_context(self, request):
        """
        Get complete organization context for templates.
        
        Returns:
            dict: Context dictionary with organization data
        """
        organization_id = self.get_organization_id_from_request(request)
        available_organizations = self.get_available_organizations()
        org_exists = self.validate_organization_exists(organization_id, available_organizations)
        
        # Don't pass 'default-org' to template - use None instead for cleaner logic
        if organization_id == 'default-org':
            organization_id = None
        
        return {
            'organization_id': organization_id,
            'organizations': available_organizations,
            'organization_exists': org_exists,
        }
    
    def get_last_selected_organization(self, request):
        """
        Get the last selected organization from session.
        
        Returns:
            str: Organization ID that was last selected
            None: If no organization was previously selected
        """
        return request.session.get(self.LAST_ORGANIZATION_SESSION_KEY)
    
    def set_last_selected_organization(self, request, organization_id):
        """
        Store the last selected organization in session.
        
        Args:
            request: Django request object
            organization_id: Organization ID to store
        """
        if organization_id and organization_id != 'default-org':
            request.session[self.LAST_ORGANIZATION_SESSION_KEY] = organization_id
            request.session.modified = True
            logger.info(f"ORGANIZATION_MIXIN: Stored last selected organization: {organization_id}")
    
    def clear_last_selected_organization(self, request):
        """
        Clear the last selected organization from session.
        """
        if self.LAST_ORGANIZATION_SESSION_KEY in request.session:
            del request.session[self.LAST_ORGANIZATION_SESSION_KEY]
            request.session.modified = True
            logger.info("ORGANIZATION_MIXIN: Cleared last selected organization") 
    
    def _discover_available_organizations(self, analyzer):
        """
        Discover available organizations by checking S3 buckets.
        Similar to how archivist dashboard works.
        """
        try:
            # Standard organization list (same as archivist dashboard)
            standard_orgs = [
                {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
                {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
                {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
                {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
                {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
            ]
            
            # Check which organizations actually have S3 data
            for org in standard_orgs:
                try:
                    # Try to discover sources for this organization
                    sources = analyzer.discover_s3_data_sources(org['id'])
                    if sources:  # If sources found, mark as active
                        org['status'] = 'active'
                    else:
                        org['status'] = 'inactive'
                except Exception as e:
                    logger.debug(f"Organization {org['id']} check failed: {e}")
                    org['status'] = 'inactive'
            
            return standard_orgs
            
        except Exception as e:
            logger.error(f"Error discovering organizations: {e}")
            # Return standard list with unknown status if discovery fails
            return [
                {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
                {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
                {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
                {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
                {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
            ]