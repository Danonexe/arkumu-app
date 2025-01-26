from django.shortcuts import render
from django.views.generic import ListView
from django.apps import apps
from arkumu.metadata.models import Projekt, Ereignis, Akteur, Ort, Sammlung, DigitalesObjekt, Informationstraeger, Hochschule, BestehenderLizenzvertrag, Objekttyp
# Create your views here.

class ModelBrowserView(ListView):
    template_name = 'model_browser.html' 
    context_object_name = 'objects' 
    paginate_by = 10

    # Define which models you want to display
    ALLOWED_MODELS = {
        'Projekt': Projekt,
        'Ereignis': Ereignis,
        'Akteur': Akteur,
        'Ort': Ort,
        'Sammlung': Sammlung,
        'DigitalesObjekt': DigitalesObjekt,
        'Informationstraeger': Informationstraeger,
        'Hochschule': Hochschule,
        'BestehenderLizenzvertrag': BestehenderLizenzvertrag,
        'Objekttyp': Objekttyp,
    }

    def get_queryset(self):
        selected_model = self.request.GET.get('model')
        
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            return model_class.objects.all().order_by('id')
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get only specified models
        app_models = []
        for model_key, model_class in self.ALLOWED_MODELS.items():
            app_models.append({
                'name': model_class._meta.verbose_name.title(),
                'model_name': model_key,
                'fields': [field.name for field in model_class._meta.fields 
                          if not field.name in ['id', 'password']]  # Optionally exclude certain fields
            })
        
        context['models'] = app_models

        # Add selected model info
        selected_model = self.request.GET.get('model')
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            context['selected_model'] = model_class._meta.verbose_name.title()
            context['fields'] = [field.name for field in model_class._meta.fields 
                               if not field.name in ['id', 'password']]
            
        # Preserve GET parameters for pagination
        get_copy = self.request.GET.copy()
        if 'page' in get_copy:
            get_copy.pop('page')
        context['query_params'] = get_copy.urlencode()
        
        return context

