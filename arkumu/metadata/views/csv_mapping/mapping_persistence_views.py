"""
CSV Mapping Persistence Views

This module contains views for saving, loading, listing, and deleting 
CSV mapping configurations using the Mapping model.

These views are separated from the main CSV mapping editor views to 
keep the codebase organized and maintainable.
"""

import logging
from django.http import JsonResponse, HttpResponse
from django.views import View
from arkumu.metadata.models.mappings import Mapping, MappingType
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin

logger = logging.getLogger(__name__)


class SaveMappingView(CSVMappingCoordinatorMixin, View):
    """Save current mapping state to database"""
    
    def post(self, request):
        """Save current mapping configuration to Mapping model"""
        logger.info("SAVE_MAPPING: Starting save operation")
        
        try:
            # Get organization and mapping details from form
            organization_id = request.POST.get('organization')
            mapping_name = request.POST.get('mapping_name', '').strip()
            
            if not organization_id:
                return JsonResponse({'error': 'Organization ID is required'}, status=400)
            
            if not mapping_name:
                return JsonResponse({'error': 'Mapping name is required'}, status=400)
            
            # Check if mapping name already exists for this organization
            existing_mapping = Mapping.objects.filter(
                organization_id=organization_id,
                name=mapping_name
            ).first()
            
            if existing_mapping:
                return JsonResponse({
                    'error': f'Mapping "{mapping_name}" already exists. Choose a different name.'
                }, status=400)
            
            # Serialize current state
            mapping_config = self.serialize_current_mapping_state(
                request, organization_id, mapping_name
            )
            
            # Determine mapping type based on configuration
            mapping_type = self._determine_mapping_type(mapping_config)
            
            # Determine primary source dataset
            selected_datasets = mapping_config.get('selected_datasets', [])
            source_dataset = selected_datasets[0] if selected_datasets else 'unknown'
            
            # Create Mapping record
            mapping = Mapping.objects.create(
                name=mapping_name,
                mapping_type=mapping_type,
                scope='multi_dataset',
                organization_id=organization_id,
                source_dataset=source_dataset,
                mapping_config=mapping_config,
                created_by=getattr(request.user, 'username', 'anonymous'),
                validation_status='draft'
            )
            
            logger.info(f"SAVE_MAPPING: Successfully saved mapping '{mapping_name}' with ID {mapping.id}")
            
            return JsonResponse({
                'success': True,
                'mapping_id': str(mapping.id),
                'mapping_name': mapping_name,
                'message': f'Mapping "{mapping_name}" saved successfully'
            })
            
        except Exception as e:
            logger.error(f"SAVE_MAPPING: Error saving mapping: {str(e)}")
            return JsonResponse({
                'error': f'Failed to save mapping: {str(e)}'
            }, status=500)
    
    def _determine_mapping_type(self, mapping_config):
        """Determine appropriate mapping type based on configuration"""
        fk_relationships = mapping_config.get('fk_relationships', {})
        entity_mappings = mapping_config.get('entity_mappings', {})
        
        if fk_relationships:
            return MappingType.LOOKUP
        elif entity_mappings.get('predicate_mappings'):
            return MappingType.ENTITY
        else:
            return MappingType.ENTITY  # Default


class LoadMappingView(CSVMappingCoordinatorMixin, View):
    """Load existing mapping from database"""
    
    def post(self, request):
        """Load and restore mapping configuration from Mapping model"""
        logger.info("LOAD_MAPPING: Starting load operation")
        
        try:
            # Get parameters
            organization_id = request.POST.get('organization')
            mapping_id = request.POST.get('mapping_id')
            
            if not organization_id:
                return JsonResponse({'error': 'Organization ID is required'}, status=400)
                
            if not mapping_id:
                return JsonResponse({'error': 'Mapping ID is required'}, status=400)
            
            # Get mapping record
            try:
                mapping = Mapping.objects.get(
                    id=mapping_id,
                    organization_id=organization_id
                )
            except Mapping.DoesNotExist:
                return JsonResponse({
                    'error': f'Mapping with ID {mapping_id} not found for organization {organization_id}'
                }, status=404)
            
            # Validate compatibility before loading
            validation_result = self.validate_mapping_compatibility(
                request, organization_id, mapping.mapping_config
            )
            
            if not validation_result['is_valid']:
                return JsonResponse({
                    'error': 'Mapping is not compatible with current datasets',
                    'validation_errors': validation_result['errors'],
                    'missing_datasets': validation_result['missing_datasets']
                }, status=400)
            
            # Restore mapping state
            summary = self.deserialize_mapping_state(
                request, organization_id, mapping.mapping_config
            )
            
            logger.info(f"LOAD_MAPPING: Successfully loaded mapping '{mapping.name}' with ID {mapping.id}")
            
            # Return success response that triggers UI refresh
            response_data = {
                'success': True,
                'mapping_id': str(mapping.id),
                'mapping_name': mapping.name,
                'summary': summary,
                'message': f'Mapping "{mapping.name}" loaded successfully'
            }
            
            # Add validation warnings if any
            if validation_result['warnings']:
                response_data['warnings'] = validation_result['warnings']
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"LOAD_MAPPING: Error loading mapping: {str(e)}")
            return JsonResponse({
                'error': f'Failed to load mapping: {str(e)}'
            }, status=500)


class ListMappingsView(CSVMappingCoordinatorMixin, View):
    """List available mappings for organization"""
    
    def get(self, request):
        """Get list of mappings for organization"""
        logger.info("LIST_MAPPINGS: Starting list operation")
        
        try:
            organization_id = request.GET.get('organization')
            
            if not organization_id:
                return JsonResponse({'error': 'Organization ID is required'}, status=400)
            
            # Get mappings for organization
            mappings = Mapping.objects.filter(
                organization_id=organization_id
            ).order_by('-created_at')
            
            # Serialize mapping list
            mapping_list = []
            for mapping in mappings:
                metadata = mapping.mapping_config.get('metadata', {})
                mapping_list.append({
                    'id': str(mapping.id),
                    'name': mapping.name,
                    'mapping_type': mapping.get_mapping_type_display(),
                    'validation_status': mapping.get_validation_status_display(),
                    'created_at': mapping.created_at.isoformat(),
                    'created_by': mapping.created_by,
                    'source_dataset': mapping.source_dataset,
                    'total_datasets': metadata.get('total_datasets', 0),
                    'total_columns': metadata.get('total_columns', 0),
                    'total_fk_relationships': metadata.get('total_fk_relationships', 0),
                    'last_executed': mapping.last_executed.isoformat() if mapping.last_executed else None
                })
            
            logger.info(f"LIST_MAPPINGS: Found {len(mapping_list)} mappings for organization {organization_id}")
            
            # Check if this is an HTMX request for populating select dropdown
            if request.headers.get('HX-Request'):
                # Return HTML options for select dropdown
                options_html = '<option value="">Select a mapping...</option>'
                for mapping in mapping_list:
                    created_date = mapping['created_at'][:10] if mapping['created_at'] else 'Unknown'
                    datasets_info = f"{mapping['total_datasets']} datasets, {mapping['total_columns']} columns"
                    
                    options_html += f'''<option value="{mapping['id']}" 
                                               data-name="{mapping['name']}"
                                               data-type="{mapping['mapping_type']}"
                                               data-datasets="{mapping['total_datasets']}"
                                               data-columns="{mapping['total_columns']}"
                                               data-created="{created_date}">
                        {mapping['name']} ({datasets_info}) - {created_date}
                    </option>'''
                
                return HttpResponse(options_html)
            else:
                # Return JSON for API calls
                return JsonResponse({
                    'success': True,
                    'mappings': mapping_list,
                    'total_count': len(mapping_list)
                })
            
        except Exception as e:
            logger.error(f"LIST_MAPPINGS: Error listing mappings: {str(e)}")
            return JsonResponse({
                'error': f'Failed to list mappings: {str(e)}'
            }, status=500)


class DeleteMappingView(CSVMappingCoordinatorMixin, View):
    """Delete existing mapping"""
    
    def post(self, request):
        """Delete mapping from database"""
        logger.info("DELETE_MAPPING: Starting delete operation")
        
        try:
            organization_id = request.POST.get('organization')
            mapping_id = request.POST.get('mapping_id')
            
            if not organization_id:
                return JsonResponse({'error': 'Organization ID is required'}, status=400)
                
            if not mapping_id:
                return JsonResponse({'error': 'Mapping ID is required'}, status=400)
            
            # Get and delete mapping
            try:
                mapping = Mapping.objects.get(
                    id=mapping_id,
                    organization_id=organization_id
                )
                mapping_name = mapping.name
                mapping.delete()
                
                logger.info(f"DELETE_MAPPING: Successfully deleted mapping '{mapping_name}' with ID {mapping_id}")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Mapping "{mapping_name}" deleted successfully'
                })
                
            except Mapping.DoesNotExist:
                return JsonResponse({
                    'error': f'Mapping with ID {mapping_id} not found'
                }, status=404)
            
        except Exception as e:
            logger.error(f"DELETE_MAPPING: Error deleting mapping: {str(e)}")
            return JsonResponse({
                'error': f'Failed to delete mapping: {str(e)}'
            }, status=500) 