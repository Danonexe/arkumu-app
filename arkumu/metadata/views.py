from django.shortcuts import render
from django.views.generic import ListView
from django.apps import apps
from arkumu.metadata.models import Projekt, Ereignis, Akteur, Ort, Sammlung, DigitalesObjekt, Informationstraeger, Hochschule, BestehenderLizenzvertrag, DigitalesObjektLizenz, Eigenschaft, EreignisTyp, Informationstraegertyp, Organisationseinheit, ProjektArt, ProjektKategorie, Rolle, Sprache
from django.db.models import Q
from django.core.cache import cache
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
import os

# Set up logger
logger = logging.getLogger(__name__)


# Replace the existing cache decorators with:
def conditional_cache(timeout):
    def decorator(view_func):
        if os.environ.get('DISABLE_CACHE'):
            logger.info("🚫 Cache is DISABLED via DISABLE_CACHE environment variable")
            return view_func
        logger.info("✅ Cache is ENABLED with timeout: %d seconds", timeout)
        return cache_page(timeout)(view_func)
    return decorator

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
@method_decorator(conditional_cache(60 * 15), name='dispatch')
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

    def dispatch(self, request, *args, **kwargs):
        logger.info(f"MetadataModelBrowserView accessed - Cache key: {request.path}")
        return super().dispatch(request, *args, **kwargs)

# View for browsing administrative/lookup models
@method_decorator(conditional_cache(60 * 15), name='dispatch')
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

    def dispatch(self, request, *args, **kwargs):
        logger.info(f"AdministrationView accessed - Cache key: {request.path}")
        return super().dispatch(request, *args, **kwargs)

# Enhanced model browser with search functionality
@method_decorator(conditional_cache(60 * 5), name='dispatch')  # Cache for 5 minutes
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
        
        # Create a cache key based on the query parameters
        cache_key = f'model_browser_{model_name}_{search_field}_{search_query}'
        
        # Log cache attempt
        logger.info(f"Attempting to fetch from cache - Key: {cache_key}")
        
        # Try to get the queryset from cache
        queryset = cache.get(cache_key)
        if queryset is not None:
            logger.info(f"Cache HIT for key: {cache_key}")
            return queryset
            
        # If not in cache, generate the queryset
        logger.info(f"Cache MISS for key: {cache_key}")
        if model_name and model_name in self.ALLOWED_MODELS:
            queryset = self.ALLOWED_MODELS[model_name].objects.all().order_by('id')
            
            if search_field and search_query:
                lookup = f"{search_field}__icontains"
                queryset = queryset.filter(**{lookup: search_query})
                
            # Cache the queryset for 5 minutes
            cache.set(cache_key, queryset, 300)
            logger.info(f"Cached new queryset for key: {cache_key}")
            return queryset
        return []
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add current search parameters to context for form persistence
        context['search_field'] = self.request.GET.get('search_field', '')
        context['search_query'] = self.request.GET.get('search_query', '')
        return context

