from django.shortcuts import render
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Exists, OuterRef
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import ListView, DetailView
from django.conf import settings
from arkumu.metadata.models.resource import Resource, ResourceType, PublicAccessLevel
from arkumu.metadata.models.triples import Triple

class DataExplorerView(ListView):
    """Main data explorer interface"""
    model = Resource
    template_name = 'metadata/data_explorer.html'
    context_object_name = 'resources'
    paginate_by = 20
    
    def get_queryset(self):
        """Get resources with appropriate access control and debug mode support."""
        # Start with all resources
        queryset = Resource.objects.all().select_related('organization').annotate(
            subject_count=Count('subject_triples', distinct=True),
            predicate_count=Count('predicate_triples', distinct=True),
            object_count=Count('object_triples', distinct=True),
        )
        
        # Debug mode - show all resources in development
        if settings.DEBUG and self.request.GET.get('debug') == 'true':
            return self.apply_filters(queryset).order_by('-created_at')
        
        # Apply access control based on user permissions
        if not self.request.user.is_authenticated:
            # Anonymous users see only public approved resources
            queryset = queryset.filter(
                public_access_level=PublicAccessLevel.PUBLIC,
                is_public_approved=True
            )
        elif not self.request.user.has_perm('metadata.view_all_resources'):
            # Authenticated users see public + restricted resources
            queryset = queryset.filter(
                public_access_level__in=[
                    PublicAccessLevel.PUBLIC, 
                    PublicAccessLevel.RESTRICTED
                ]
            )
        # Staff/admin users see all resources (no additional filtering)
        
        # Apply filters
        return self.apply_filters(queryset).order_by('-created_at')
    
    def _get_accessible_sources(self):
        """Get list of sources accessible to current user."""
        # Start with all resources
        queryset = Resource.objects.all()
        
        # Debug mode - show all sources in development
        if settings.DEBUG and self.request.GET.get('debug') == 'true':
            return queryset.values_list('source', flat=True).distinct().order_by('source')
        
        # Apply access control based on user permissions
        if not self.request.user.is_authenticated:
            # Anonymous users see only public approved resources
            queryset = queryset.filter(
                public_access_level=PublicAccessLevel.PUBLIC,
                is_public_approved=True
            )
        elif not self.request.user.has_perm('metadata.view_all_resources'):
            # Authenticated users see public + restricted resources
            queryset = queryset.filter(
                public_access_level__in=[
                    PublicAccessLevel.PUBLIC, 
                    PublicAccessLevel.RESTRICTED
                ]
            )
        # Staff/admin users see all resources (no additional filtering)
        
        return queryset.values_list('source', flat=True).distinct().order_by('source')
    
    def apply_filters(self, queryset):
        """Apply various filters based on request parameters"""
        # Search
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(uri__icontains=search) |
                Q(name__icontains=search) |
                Q(value__icontains=search) |
                Q(source__icontains=search)
            )
        
        # Resource type filter
        resource_types = self.request.GET.getlist('resource_type')
        if resource_types:
            queryset = queryset.filter(resource_type__in=resource_types)
        
        # Resource type groups
        type_group = self.request.GET.get('type_group')
        if type_group == 'identifiers':
            queryset = queryset.exclude(resource_type=ResourceType.LITERAL)
        elif type_group == 'literals':
            queryset = queryset.filter(resource_type=ResourceType.LITERAL)
        elif type_group == 'placeholders':
            queryset = queryset.filter(is_placeholder=True)
        
        # Source filter
        sources = self.request.GET.getlist('source')
        if sources:
            queryset = queryset.filter(source__in=sources)
        
        # Triple usage filter
        triple_usage = self.request.GET.get('triple_usage')
        if triple_usage == 'as_subject':
            queryset = queryset.filter(
                Exists(Triple.objects.filter(subject=OuterRef('pk')))
            )
        elif triple_usage == 'as_predicate':
            queryset = queryset.filter(
                Exists(Triple.objects.filter(predicate=OuterRef('pk')))
            )
        elif triple_usage == 'as_object':
            queryset = queryset.filter(
                Exists(Triple.objects.filter(object=OuterRef('pk')))
            )
        elif triple_usage == 'no_triples':
            queryset = queryset.filter(
                ~Exists(Triple.objects.filter(
                    Q(subject=OuterRef('pk')) |
                    Q(predicate=OuterRef('pk')) |
                    Q(object=OuterRef('pk'))
                ))
            )
        
        # External linking
        externally_linked = self.request.GET.get('externally_linked')
        if externally_linked == 'true':
            queryset = queryset.filter(is_externally_linked=True)
        elif externally_linked == 'false':
            queryset = queryset.filter(is_externally_linked=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        if not hasattr(self, 'kwargs'):
            self.kwargs = {}
        context = super().get_context_data(**kwargs)
        
        # Add filter options for the template
        context['filter_options'] = {
            'resource_types': [
                {'value': ResourceType.IRI, 'label': 'IRI'},
                {'value': ResourceType.CLASS, 'label': 'Class'},
                {'value': ResourceType.PROPERTY, 'label': 'Property'},
                {'value': ResourceType.LITERAL, 'label': 'Literal'},
            ],
            'type_groups': [
                {'value': 'identifiers', 'label': 'Identifiers (IRI, Class, Property)'},
                {'value': 'literals', 'label': 'Literals Only'},
                {'value': 'placeholders', 'label': 'Placeholder Resources'},
            ],
            'triple_usage': [
                {'value': 'as_subject', 'label': 'Used as Subject'},
                {'value': 'as_predicate', 'label': 'Used as Predicate'},
                {'value': 'as_object', 'label': 'Used as Object'},
                {'value': 'no_triples', 'label': 'No Triple References'},
            ],
            'sources': self._get_accessible_sources(),
        }
        
        # Current filters for template
        context['current_filters'] = {
            'search': self.request.GET.get('search', ''),
            'resource_type': self.request.GET.getlist('resource_type'),
            'type_group': self.request.GET.get('type_group'),
            'source': self.request.GET.getlist('source'),
            'triple_usage': self.request.GET.get('triple_usage'),
            'externally_linked': self.request.GET.get('externally_linked'),
        }
        
        return context

class ResourceDetailView(DetailView):
    """HTMX-powered resource detail view"""
    model = Resource
    template_name = 'metadata/resource_detail.html'
    context_object_name = 'resource'
    
    def get_queryset(self):
        """Get resources with appropriate access control."""
        # Start with all resources
        queryset = Resource.objects.all().select_related('organization')
        
        # Debug mode - show all resources in development
        if settings.DEBUG and self.request.GET.get('debug') == 'true':
            return queryset
        
        # Apply access control based on user permissions
        if not self.request.user.is_authenticated:
            # Anonymous users see only public approved resources
            queryset = queryset.filter(
                public_access_level=PublicAccessLevel.PUBLIC,
                is_public_approved=True
            )
        elif not self.request.user.has_perm('metadata.view_all_resources'):
            # Authenticated users see public + restricted resources
            queryset = queryset.filter(
                public_access_level__in=[
                    PublicAccessLevel.PUBLIC, 
                    PublicAccessLevel.RESTRICTED
                ]
            )
        # Staff/admin users see all resources (no additional filtering)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resource = self.object
        
        # Get triple relationships
        context['subject_triples'] = Triple.objects.filter(
            subject=resource
        ).select_related('predicate', 'object')[:10]
        
        context['predicate_triples'] = Triple.objects.filter(
            predicate=resource
        ).select_related('subject', 'object')[:10]
        
        context['object_triples'] = Triple.objects.filter(
            object=resource
        ).select_related('subject', 'predicate')[:10]
        
        # Get counts
        context['subject_count'] = resource.subject_triples.count()
        context['predicate_count'] = resource.predicate_triples.count()
        context['object_count'] = resource.object_triples.count()
        
        return context

@method_decorator(cache_page(60 * 5), name='dispatch')  # 5 minute cache
class DataExplorerResultsView(DataExplorerView):
    """HTMX endpoint for filtered results"""
    template_name = 'metadata/data_explorer_results.html'