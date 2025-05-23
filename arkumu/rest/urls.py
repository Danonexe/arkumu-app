from django.urls import path, include
from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from arkumu.rest.views.import_viewsets import ImportViewSet, TestingViewSet
from arkumu.rest.views.test_view import test_view

app_name = 'rest'

# Create a router based on debug mode
router = DefaultRouter() if settings.DEBUG else SimpleRouter()

# Register ViewSets
router.register(r'import', ImportViewSet, basename='import')
router.register(r'testing', TestingViewSet, basename='testing')

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    # Test view
    path('', test_view, name='test_view'),
] 