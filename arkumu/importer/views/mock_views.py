"""
Mock views for testing HTMX progress displays without actual imports.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from arkumu.importer.services.progress_cache import ProgressCacheService
from arkumu.importer.models import IngestSession
from arkumu.users.models import Organization
import logging
import time
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)


@login_required
def mock_test_interface(request):
    """Display the mock test interface."""
    return render(request, 'importer/mock_test_interface.html')


@login_required
@require_http_methods(["POST"])
def start_mock_import(request):
    """Start a mock import simulation for testing views."""
    try:
        # Get first available organization
        org = Organization.objects.first()
        if not org:
            return HttpResponse('<div class="alert alert-error">No organization available</div>', status=400)
        
        # Check if we should simulate an error
        simulate_error = request.POST.get('simulate_error', 'false').lower() == 'true'
        
        # Create a mock session
        session = IngestSession.objects.create(
            user=request.user,
            organization=org,
            status='pending',
            dataset_name='Mock Production Import Test',
            file_paths=[
                'arbeitsverhaeltnis.csv',
                'person.csv', 
                'projekt.csv',
                'organisationseinheit.csv',
                'adresse.csv',
                'ereignis.csv'
            ],
            base_uri='http://test.arkumu.org/data'
        )
        
        # Initialize progress cache with realistic starting data
        progress_cache = ProgressCacheService()
        progress_cache.update_progress(str(session.pk), {
            'status': 'started',
            'message': 'Mock import simulation started',
            'percentage': 0,
            'processed': 0,
            'total': 50000,  # Realistic total based on real test data
            'phase': 'initialization',
            'datasets_found': 35,
            'columns_mapped': 337,
            'fk_relationships': 72,
            'mock_mode': True,
            'simulate_error': simulate_error,
            'phase_start_time': time.time()
        })
        
        # Return progress display template
        return render(request, 'importer/partials/progress_display_polling.html', {
            'session': session,
            'should_poll': True,
            'is_mock': True
        })
        
    except Exception as e:
        logger.error(f"Error starting mock import: {e}")
        return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>', status=500)


@login_required
def mock_import_progress(request, session_pk):
    """Mock version of import_progress_view that simulates realistic progress."""
    try:
        session = get_object_or_404(IngestSession, pk=session_pk)
        
        if session.user != request.user:
            return HttpResponse('<div class="alert alert-error">Unauthorized</div>', status=403)
        
        # Get current progress from cache
        progress_cache = ProgressCacheService()
        current_progress = progress_cache.get_progress(str(session_pk))
        
        if not current_progress:
            # If no progress data, return completed state
            progress_data = {
                'status': 'completed',
                'message': 'Mock import completed',
                'percentage': 100,
                'processed': 50000,
                'total': 50000,
                'mock_mode': True
            }
            should_poll = False
        else:
            # Simulate progress advancement
            progress_data = simulate_progress_advancement(current_progress)
            progress_cache.update_progress(str(session_pk), progress_data)
            should_poll = progress_data.get('status') not in ['completed', 'failed']
        
        return render(request, 'importer/partials/progress_display_polling.html', {
            'session': session,
            'progress_data': progress_data,
            'should_poll': should_poll,
            'is_mock': True
        })
        
    except Exception as e:
        logger.error(f"Error in mock progress view: {e}")
        return HttpResponse('<div class="alert alert-error">Error retrieving progress</div>', status=500)


def simulate_progress_advancement(current_progress: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate realistic progress advancement based on current state."""
    
    # Define realistic phases with durations (in seconds)
    phases = [
        {'name': 'initialization', 'duration': 5, 'description': 'Initializing mapping-aware import'},
        {'name': 'mapping_load', 'duration': 10, 'description': 'Loading and translating mapping configuration'},
        {'name': 'data_preparation', 'duration': 15, 'description': 'Preparing CSV data sources'},
        {'name': 'mapping_aware_processing', 'duration': 30, 'description': 'Processing with MappingAwareProcessor'},
        {'name': 'finalization', 'duration': 8, 'description': 'Finalizing mapping-aware import'}
    ]
    
    current_phase = current_progress.get('phase', 'initialization')
    phase_start_time = current_progress.get('phase_start_time', time.time())
    simulate_error = current_progress.get('simulate_error', False)
    
    # Find current phase index
    current_phase_idx = 0
    for i, phase in enumerate(phases):
        if phase['name'] == current_phase:
            current_phase_idx = i
            break
    
    # Calculate elapsed time in current phase
    elapsed_in_phase = time.time() - phase_start_time
    phase_duration = phases[current_phase_idx]['duration']
    
    # Check if we should simulate an error (in processing phase)
    if simulate_error and current_phase == 'mapping_aware_processing' and elapsed_in_phase > 10:
        error_messages = [
            "Mapping validation failed: Column 'person_id' not found in arbeitsverhaeltnis.csv",
            "Foreign key constraint violation: Invalid reference to organisationseinheit",
            "CSV parsing error: Invalid character in line 1247 of projekt.csv"
        ]
        import random
        error_message = random.choice(error_messages)
        
        return {
            'status': 'failed',
            'message': f'Import failed: {error_message}',
            'percentage': max(30, current_progress.get('percentage', 0)),
            'processed': current_progress.get('processed', 0),
            'total': current_progress.get('total', 50000),
            'error': error_message,
            'mock_mode': True
        }
    
    # Calculate progress within current phase
    phase_progress = min(100, (elapsed_in_phase / phase_duration) * 100)
    
    # Calculate overall progress
    phase_weight = 100 / len(phases)
    overall_progress = (current_phase_idx * phase_weight) + (phase_progress * phase_weight / 100)
    
    # Calculate processed rows based on phase
    total_rows = current_progress.get('total', 50000)
    if current_phase_idx <= 2:  # Pre-processing phases
        processed_rows = 0
    elif current_phase == 'mapping_aware_processing':
        processed_rows = int((phase_progress / 100) * total_rows)
    else:  # Finalization
        processed_rows = total_rows
    
    progress_data = {
        'status': 'processing',
        'message': phases[current_phase_idx]['description'],
        'percentage': int(overall_progress),
        'processed': processed_rows,
        'total': total_rows,
        'phase': current_phase,
        'phase_progress': int(phase_progress),
        'current_phase': current_phase_idx + 1,
        'total_phases': len(phases),
        'datasets_processed': min(current_phase_idx * 7, 35),
        'resources_created': processed_rows * 2,
        'triples_created': processed_rows * 5,
        'mock_mode': True,
        'simulate_error': simulate_error,
        'phase_start_time': phase_start_time
    }
    
    # Check if we should advance to next phase
    if phase_progress >= 100:
        if current_phase_idx < len(phases) - 1:
            # Move to next phase
            next_phase = phases[current_phase_idx + 1]
            progress_data['phase'] = next_phase['name']
            progress_data['message'] = next_phase['description']
            progress_data['phase_start_time'] = time.time()
            progress_data['phase_progress'] = 0
        else:
            # Completed
            progress_data['status'] = 'completed'
            progress_data['message'] = 'Mock import completed successfully'
            progress_data['percentage'] = 100
            progress_data['processed'] = total_rows
    
    return progress_data