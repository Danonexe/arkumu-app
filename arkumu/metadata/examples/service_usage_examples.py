"""
Service Usage Examples

Examples showing how to use the semantic transformation services
in both Django views and REST API endpoints.
"""

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from ..services import get_services_for_request, get_services_for_api
from ..services.mapping_configuration import PatternType, MappingType


# ================================
# Django View Examples
# ================================

def analyze_csv_view(request):
    """Django view to analyze a CSV file"""
    if request.method == 'POST':
        # Get services configured for this request (with session storage)
        services = get_services_for_request(request)
        
        # Get file path from form data
        file_path = request.POST.get('file_path')
        
        try:
            # Use the table analysis service
            analysis_result = services['table_analysis'].analyze_csv_file(file_path)
            
            # Store analysis in session for later use
            request.session['last_analysis'] = {
                'file_path': file_path,
                'table_type': analysis_result.table_type,
                'quality_score': analysis_result.quality_score
            }
            
            context = {
                'analysis': analysis_result,
                'suggestions': analysis_result.suggestions,
                'columns': analysis_result.columns
            }
            
            return render(request, 'metadata/analysis_results.html', context)
            
        except Exception as e:
            return render(request, 'metadata/error.html', {'error': str(e)})
    
    return render(request, 'metadata/analyze_form.html')


def create_mapping_rule_view(request):
    """Django view to create a mapping rule"""
    if request.method == 'POST':
        services = get_services_for_request(request)
        mapping_service = services['mapping_configuration']
        
        # Get form data
        rule_name = request.POST.get('rule_name')
        pattern_type = request.POST.get('pattern_type')
        pattern_value = request.POST.get('pattern_value')
        target_fields = request.POST.getlist('target_fields')
        semantic_type = request.POST.get('semantic_type')
        
        try:
            # Create pattern rule
            pattern_rule = mapping_service.create_pattern_rule(
                name=f"{rule_name}_pattern",
                pattern_type=pattern_type,
                pattern_value=pattern_value,
                target_fields=target_fields
            )
            
            # Create mapping rule
            mapping_rule = mapping_service.create_mapping_rule(
                name=rule_name,
                pattern_rule=pattern_rule,
                mapping_type='type_assignment',
                target_semantic_type=semantic_type
            )
            
            # Get or create active configuration
            active_config = mapping_service.get_active_configuration()
            if not active_config:
                active_config = mapping_service.create_configuration(
                    name="Default Configuration"
                )
            
            # Add rule to configuration
            mapping_service.add_mapping_rule_to_configuration(
                active_config.id, mapping_rule
            )
            
            return JsonResponse({
                'success': True,
                'rule_id': mapping_rule.id,
                'message': 'Mapping rule created successfully'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


def preview_transformation_view(request):
    """Django view to preview a transformation"""
    if request.method == 'POST':
        services = get_services_for_request(request)
        preview_service = services['preview']
        
        file_path = request.POST.get('file_path')
        
        try:
            # Get active configuration
            mapping_service = services['mapping_configuration']
            active_config = mapping_service.get_active_configuration()
            
            if not active_config:
                return JsonResponse({
                    'error': 'No active configuration found'
                }, status=400)
            
            # Preview transformation
            preview_result = preview_service.preview_dataset_transformation(
                dataset_path=file_path,
                configuration_id=active_config.id
            )
            
            context = {
                'preview_result': preview_result,
                'summary': preview_result.summary,
                'sample_changes': preview_result.changes[:10],
                'impact_analysis': preview_result.impact_analysis
            }
            
            return render(request, 'metadata/preview_results.html', context)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# ================================
# REST API Examples
# ================================

@api_view(['POST'])
def analyze_csv_api(request):
    """REST API endpoint to analyze a CSV file"""
    # Get services configured for API use (no session storage)
    services = get_services_for_api()
    
    file_path = request.data.get('file_path')
    sample_size = request.data.get('sample_size', 1000)
    
    if not file_path:
        return Response({
            'error': 'file_path is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Use the table analysis service
        analysis_result = services['table_analysis'].analyze_csv_file(
            file_path, sample_size
        )
        
        # Convert to JSON-serializable format
        return Response({
            'filename': analysis_result.filename,
            'table_type': analysis_result.table_type,
            'row_count': analysis_result.row_count,
            'column_count': analysis_result.column_count,
            'quality_score': analysis_result.quality_score,
            'suggestions': analysis_result.suggestions,
            'primary_key_candidates': analysis_result.primary_key_candidates,
            'foreign_key_candidates': analysis_result.foreign_key_candidates,
            'columns': [
                {
                    'name': col.name,
                    'data_type': col.data_type,
                    'unique_count': col.unique_count,
                    'null_count': col.null_count,
                    'patterns': col.patterns,
                    'semantic_hints': col.semantic_hints
                }
                for col in analysis_result.columns
            ]
        })
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
def mapping_configurations_api(request):
    """REST API endpoint to manage mapping configurations"""
    services = get_services_for_api()
    mapping_service = services['mapping_configuration']
    
    if request.method == 'GET':
        # List all configurations
        configurations = mapping_service.list_configurations()
        return Response({'configurations': configurations})
    
    elif request.method == 'POST':
        # Create new configuration
        name = request.data.get('name')
        description = request.data.get('description', '')
        
        if not name:
            return Response({
                'error': 'name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            config = mapping_service.create_configuration(name, description)
            return Response({
                'id': config.id,
                'name': config.name,
                'description': config.description,
                'created_at': config.created_at
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_mapping_rule_api(request):
    """REST API endpoint to create a mapping rule"""
    services = get_services_for_api()
    mapping_service = services['mapping_configuration']
    
    # Extract data
    config_id = request.data.get('configuration_id')
    rule_name = request.data.get('rule_name')
    pattern_data = request.data.get('pattern_rule', {})
    semantic_type = request.data.get('target_semantic_type')
    
    # Validate required fields
    required_fields = ['configuration_id', 'rule_name', 'target_semantic_type']
    for field in required_fields:
        if not request.data.get(field):
            return Response({
                'error': f'{field} is required'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Create pattern rule
        pattern_rule = mapping_service.create_pattern_rule(
            name=pattern_data.get('name', f"{rule_name}_pattern"),
            pattern_type=pattern_data.get('pattern_type', 'prefix'),
            pattern_value=pattern_data.get('pattern_value', ''),
            target_fields=pattern_data.get('target_fields', ['uri'])
        )
        
        # Create mapping rule
        mapping_rule = mapping_service.create_mapping_rule(
            name=rule_name,
            pattern_rule=pattern_rule,
            mapping_type='type_assignment',
            target_semantic_type=semantic_type
        )
        
        # Add to configuration
        success = mapping_service.add_mapping_rule_to_configuration(
            config_id, mapping_rule
        )
        
        if success:
            return Response({
                'rule_id': mapping_rule.id,
                'message': 'Mapping rule created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Configuration not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def preview_transformation_api(request):
    """REST API endpoint to preview a transformation"""
    services = get_services_for_api()
    preview_service = services['preview']
    
    file_path = request.data.get('file_path')
    config_id = request.data.get('configuration_id')
    sample_size = request.data.get('sample_size', 100)
    
    if not file_path or not config_id:
        return Response({
            'error': 'file_path and configuration_id are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        preview_result = preview_service.preview_dataset_transformation(
            dataset_path=file_path,
            configuration_id=config_id,
            sample_size=sample_size
        )
        
        return Response({
            'summary': {
                'total_changes': preview_result.summary.total_changes,
                'changes_by_type': preview_result.summary.changes_by_type,
                'entities_affected': preview_result.summary.entities_affected,
                'relationships_affected': preview_result.summary.relationships_affected,
                'estimated_duration': preview_result.summary.estimated_duration,
                'potential_issues': preview_result.summary.potential_issues,
                'recommendations': preview_result.summary.recommendations
            },
            'sample_changes': [
                {
                    'change_type': change.change_type.value,
                    'target_id': change.target_id,
                    'description': change.description,
                    'confidence': change.confidence
                }
                for change in preview_result.changes[:10]  # First 10 changes
            ],
            'impact_analysis': preview_result.impact_analysis,
            'validation_preview': preview_result.validation_preview,
            'metadata': preview_result.metadata
        })
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def execute_pipeline_api(request):
    """REST API endpoint to execute a transformation pipeline"""
    services = get_services_for_api()
    pipeline_service = services['processing_pipeline']
    
    dataset_paths = request.data.get('dataset_paths', [])
    config_id = request.data.get('configuration_id')
    options_data = request.data.get('options', {})
    
    if not dataset_paths or not config_id:
        return Response({
            'error': 'dataset_paths and configuration_id are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Create processing options
        from ..services.processing_pipeline import ProcessingOptions
        options = ProcessingOptions(
            dry_run=options_data.get('dry_run', False),
            parallel_processing=options_data.get('parallel_processing', True),
            max_workers=options_data.get('max_workers', 4),
            validate_during_processing=options_data.get('validate_during_processing', True),
            output_format=options_data.get('output_format', 'turtle')
        )
        
        # Execute pipeline
        execution_id = pipeline_service.execute_pipeline(
            dataset_paths=dataset_paths,
            configuration_id=config_id,
            options=options
        )
        
        return Response({
            'execution_id': execution_id,
            'message': 'Pipeline execution started'
        }, status=status.HTTP_202_ACCEPTED)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def pipeline_status_api(request, execution_id):
    """REST API endpoint to check pipeline execution status"""
    services = get_services_for_api()
    pipeline_service = services['processing_pipeline']
    
    try:
        status_info = pipeline_service.get_execution_status(execution_id)
        
        if status_info:
            return Response(status_info)
        else:
            return Response({
                'error': 'Execution not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ================================
# Usage in Class-Based Views
# ================================

from django.views import View

class SemanticTransformationView(View):
    """Example class-based view using the services"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.services = None
    
    def dispatch(self, request, *args, **kwargs):
        # Initialize services for this request
        self.services = get_services_for_request(request)
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        """Handle semantic transformation request"""
        try:
            # Use services
            file_path = request.POST.get('file_path')
            
            # Step 1: Analyze
            analysis = self.services['table_analysis'].analyze_csv_file(file_path)
            
            # Step 2: Preview
            config = self.services['mapping_configuration'].get_active_configuration()
            if config:
                preview = self.services['preview'].preview_dataset_transformation(
                    file_path, config.id
                )
                
                return JsonResponse({
                    'analysis': {
                        'table_type': analysis.table_type,
                        'quality_score': analysis.quality_score,
                        'suggestions': analysis.suggestions
                    },
                    'preview': {
                        'total_changes': preview.summary.total_changes,
                        'entities_affected': preview.summary.entities_affected,
                        'recommendations': preview.summary.recommendations
                    }
                })
            else:
                return JsonResponse({
                    'error': 'No active configuration found'
                }, status=400)
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500) 