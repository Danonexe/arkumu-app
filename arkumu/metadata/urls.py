from django.urls import path
from .views import ModelBrowserView

app_name = 'metadata'
urlpatterns = [
    path('browse/', ModelBrowserView.as_view(), name='model_browser'),
]
