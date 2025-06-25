from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class ShibbolethRemoteUserBackend(RemoteUserBackend):
    """
    Enhanced Shibboleth authentication backend with organization and role support.
    
    This backend uses the RemoteUserBackend to authenticate users and
    populates user fields from Shibboleth attributes including organization mapping.
    """
    
    create_unknown_user = True
    
    def authenticate(self, request, remote_user, **kwargs):
        """
        The username passed as ``remote_user`` is considered trusted.
        Return the ``User`` object with the given username. Create a new
        ``User`` object if ``create_unknown_user`` is ``True``.
        
        Also populate additional user fields from Shibboleth attributes.
        """
        if not remote_user:
            return None
            
        username = self.clean_username(remote_user)
        eppn = request.META.get('eppn', username) if request else username
        
        # Try to find user by various identifiers
        user = self._find_existing_user(username, eppn, request)
        
        if not user and self.create_unknown_user:
            user = self._create_shibboleth_user(username, eppn, request)
        
        if user:
            self.update_user_from_shibboleth(request, user)
                
        return user
    
    def _find_existing_user(self, username, eppn, request):
        """Find existing user by various identifiers"""
        # Try EPPN first
        if eppn:
            try:
                return User.objects.get(shibboleth_eppn=eppn)
            except User.DoesNotExist:
                pass
        
        # Try username
        try:
            user = User.objects.get(username=username)
            # Update EPPN if missing
            if not user.shibboleth_eppn:
                user.shibboleth_eppn = eppn
                user.auth_source = 'shibboleth'
                user.is_federated_user = True
                user.save()
            return user
        except User.DoesNotExist:
            pass
        
        # Try email as fallback
        email = request.META.get('mail') if request else None
        if email:
            try:
                user = User.objects.get(email=email)
                # Link to Shibboleth
                user.username = username
                user.shibboleth_eppn = eppn
                user.auth_source = 'shibboleth'
                user.is_federated_user = True
                user.save()
                return user
            except User.DoesNotExist:
                pass
        
        return None
    
    def _create_shibboleth_user(self, username, eppn, request):
        """Create new user from Shibboleth attributes"""
        user = User(
            username=username,
            shibboleth_eppn=eppn,
            auth_source='shibboleth',
            is_federated_user=True
        )
        user.set_unusable_password()
        
        # Set email if available
        if request and 'mail' in request.META:
            user.email = request.META['mail']
        
        # Try to determine organization from attributes
        org = self._determine_organization(request)
        if org:
            user.organization = org
            user.role = self._determine_initial_role(request, org)
        
        user.save()
        logger.info(f"Created new Shibboleth user: {username}")
        return user
    
    def _determine_organization(self, request):
        """Determine organization from Shibboleth attributes"""
        if not request:
            return None
        
        from .models import Organization
        
        # Try schacHomeOrganization
        home_org = request.META.get('schacHomeOrganization')
        if home_org:
            try:
                return Organization.objects.get(code=home_org)
            except Organization.DoesNotExist:
                pass
        
        # Try entity ID
        entity_id = request.META.get('Shib-Identity-Provider')
        if entity_id:
            try:
                return Organization.objects.get(shibboleth_entity_id=entity_id)
            except Organization.DoesNotExist:
                pass
        
        # Try email domain
        email = request.META.get('mail')
        if email and '@' in email:
            domain = email.split('@')[1]
            try:
                return Organization.objects.get(domain=domain)
            except Organization.DoesNotExist:
                pass
        
        return None
    
    def _determine_initial_role(self, request, organization):
        """Determine initial role based on Shibboleth attributes"""
        if not request:
            return 'researcher'
        
        # Check affiliation
        affiliation = request.META.get('eduPersonScopedAffiliation', '')
        
        if 'staff' in affiliation or 'employee' in affiliation:
            return 'archivist'
        elif 'faculty' in affiliation:
            return 'data_admin'
        else:
            return 'researcher'
        
    def update_user_from_shibboleth(self, request, user):
        """Update user attributes from Shibboleth"""
        if not request:
            return
        
        updated = False
        
        # Update basic info
        if 'givenName' in request.META or 'sn' in request.META:
            name_parts = []
            if request.META.get('givenName'):
                name_parts.append(request.META['givenName'])
            if request.META.get('sn'):
                name_parts.append(request.META['sn'])
            if name_parts:
                new_name = ' '.join(name_parts)
                if user.name != new_name:
                    user.name = new_name
                    updated = True
        
        # Update email
        if 'mail' in request.META and request.META['mail']:
            if user.email != request.META['mail']:
                user.email = request.META['mail']
                updated = True
        
        # Update affiliation
        affiliation = request.META.get('eduPersonScopedAffiliation', '')
        if user.shibboleth_affiliation != affiliation:
            user.shibboleth_affiliation = affiliation
            updated = True
        
        # Update organization if changed
        if not user.organization:
            org = self._determine_organization(request)
            if org:
                user.organization = org
                updated = True
        
        # Update last login
        user.last_shibboleth_login = timezone.now()
        updated = True
        
        if updated:
            user.save()
    
    def update_user_attributes(self, request, user):
        """Legacy method for backward compatibility"""
        return self.update_user_from_shibboleth(request, user) 