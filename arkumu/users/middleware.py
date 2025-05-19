from django.conf import settings
from django.contrib.auth.middleware import RemoteUserMiddleware
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class ShibbolethRemoteUserMiddleware(RemoteUserMiddleware):
    """
    Middleware for utilizing Shibboleth-provided authentication.
    
    The RemoteUserMiddleware authentication middleware allows for remote
    authentication via the REMOTE_USER environment variable set by
    Shibboleth through mod_shib.
    """
    
    # Name of the Shibboleth attribute in request.META for username
    header = 'HTTP_EPPN'  # HTTP_ prefixed header format that Apache uses
    
    # List of Shibboleth attributes to map
    shibboleth_attributes = [
        'eppn',            # eduPersonPrincipalName
        'mail',            # Email
        'givenName',       # First name
        'sn',              # Last name
        'eduPersonAffiliation',  # Role
        'schacHomeOrganization'  # Institution
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Check for our special cookie that indicates this is a Shibboleth authenticated session
        if settings.DEBUG and 'shibauth' in request.COOKIES and not request.user.is_authenticated:
            logger.info("🔐 ShibbolethMiddleware: Detected shibauth cookie but user not authenticated")
            
            # We need to try to restore the user's session
            # First, check if the user has a session cookie but Django hasn't loaded the user yet
            if request.session.session_key:
                logger.info(f"🔐 ShibbolethMiddleware: Found session key: {request.session.session_key}")
                # The session exists but the user wasn't loaded automatically
                # This could happen if the session backend is having issues
            
        # Call parent middleware to handle the request
        response = super().__call__(request)
        
        # Debug logging
        if request.path == '/users/shibboleth/' or request.path == '/':
            logger.info(f"🔐 ShibbolethMiddleware: After processing, authenticated={request.user.is_authenticated}")
            if request.user.is_authenticated:
                logger.info(f"🔐 ShibbolethMiddleware: Logged in as {request.user.username}")
        
        return response 