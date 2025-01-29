from django.shortcuts import render
from django.views.generic import ListView
from django.apps import apps
from arkumu.metadata.models import Projekt, Ereignis, Akteur, Ort, Sammlung, DigitalesObjekt, Informationstraeger, Hochschule, BestehenderLizenzvertrag, DigitalesObjektLizenz, Eigenschaft, EreignisTyp, Informationstraegertyp, Organisationseinheit, ProjektArt, ProjektKategorie, Rolle, Sprache
# Create your views here.

class BaseModelBrowserView(ListView):
    template_name = 'model_browser.html' 
    context_object_name = 'objects' 
    paginate_by = 10

    # Override this in child classes
    ALLOWED_MODELS = {}

    def get_queryset(self):
        selected_model = self.request.GET.get('model')
        
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            return model_class.objects.all().order_by('id')
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        app_models = []
        for model_key, model_class in self.ALLOWED_MODELS.items():
            app_models.append({
                'name': model_class._meta.verbose_name.title(),
                'model_name': model_key,
                'fields': [field.name for field in model_class._meta.fields 
                          if not field.name in ['id', 'password']]
            })
        
        context['models'] = app_models

        selected_model = self.request.GET.get('model')
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            context['selected_model'] = model_class._meta.verbose_name.title()
            context['fields'] = [field.name for field in model_class._meta.fields 
                               if not field.name in ['id', 'password']]
            
        get_copy = self.request.GET.copy()
        if 'page' in get_copy:
            get_copy.pop('page')
        context['query_params'] = get_copy.urlencode()
        
        return context

# Your original view becomes:
class MetadataModelBrowserView(BaseModelBrowserView):
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
    }

# View for administration models
class AdministrationView(BaseModelBrowserView):
    ALLOWED_MODELS = {
        'BestehenderLizenzvertrag': BestehenderLizenzvertrag,
        'DigitalesObjektLizenz': DigitalesObjektLizenz,
        'Eigenschaft': Eigenschaft,
        'EreignisTyp': EreignisTyp,
        'Hochschule': Hochschule,
        'Informationstraegertyp': Informationstraegertyp,
        'Organisationseinheit': Organisationseinheit,
        'ProjektArt': ProjektArt,
        'ProjektKategorie': ProjektKategorie,
        'Rolle': Rolle,
        'Sprache': Sprache,
    }

