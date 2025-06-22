"""
CSV Mapping External Ontology Views

This module contains views for external ontology configuration in the CSV mapping interface:
- Toggle ontology forms (ORCID, Wikidata, GND, VIAF, etc.)
- Save/remove ontology configurations
- Validate ontology identifiers

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View

from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class ToggleExternalOntologyFormView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Toggle external ontology configuration form view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for toggling external ontology forms."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id') or request.GET.get('column_id')
            
            logger.info(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
            
            # Get workspace columns using coordinator
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Find column using coordinator method
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                logger.error(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: Column '{column_id}' not found")
                return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
            
            # Get current external ontology configuration if exists
            external_ontology = column.get('external_ontology', {})
            ontology_type = external_ontology.get('ontology_type', '')
            uri_template = external_ontology.get('uri_template', '')
            identifier_pattern = external_ontology.get('identifier_pattern', '')
            validation_enabled = external_ontology.get('validation_enabled', True)
            
            # Define common ontology types with their templates and patterns
            ontology_presets = {
                'orcid': {
                    'name': 'ORCID',
                    'uri_template': 'https://orcid.org/{identifier}',
                    'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
                    'example': '0000-0002-1825-0097',
                    'description': 'ORCID researcher identifiers'
                },
                'wikidata': {
                    'name': 'Wikidata',
                    'uri_template': 'https://www.wikidata.org/entity/{identifier}',
                    'identifier_pattern': r'^Q\d+$',
                    'example': 'Q42',
                    'description': 'Wikidata entity IDs'
                },
                'gnd': {
                    'name': 'GND (German National Library)',
                    'uri_template': 'https://d-nb.info/gnd/{identifier}',
                    'identifier_pattern': r'^\d{8,9}[\dX]?$',
                    'example': '118501429',
                    'description': 'German National Library authority file'
                },
                'viaf': {
                    'name': 'VIAF',
                    'uri_template': 'https://viaf.org/viaf/{identifier}',
                    'identifier_pattern': r'^\d+$',
                    'example': '12347231',
                    'description': 'Virtual International Authority File'
                },
                'loc': {
                    'name': 'Library of Congress',
                    'uri_template': 'http://id.loc.gov/authorities/names/{identifier}',
                    'identifier_pattern': r'^[a-z]{1,2}\d{8,10}$',
                    'example': 'n80057250',
                    'description': 'Library of Congress Name Authority File'
                },
                'isni': {
                    'name': 'ISNI',
                    'uri_template': 'https://isni.org/isni/{identifier}',
                    'identifier_pattern': r'^\d{15}[\dX]$',
                    'example': '0000000121032683',
                    'description': 'International Standard Name Identifier'
                },
                
                # === VOCABULARIES / ONTOLOGIES ===
                'dublin_core': {
                    'name': 'Dublin Core Terms',
                    'uri_template': 'http://purl.org/dc/terms/{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'title',
                    'description': 'Dublin Core Metadata Terms vocabulary'
                },
                'foaf': {
                    'name': 'FOAF (Friend of a Friend)',
                    'uri_template': 'http://xmlns.com/foaf/0.1/{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'name',
                    'description': 'FOAF vocabulary for describing people and relationships'
                },
                'skos': {
                    'name': 'SKOS (Simple Knowledge Organization System)',
                    'uri_template': 'http://www.w3.org/2004/02/skos/core#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'prefLabel',
                    'description': 'SKOS vocabulary for organizing knowledge'
                },
                'schema_org': {
                    'name': 'Schema.org',
                    'uri_template': 'https://schema.org/{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Person',
                    'description': 'Schema.org structured data vocabulary'
                },
                'bibframe': {
                    'name': 'BIBFRAME',
                    'uri_template': 'http://id.loc.gov/ontologies/bibframe/{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Work',
                    'description': 'Bibliographic Framework vocabulary'
                },
                'dcat': {
                    'name': 'DCAT (Data Catalog Vocabulary)',
                    'uri_template': 'http://www.w3.org/ns/dcat#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Dataset',
                    'description': 'W3C Data Catalog vocabulary'
                },
                'prov': {
                    'name': 'PROV-O (Provenance Ontology)',
                    'uri_template': 'http://www.w3.org/ns/prov#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Activity',
                    'description': 'W3C Provenance ontology'
                },
                'void': {
                    'name': 'VoID (Vocabulary of Interlinked Datasets)',
                    'uri_template': 'http://rdfs.org/ns/void#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Dataset',
                    'description': 'Vocabulary for describing linked datasets'
                },
                'org': {
                    'name': 'ORG (Organization Ontology)',
                    'uri_template': 'http://www.w3.org/ns/org#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Organization',
                    'description': 'W3C Organization ontology'
                },
                'time': {
                    'name': 'OWL-Time',
                    'uri_template': 'http://www.w3.org/2006/time#{identifier}',
                    'identifier_pattern': r'^[a-zA-Z][a-zA-Z0-9_]*$',
                    'example': 'Instant',
                    'description': 'W3C Time ontology'
                },
                'custom': {
                    'name': 'Custom Ontology',
                    'uri_template': '',
                    'identifier_pattern': '',
                    'example': '',
                    'description': 'Custom ontology with user-defined template'
                }
            }
            
            context = {
                'column': column,
                'ontology_type': ontology_type,
                'uri_template': uri_template,
                'identifier_pattern': identifier_pattern,
                'validation_enabled': validation_enabled,
                'ontology_presets': ontology_presets,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE')
            }
            
            return render(request, 'csv_mapping/partials/inline_external_ontology_form.html', context)
            
        except Exception as e:
            logger.error(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: Error toggling form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error opening external ontology configuration</div>')


class SaveInlineExternalOntologyView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Save inline external ontology configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for saving external ontology configurations."""
        try:
            # Debug: Log all POST parameters
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: POST params: {dict(request.POST)}")
            
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract form data
            column_id = request.POST.get('column_id')
            ontology_type = request.POST.get('ontology_type')
            uri_template = request.POST.get('uri_template')
            identifier_pattern = request.POST.get('identifier_pattern')
            validation_enabled = request.POST.get('validation_enabled') == 'on'
            
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: column_id='{column_id}', type='{ontology_type}', template='{uri_template}', org='{organization_id}'")
            
            # Validate required fields
            if not all([column_id, ontology_type]):
                missing = []
                if not column_id: missing.append('column_id')
                if not ontology_type: missing.append('ontology_type')
                error_msg = f'Missing required fields: {", ".join(missing)}'
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # For custom ontology, require URI template
            if ontology_type == 'custom' and not uri_template:
                error_msg = 'URI template is required for custom ontologies'
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column with external ontology configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_external_ontology'] = True
                    col['external_ontology'] = {
                        'ontology_type': ontology_type,
                        'uri_template': uri_template,
                        'identifier_pattern': identifier_pattern,
                        'validation_enabled': validation_enabled,
                    }
                    updated_column = col
                    logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: ✅ Updated column '{column_id}' with external ontology config")
                    break
            
            if not updated_column:
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Successfully updated external ontology configuration")
            
            # Return just the updated column item using template helper
            column_html = self.render_column_item_template(request, organization_id, updated_column)
            
            return HttpResponse(column_html)
            
        except Exception as e:
            logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Error saving configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error saving external ontology configuration</div>')


class HideExternalOntologyFormView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Hide external ontology form view using coordinator-based architecture.
    """
    
    def get(self, request):
        """Handle GET requests for hiding external ontology forms."""
        try:
            column_id = request.GET.get('column_id')
            logger.info(f"CSV_HIDE_EXTERNAL_ONTOLOGY_FORM: column={column_id}")
            
            # Return empty div to hide the form (using slugified ID to match template)
            from django.utils.text import slugify
            slugified_id = slugify(column_id) if column_id else 'unknown'
            return HttpResponse(f'<div id="external-ontology-form-{slugified_id}"></div>')
            
        except Exception as e:
            logger.error(f"CSV_HIDE_EXTERNAL_ONTOLOGY_FORM: Error hiding form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error hiding external ontology form</div>')


class RemoveExternalOntologyView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Remove external ontology configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for removing external ontology configurations."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-xs p-2">Column ID required</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column to remove external ontology configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_external_ontology'] = False
                    col['external_ontology'] = {}
                    updated_column = col
                    logger.info(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: ✅ Removed external ontology config from column '{column_id}'")
                    break
            
            if not updated_column:
                logger.error(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            # Return updated workspace using template helper
            workspace_html = self.render_workspace_template(request, organization_id)
            
            return HttpResponse(workspace_html)
            
        except Exception as e:
            logger.error(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: Error removing configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error removing external ontology configuration</div>')


class ValidateExternalOntologyIdentifierView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Validate external ontology identifier view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for validating external ontology identifiers."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract validation data
            column_id = request.POST.get('column_id')
            identifier = request.POST.get('identifier')
            ontology_type = request.POST.get('ontology_type')
            identifier_pattern = request.POST.get('identifier_pattern')
            
            logger.info(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: column_id='{column_id}', type='{ontology_type}', identifier='{identifier}', org='{organization_id}'")
            
            if not all([column_id, identifier, ontology_type]):
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required fields for validation'
                })
            
            # Validate identifier format
            is_valid = True
            validation_message = ''
            
            if identifier_pattern:
                import re
                if not re.match(identifier_pattern, identifier):
                    is_valid = False
                    validation_message = f'Identifier does not match expected pattern for {ontology_type}'
                else:
                    validation_message = f'Valid {ontology_type} identifier format'
            else:
                validation_message = f'No validation pattern available for {ontology_type}'
            
            logger.info(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: Validation result - Valid: {is_valid}, Message: {validation_message}")
            
            return JsonResponse({
                'success': True,
                'is_valid': is_valid,
                'message': validation_message,
                'identifier': identifier,
                'ontology_type': ontology_type
            })
            
        except Exception as e:
            logger.error(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: Error validating identifier: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Error validating external ontology identifier'
            }) 