from django.shortcuts import render
from django.views.generic import ListView
from django.apps import apps
from arkumu.metadata.models import Projekt, Ereignis, Akteur, Ort, Sammlung, DigitalesObjekt, Informationstraeger, Hochschule, BestehenderLizenzvertrag, DigitalesObjektLizenz, Eigenschaft, EreignisTyp, Informationstraegertyp, Organisationseinheit, ProjektArt, ProjektKategorie, Rolle, Sprache
from django.db.models import Q

# Base class for model browsing views that provides common functionality
class BaseModelBrowserView(ListView):
    template_name = 'model_browser.html' 
    context_object_name = 'objects' 
    paginate_by = 10

    # Dictionary mapping model names to model classes
    # Must be overridden in child classes
    ALLOWED_MODELS = {}

    def get_queryset(self):
        selected_model = self.request.GET.get('model')
        
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            return model_class.objects.all().order_by('id')
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Build list of available models and their fields for the template
        app_models = []
        for model_key, model_class in self.ALLOWED_MODELS.items():
            app_models.append({
                'name': model_class._meta.verbose_name.title(),
                'model_name': model_key,
                'fields': [field.name for field in model_class._meta.fields 
                          if not field.name in ['id', 'password']]
            })
        
        context['models'] = app_models

        # Add selected model info to context if one is selected
        selected_model = self.request.GET.get('model')
        if selected_model and selected_model in self.ALLOWED_MODELS:
            model_class = self.ALLOWED_MODELS[selected_model]
            context['selected_model'] = model_class._meta.verbose_name.title()
            context['fields'] = [field.name for field in model_class._meta.fields 
                               if not field.name in ['id', 'password']]
            
        # Preserve query parameters except page number for pagination links
        get_copy = self.request.GET.copy()
        if 'page' in get_copy:
            get_copy.pop('page')
        context['query_params'] = get_copy.urlencode()
        
        return context

# View for browsing core metadata models
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

# View for browsing administrative/lookup models
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

# Enhanced model browser with search functionality
class ModelBrowserView(BaseModelBrowserView):
    template_name = 'model_browser.html'
    paginate_by = 20
    
    ALLOWED_MODELS = MetadataModelBrowserView.ALLOWED_MODELS
    
    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['model_browser_results.html']
        return [self.template_name]
    
    def get_queryset(self):
        model_name = self.request.GET.get('model')
        search_field = self.request.GET.get('search_field')
        search_query = self.request.GET.get('search_query')
        
        # Get base queryset for selected model
        if model_name and model_name in self.ALLOWED_MODELS:
            queryset = self.ALLOWED_MODELS[model_name].objects.all().order_by('id')
            
            # Filter queryset based on search parameters if provided
            if search_field and search_query:
                # Use case-insensitive contains lookup
                lookup = f"{search_field}__icontains"
                queryset = queryset.filter(**{lookup: search_query})
                
            return queryset
        return []
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add current search parameters to context for form persistence
        context['search_field'] = self.request.GET.get('search_field', '')
        context['search_query'] = self.request.GET.get('search_query', '')
        return context

