from django.urls import path
from . import views

app_name = 'metadata'

urlpatterns = [
    # Add your metadata URLs here
    path('daisy-test/', views.daisy_test, name='daisy_test'),
]
