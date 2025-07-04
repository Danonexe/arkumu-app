"""
Model Graph Views for Interactive Model Visualization

Provides HTMX endpoints for exploring the Mapping model structure
in an interactive graphical interface.
"""

import logging
from django.shortcuts import render
from django.http import HttpResponse
from django.views import View
from arkumu.users.mixins import GeneralLoginRequiredMixin

logger = logging.getLogger(__name__)


class ModelGraphView(GeneralLoginRequiredMixin, View):
    """
    Main view for the interactive model graph visualization.
    Shows the complete Mapping model structure.
    """
    
    def get(self, request):
        """Render the main model graph view."""
        logger.info("MODEL_GRAPH: Rendering main model graph view")
        
        context = {
            'page_title': 'Mapping Model Graph',
            'description': 'Interactive visualization of the Mapping model architecture'
        }
        
        return render(request, 'model_graph.html', context)


class MappingDetailsView(GeneralLoginRequiredMixin, View):
    """
    HTMX endpoint for showing details about the core Mapping model.
    """
    
    def get(self, request):
        """Return details about the core Mapping model."""
        logger.info("MODEL_GRAPH: Serving mapping core details")
        
        return render(request, 'partials/model_graph/mapping_details.html')


class FieldDetailsView(GeneralLoginRequiredMixin, View):
    """
    HTMX endpoint for showing details about specific model fields.
    """
    
    def get(self, request, field_type):
        """Return details about a specific field type."""
        logger.info(f"MODEL_GRAPH: Serving field details for type: {field_type}")
        
        # Validate field type
        valid_field_types = ['basic', 'organization', 'sources', 'config', 'indexes']
        if field_type not in valid_field_types:
            return HttpResponse(f'<div class="text-red-600">Invalid field type: {field_type}</div>')
        
        context = {
            'field_type': field_type
        }
        
        return render(request, 'partials/model_graph/field_details.html', context)


class WorkflowDetailsView(GeneralLoginRequiredMixin, View):
    """
    HTMX endpoint for showing details about workflow-related fields.
    """
    
    def get(self, request, workflow_type):
        """Return details about workflow aspects."""
        logger.info(f"MODEL_GRAPH: Serving workflow details for type: {workflow_type}")
        
        # Validate workflow type
        valid_workflow_types = ['validation', 'execution']
        if workflow_type not in valid_workflow_types:
            return HttpResponse(f'<div class="text-red-600">Invalid workflow type: {workflow_type}</div>')
        
        context = {
            'workflow_type': workflow_type
        }
        
        return render(request, 'partials/model_graph/workflow_details.html', context)


class RelationDetailsView(GeneralLoginRequiredMixin, View):
    """
    HTMX endpoint for showing details about model relationships.
    """
    
    def get(self, request, relation_type):
        """Return details about model relationships."""
        logger.info(f"MODEL_GRAPH: Serving relation details for type: {relation_type}")
        
        # Validate relation type
        valid_relation_types = ['user']
        if relation_type not in valid_relation_types:
            return HttpResponse(f'<div class="text-red-600">Invalid relation type: {relation_type}</div>')
        
        context = {
            'relation_type': relation_type
        }
        
        return render(request, 'partials/model_graph/relation_details.html', context)


# Function-based views for simpler routing (alternative approach)
def model_graph_main(request):
    """Simple function-based view for main graph."""
    return ModelGraphView.as_view()(request)


def model_graph_mapping_details(request):
    """Simple function-based view for mapping details."""
    return MappingDetailsView.as_view()(request)


def model_graph_field_details(request, field_type):
    """Simple function-based view for field details."""
    return FieldDetailsView.as_view()(request, field_type=field_type)


def model_graph_workflow_details(request, workflow_type):
    """Simple function-based view for workflow details."""
    return WorkflowDetailsView.as_view()(request, workflow_type=workflow_type)


def model_graph_relation_details(request, relation_type):
    """Simple function-based view for relation details."""
    return RelationDetailsView.as_view()(request, relation_type=relation_type)