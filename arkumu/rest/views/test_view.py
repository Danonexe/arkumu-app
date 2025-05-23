from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([AllowAny])
def test_view(request):
    """
    A simple test view to check if our API is accessible.
    """
    return Response({"message": "Test view is working!"}) 