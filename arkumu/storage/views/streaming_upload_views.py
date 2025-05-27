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

from arkumu.storage.services.upload_service import UploadService

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
        return render(request, "upload/streaming_upload_form.html")
    
    # Handle POST request with file uploads
    logger.info(f"Processing streaming upload for user: {request.user.username}")
    
    # Get folder name
    folder_name = request.POST.get('folder_name', '').strip()
    if not folder_name:
        return JsonResponse({
            'success': False,
            'error': 'Folder name is required'
        }, status=400)
    
    # Get uploaded files
    uploaded_files = request.FILES.getlist('files')
    if not uploaded_files:
        return JsonResponse({
            'success': False,
            'error': 'No files were uploaded'
        }, status=400)
    
    logger.info(f"Received {len(uploaded_files)} files for upload to folder: {folder_name}")
    
    try:
        # Initialize upload service
        upload_service = UploadService()
        
        # Upload files using optimized parallel streaming
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=uploaded_files,
            path_prefix=folder_name,
            max_workers=min(20, len(uploaded_files)),  # Adjust workers based on file count
            multipart_threshold=10 * 1024 * 1024,      # 10MB threshold
            max_concurrency=10,                        # 10 threads per file for multipart
            multipart_chunksize=8 * 1024 * 1024        # 8MB chunk size
        )
        
        if result['success']:
            logger.info(f"Successfully uploaded {result['total_uploaded']} files in {result['duration_seconds']:.2f} seconds, "
                       f"total size: {result['total_size_formatted']}")
            
            # Return success response
            return JsonResponse({
                'success': True,
                'message': f"Successfully uploaded {result['total_uploaded']} files",
                'total_uploaded': result['total_uploaded'],
                'total_size': result['total_size_formatted'],
                'duration_seconds': result['duration_seconds'],
                'results': result['results']
            })
        else:
            logger.error(f"Batch upload partially failed: {result['total_failed']} failures out of {len(uploaded_files)} files")
            
            # Return partial success response
            return JsonResponse({
                'success': False,
                'error': f"Upload completed with {result['total_failed']} failures",
                'total_uploaded': result['total_uploaded'],
                'total_failed': result['total_failed'],
                'duration_seconds': result['duration_seconds'],
                'results': result['results'],
                'failures': result['failures']
            }, status=207)  # 207 Multi-Status
            
    except Exception as e:
        logger.exception(f"Error during streaming upload: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"Upload failed: {str(e)}"
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt  # Allow CSRF exemption for API-style uploads
def streaming_upload_api(request):
    """
    API endpoint for streaming file uploads.
    Accepts multipart/form-data with files and metadata.
    """
    logger.info(f"API streaming upload request from user: {request.user.username}")
    
    try:
        # Parse request data
        folder_name = request.POST.get('folder_name', '').strip()
        uploaded_files = request.FILES.getlist('files')
        
        # Validate inputs
        if not folder_name:
            return JsonResponse({
                'success': False,
                'error': 'folder_name is required'
            }, status=400)
        
        if not uploaded_files:
            return JsonResponse({
                'success': False,
                'error': 'No files provided'
            }, status=400)
        
        logger.info(f"API upload: {len(uploaded_files)} files to folder '{folder_name}'")
        
        # Initialize upload service
        upload_service = UploadService()
        
        # Upload files using optimized parallel streaming
        result = upload_service.upload_batch_django_files_optimized(
            uploaded_files=uploaded_files,
            path_prefix=folder_name,
            max_workers=min(20, len(uploaded_files)),  # Adjust workers based on file count
            multipart_threshold=10 * 1024 * 1024,      # 10MB threshold
            max_concurrency=10,                        # 10 threads per file for multipart
            multipart_chunksize=8 * 1024 * 1024        # 8MB chunk size
        )
        
        # Return structured response
        response_data = {
            'success': result['success'],
            'total_uploaded': result['total_uploaded'],
            'total_failed': result['total_failed'],
            'total_size': result['total_size'],
            'total_size_formatted': result['total_size_formatted'],
            'duration_seconds': result['duration_seconds'],
            'uploads': []
        }
        
        # Add successful uploads
        for upload_result in result['results']:
            response_data['uploads'].append({
                'file_name': upload_result['file_name'],
                's3_key': upload_result['s3_key'],
                'file_size': upload_result['file_size'],
                'file_size_formatted': upload_result['file_size_formatted'],
                'content_type': upload_result['content_type'],
                'upload_type': upload_result.get('upload_type', 'single')
            })
        
        # Add failures if any
        if result['failures']:
            response_data['failures'] = result['failures']
        
        status_code = 200 if result['success'] else 207
        return JsonResponse(response_data, status=status_code)
        
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
    Get information about an uploaded file.
    """
    s3_key = request.GET.get('s3_key')
    if not s3_key:
        return JsonResponse({
            'success': False,
            'error': 's3_key parameter is required'
        }, status=400)
    
    try:
        upload_service = UploadService()
        result = upload_service.get_file_info(s3_key)
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.exception(f"Error getting file info for {s3_key}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def guess_content_type(filename: str) -> str:
    """
    Guess the content type based on file extension.
    
    Args:
        filename: The filename to analyze
        
    Returns:
        str: The guessed MIME type
    """
    # Get file extension
    ext = os.path.splitext(filename.lower())[1]
    
    # Common MIME types
    mime_types = {
        '.txt': 'text/plain',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.svg': 'image/svg+xml',
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.wmv': 'video/x-ms-wmv',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
        '.tar': 'application/x-tar',
        '.gz': 'application/gzip',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.csv': 'text/csv',
        '.html': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
    }
    
    return mime_types.get(ext, 'application/octet-stream')


def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    # Define size units
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)
    unit_index = 0
    
    # Find the appropriate unit
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    # Format with appropriate precision
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.2f} {units[unit_index]}" 