from django.urls import path
from .views import ModelBrowserView, AdministrationView

app_name = 'metadata'
urlpatterns = [
    path('browse/', ModelBrowserView.as_view(), name='model_browser'),
    path('administration/', AdministrationView.as_view(), name='administration'),
]
