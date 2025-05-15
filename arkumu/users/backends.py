from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class ShibbolethRemoteUserBackend(RemoteUserBackend):
    """
    Authentication backend for Shibboleth.
    
    This backend uses the RemoteUserBackend to authenticate users and
    populates user fields from Shibboleth attributes.
    """
    
    # By default, don't create users automatically if not found
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
            
        user = None
        username = self.clean_username(remote_user)
        
        # Get user by username (ePPN)
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Try to get user by email as fallback
            if request and 'mail' in request.META:
                email = request.META['mail']
                try:
                    user = User.objects.get(email=email)
                    # Update username to match ePPN for future lookups
                    user.username = username
                    user.save()
                except User.DoesNotExist:
                    # Create user if allowed
                    if self.create_unknown_user:
                        user = User(username=username)
                        if email:
                            user.email = email
                        user.set_unusable_password()
                        user.save()
            elif self.create_unknown_user:
                # Create user without email
                user = User(username=username)
                user.set_unusable_password()
                user.save()
                
        if user:
            # Update user attributes from Shibboleth
            self.update_user_attributes(request, user)
                
        return user
        
    def update_user_attributes(self, request, user):
        """Update user attributes from Shibboleth headers"""
        if not request:
            return
        
        # Update name from givenName and sn if available
        if 'givenName' in request.META:
            if hasattr(user, 'name'):
                name_parts = []
                if request.META.get('givenName'):
                    name_parts.append(request.META['givenName'])
                if request.META.get('sn'):
                    name_parts.append(request.META['sn'])
                if name_parts:
                    user.name = ' '.join(name_parts)
            
        # Update email if available
        if 'mail' in request.META and request.META['mail']:
            user.email = request.META['mail']
            
        user.save()
        return user 