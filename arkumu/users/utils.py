"""
User and Organization utilities for backward compatibility and integration.
"""
from typing import Optional
from django.http import HttpRequest
from .models import Organization


def get_organization_from_request(request: HttpRequest) -> Optional[Organization]:
    """
    Get Organization object from request with backward compatibility.
    
    This function provides a bridge between the existing string-based org_id system
    and the new Organization model. It maintains full backward compatibility while
    enabling new Organization features.
    
    Args:
        request: Django HttpRequest object
        
    Returns:
        Organization object if found, None otherwise
        
    Usage:
        # In views that currently use get_organization_id_from_request
        org = get_organization_from_request(request)
        if org:
            org_code = org.code  # backward compatible string
            org_name = org.name  # new functionality
    """
    # Import here to avoid circular imports
    from arkumu.metadata.views.direct_data_views import get_organization_id_from_request
    
    org_code = get_organization_id_from_request(request)
    if org_code:
        try:
            return Organization.objects.get(code=org_code)
        except Organization.DoesNotExist:
            # Log missing organization for admin attention
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Organization with code '{org_code}' not found in database")
            return None
    return None


def get_organization_by_code(org_code: str) -> Optional[Organization]:
    """
    Get Organization object by code string.
    
    Args:
        org_code: Organization code (e.g., "rsh", "khm", "fuk")
        
    Returns:
        Organization object if found, None otherwise
    """
    if not org_code:
        return None
        
    try:
        return Organization.objects.get(code=org_code)
    except Organization.DoesNotExist:
        return None


def get_user_organization_access(user, org_code: str = None) -> dict:
    """
    Check user's access to organization data.
    
    Args:
        user: User object
        org_code: Optional organization code to check specific access
        
    Returns:
        Dictionary with access information:
        {
            'can_access': bool,
            'user_org': Organization or None,
            'target_org': Organization or None,
            'is_system_admin': bool,
            'access_reason': str
        }
    """
    result = {
        'can_access': False,
        'user_org': user.organization,
        'target_org': None,
        'is_system_admin': user.role == 'system_admin',
        'access_reason': ''
    }
    
    # System admins can access all organizations
    if user.role == 'system_admin':
        result['can_access'] = True
        result['access_reason'] = 'system_admin'
        if org_code:
            result['target_org'] = get_organization_by_code(org_code)
        return result
    
    # If no specific org requested, check if user has an organization
    if not org_code:
        result['can_access'] = user.organization is not None
        result['access_reason'] = 'user_has_organization' if result['can_access'] else 'no_organization'
        return result
    
    # Check access to specific organization
    target_org = get_organization_by_code(org_code)
    result['target_org'] = target_org
    
    if not target_org:
        result['access_reason'] = 'organization_not_found'
        return result
    
    if user.organization == target_org:
        result['can_access'] = True
        result['access_reason'] = 'same_organization'
    else:
        result['access_reason'] = 'different_organization'
    
    return result


def create_organization_from_code(org_code: str, name: str = None) -> Organization:
    """
    Create Organization from legacy org_code.
    
    This is useful for migrating existing org_id strings to Organization objects.
    
    Args:
        org_code: Organization code (e.g., "rsh", "khm")
        name: Optional organization name, defaults to formatted code
        
    Returns:
        Created Organization object
    """
    if not name:
        name = f"Organization {org_code.upper()}"
    
    org, created = Organization.objects.get_or_create(
        code=org_code,
        defaults={'name': name}
    )
    
    if created:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Created organization: {org.name} (code: {org.code})")
    
    return org


def ensure_predefined_organizations():
    """
    Ensure all predefined organizations exist in the database.
    
    This should be called during deployment or setup to create Organization
    objects for all existing org_id strings used in the system.
    
    Now uses OrganizationType TextChoices for standardized organization data.
    """
    # Import here to avoid circular imports  
    from arkumu.storage.services.bucket_service import PREDEFINED_ORGANIZATIONS
    
    # Use OrganizationType for consistent organization data
    from .models import Organization, OrganizationType
    type_choices_map = {choice[0]: choice[1] for choice in OrganizationType.choices}
    
    created_count = 0
    for org_code in PREDEFINED_ORGANIZATIONS:
        # Try to match with OrganizationType or create custom name
        org_name = type_choices_map.get(org_code, f"Organization {org_code.upper()}")
        
        org, created = Organization.objects.get_or_create(
            code=org_code,
            defaults={
                'name': org_name,
                'is_active': True
            }
        )
        if created:
            created_count += 1
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Ensured {len(PREDEFINED_ORGANIZATIONS)} organizations exist, created {created_count} new ones")
    
    return created_count