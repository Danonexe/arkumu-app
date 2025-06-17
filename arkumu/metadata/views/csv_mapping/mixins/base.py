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
    
    def get_organization_id_from_request(self, request):
        """Get the organization ID from the request (following the same pattern as other views)."""
        # Extract organization from GET or POST parameters, following the same pattern as other views
        organization = request.GET.get('organization') or request.POST.get('organization')
        
        # Handle both cases where organization might be passed
        if organization:
            return organization.strip()
        
        # For HTMX requests, try to extract organization from referrer URL
        if 'HX-Request' in request.headers:
            referrer = request.headers.get('Referer', '')
            if '?organization=' in referrer:
                # Extract organization from URL like "...?organization=rsh"
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed_url = urlparse(referrer)
                    query_params = parse_qs(parsed_url.query)
                    org_param = query_params.get('organization', [None])[0]
                    if org_param:
                        return org_param.strip()
                except Exception as e:
                    logger.warning(f"Could not extract organization from referrer URL: {e}")
        
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
            organizations = analyzer.discover_available_organizations()
            available_organizations = [
                {
                    'id': org_id,
                    'name': org_name,
                    'status': 'active'  # Could be enhanced with actual status checking
                }
                for org_id, org_name in organizations.items()
            ]
            
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
        
        return {
            'organization_id': organization_id,
            'organizations': available_organizations,
            'organization_exists': org_exists,
        } 