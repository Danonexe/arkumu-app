import logging
import json
import os
from typing import List
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.uploadedfile import UploadedFile
import time

from arkumu.storage.services.upload_service import UploadService
from arkumu.storage.services.bucket_service import BucketService

# Cache services to avoid repeated initialization
_upload_service = None
_bucket_service = None

def get_cached_upload_service():
    """Get cached upload service to avoid repeated initialization."""
    global _upload_service
    if _upload_service is None:
        logger.info("Initializing UploadService for the first time...")
        start_time = time.time()
        _upload_service = UploadService()
        init_duration = time.time() - start_time
        logger.info(f"UploadService initialized in {init_duration:.2f} seconds")
    else:
        logger.info("Using cached UploadService")
    return _upload_service

def get_cached_bucket_service():
    """Get cached bucket service to avoid repeated initialization."""
    global _bucket_service
    if _bucket_service is None:
        logger.info("Initializing BucketService for the first time...")
        start_time = time.time()
        _bucket_service = BucketService()
        init_duration = time.time() - start_time
        logger.info(f"BucketService initialized in {init_duration:.2f} seconds")
    else:
        logger.info("Using cached BucketService")
    return _bucket_service

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def streaming_upload_form(request):
    """
    Handle streaming file uploads through Django to S3.
    GET: Show the upload form
    POST: Process uploaded files
    """
    if request.method == 'GET':
        # Get optional organization parameter
        organization = request.GET.get('organization', '')
        return render(request, "upload/streaming_upload_form.html", {
            "organization": organization
        })
    
    # Handle POST request with file uploads
    logger.info(f"Processing streaming upload for user: {request.user.username}")
    
    # Get folder name
    folder_name = request.POST.get('folder_name', '').strip()
    if not folder_name:
        return JsonResponse({
            'success': False,
            'error': 'Folder name is required'
        }, status=400)
    
    # Get organization (if provided)
    organization = request.POST.get('organization', '').strip()
    
    # Get uploaded files
    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({
            'success': False,
            'error': 'No files were uploaded'
        }, status=400)
    
    try:
        # Get cached services to avoid repeated initialization
        upload_service = get_cached_upload_service()
        
        # Determine target bucket based on organization
        target_bucket = upload_service.ingest_bucket
        if organization:
            # Get the cached bucket service to resolve organization bucket
            bucket_service = get_cached_bucket_service()
            # Just get the bucket name without expensive existence checks
            target_bucket = bucket_service.get_organization_bucket(organization)
            logger.info(f"Using organization bucket: {target_bucket}")
        
        # Record start time
        start_time = time.time()
        
        # Process files with optimized method
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=files,
            path_prefix=folder_name,
            bucket_name=target_bucket
        )
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Add duration to result
        result['duration'] = f"{duration:.2f}"
        result['duration_seconds'] = duration
        
        # Log the result
        if result.get('success', False):
            logger.info(f"Successfully uploaded {len(files)} files to {folder_name} in {duration:.2f} seconds")
        else:
            logger.error(f"Failed to upload files: {result.get('error', 'Unknown error')}")
        
        return JsonResponse(result)
    
    except Exception as e:
        logger.exception(f"Error in streaming upload: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def streaming_upload_api(request):
    """
    API endpoint for streaming file uploads through Django to S3.
    This is for programmatic use by other applications.
    """
    try:
        # Parse JSON data if Content-Type is application/json
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            folder_name = data.get('folder_name', '').strip()
            organization = data.get('organization', '').strip()
        else:
            # Otherwise get from POST data
            folder_name = request.POST.get('folder_name', '').strip()
            organization = request.POST.get('organization', '').strip()
        
        if not folder_name:
            return JsonResponse({
                'success': False,
                'error': 'folder_name is required'
            }, status=400)
        
        # Get uploaded files
        files = request.FILES.getlist('files')
        if not files:
            return JsonResponse({
                'success': False,
                'error': 'No files were uploaded'
            }, status=400)
        
        # Initialize upload service
        upload_service = UploadService()
        
        # Determine target bucket based on organization
        target_bucket = upload_service.ingest_bucket
        if organization:
            # Get the bucket service to resolve organization bucket
            bucket_service = BucketService()
            # Ensure the organization bucket exists
            bucket_result = bucket_service.ensure_organization_bucket_exists(organization)
            if not bucket_result.get('success', False):
                return JsonResponse({
                    'success': False,
                    'error': f"Failed to create organization bucket: {bucket_result.get('error', 'Unknown error')}"
                }, status=500)
            target_bucket = bucket_service.get_organization_bucket(organization)
            logger.info(f"Using organization bucket: {target_bucket}")
        
        # Record start time
        start_time = time.time()
        
        # Process files with optimized method
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=files,
            path_prefix=folder_name,
            bucket_name=target_bucket
        )
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Add duration to result
        result['duration'] = f"{duration:.2f}"
        result['duration_seconds'] = duration
        
        # Log the result
        if result.get('success', False):
            logger.info(f"API: Successfully uploaded {len(files)} files to {folder_name} in {duration:.2f} seconds")
        else:
            logger.error(f"API: Failed to upload files: {result.get('error', 'Unknown error')}")
        
        return JsonResponse(result)
    
    except Exception as e:
        logger.exception(f"Error in streaming upload API: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def streaming_upload_single(request):
    """
    Upload a single file via streaming.
    """
    logger.info(f"Single file streaming upload for user: {request.user.username}")
    
    try:
        # Get parameters
        folder_name = request.POST.get('folder_name', '').strip()
        uploaded_file = request.FILES.get('file')
        
        if not uploaded_file:
            return JsonResponse({
                'success': False,
                'error': 'No file provided'
            }, status=400)
        
        logger.info(f"Uploading single file: {uploaded_file.name} to folder: {folder_name}")
        
        # Initialize upload service
        upload_service = UploadService()
        
        # Get file size to determine if we should use optimized settings
        file_size = uploaded_file.size if hasattr(uploaded_file, 'size') else None
        use_optimized = file_size and file_size > 5 * 1024 * 1024  # 5MB threshold
        
        # Upload the file with optimized settings for larger files
        if use_optimized:
            # Create a list with single file and use the optimized batch method
            result = upload_service.upload_batch_django_files_optimized(
                uploaded_files=[uploaded_file],
                path_prefix=folder_name,
                max_workers=1,
                multipart_threshold=5 * 1024 * 1024,  # 5MB threshold
                max_concurrency=10,                   # 10 threads for multipart
                multipart_chunksize=8 * 1024 * 1024   # 8MB chunk size
            )
            
            # Extract the single result
            if result['success'] and result['results']:
                single_result = result['results'][0]
                single_result['duration_seconds'] = result['duration_seconds']
                return JsonResponse(single_result)
            else:
                error = result.get('failures', [{}])[0].get('error', 'Upload failed') if result.get('failures') else 'Upload failed'
                return JsonResponse({
                    'success': False,
                    'error': error
                }, status=500)
        else:
            # Use regular upload for smaller files
            result = upload_service.upload_django_file(
                uploaded_file=uploaded_file,
                path_prefix=folder_name,
                use_multipart=True,
                multipart_threshold=10 * 1024 * 1024
            )
            
            if result['success']:
                logger.info(f"Successfully uploaded {result['file_name']} ({result['file_size_formatted']})")
                
                return JsonResponse({
                    'success': True,
                    'file_name': result['file_name'],
                    's3_key': result['s3_key'],
                    'file_size': result['file_size'],
                    'file_size_formatted': result['file_size_formatted'],
                    'content_type': result['content_type'],
                    'upload_type': result.get('upload_type', 'single')
                })
            else:
                logger.error(f"Failed to upload {uploaded_file.name}: {result.get('error')}")
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Upload failed')
                }, status=500)
            
    except Exception as e:
        logger.exception(f"Error in single file streaming upload: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def file_info(request):
    """
    Get information about a specific file in the bucket.
    """
    try:
        s3_key = request.GET.get('s3_key', '').strip()
        if not s3_key:
            return JsonResponse({
                'success': False,
                'error': 's3_key parameter is required'
            }, status=400)
        
        # Initialize upload service to get file info
        upload_service = UploadService()
        
        # Get file information
        result = upload_service.get_file_info(s3_key)
        
        return JsonResponse(result)
    
    except Exception as e:
        logger.exception(f"Error getting file info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def guess_content_type(filename: str) -> str:
    """
    Guess the content type based on file extension.
    """
    import mimetypes
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or 'application/octet-stream'


def format_file_size(size_bytes: int) -> str:
    """
    Format bytes to human-readable size.
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB" 