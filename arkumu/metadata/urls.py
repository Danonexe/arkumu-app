from django.urls import path
from .views import MetadataModelBrowserView, AdministrationView

app_name = 'metadata'
urlpatterns = [
    path('browse/', MetadataModelBrowserView.as_view(), name='model_browser'),
    path('administration/', AdministrationView.as_view(), name='administration'),
]
