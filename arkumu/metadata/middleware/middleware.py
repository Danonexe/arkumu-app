from threading import local

_thread_locals = local()

def get_current_user():
    """Returns the current user from thread-local storage"""
    return getattr(_thread_locals, 'user', None)

class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store the user at the beginning of the request
        if hasattr(request, 'user'):
            _thread_locals.user = request.user
        else:
            _thread_locals.user = None

        # Process the request
        response = self.get_response(request)

        # Clean up thread local storage
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user

        return response
