from django.urls import path
from django.views.generic import TemplateView

app_name = 'catalog'

urlpatterns = [
    # Design showcase pages with local catalog templates
    path('design/', TemplateView.as_view(template_name="catalog/design.html"), name='design'),
    path('components/', TemplateView.as_view(template_name="catalog/components.html"), name='components'),
    path('documentation/', TemplateView.as_view(template_name="catalog/documentation.html"), name='documentation'),
    path('projekt/', TemplateView.as_view(template_name="catalog/projekt.html"), name='projekt'),
]