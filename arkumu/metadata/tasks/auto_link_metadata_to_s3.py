import logging
from typing import Dict, Any, Optional
from uuid import UUID
import os

# Huey imports
from huey.contrib.djhuey import db_task, task, db_periodic_task
# Try importing configured Huey instance, fallback to default djhuey
try:
    from arkumu.config.huey import HUEY as arkumu_huey_instance
except ImportError:
    from config.settings.base import HUEY as arkumu_huey_instance 

from django.db import transaction
from django.core.cache import cache
from django.utils import timezone

# from arkumu.metadata.services.mapping.map_resources_to_files import FileResourceMatcherService, MatchingConfig # Not used anymore
from arkumu.storage.models import S3FileObject
from arkumu.metadata.models import Resource

logger = logging.getLogger(__name__) # Use this logger for all task-related logging


@db_task(retries=1, retry_delay=60)
def auto_link_all_files_task(
    organization: Optional[str] = None, 
    status_filter: Optional[str] = None,
    task_id_for_cache: Optional[str] = None
) -> Dict[str, Any]:
    """
    Huey task to automatically link unlinked S3 files to metadata resources.
    Uses the same simple direct linking approach as manual linking.
    
    Args:
        organization: Filter by organization (optional)
        status_filter: Filter by link status (optional)  
        task_id_for_cache: Explicit task ID for caching (optional)
    
    Returns:
        Dict with results: processed_count, linked_count, ambiguous_count, error_count, success
    """
    actual_task_id = task_id_for_cache
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(auto_link_all_files_task, 'request') and auto_link_all_files_task.request.id:
        actual_task_id = auto_link_all_files_task.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for auto-link. Status polling may not work.")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache(status: str, message: str, progress: int, details: Optional[Dict] = None, error_type: Optional[str] = None):
        if cache_key:
            payload = {"status": status, "message": message, "progress": progress}
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
            cache.set(cache_key, payload, timeout=3600)

    update_cache("processing", "Starting auto-link process...", 5)
    
    logger.info(f"Task {actual_task_id or 'UnknownID'}: Starting auto-link task for organization: {organization}, status_filter: {status_filter}")
    
    try:
        # Get files to process - same logic as the view
        queryset = S3FileObject.objects.filter(s3_key__startswith='data/')
        
        # Apply organization filter if specified
        if organization and organization.lower() != 'all':
            queryset = queryset.filter(session__s3_bucket=organization)
        
        # Apply status filter - for auto-link, we typically want unlinked files
        if status_filter == 'linked':
            queryset = queryset.filter(related_resource__isnull=False)
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Filtered to linked files only")
        else:
            # Default: only process unlinked files for auto-linking
            queryset = queryset.filter(related_resource__isnull=True)
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Processing unlinked files only")
        
        total_files = queryset.count()
        update_cache("processing", f"Found {total_files} files to process...", 10)
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Found {total_files} files to process")
        
        # Simple linking logic - same as manual linking
        processed_count = 0
        linked_count = 0
        ambiguous_count = 0
        error_count = 0
        
        update_cache("processing", f"Processing {total_files} files...", 20)
        
        # Process files in batches for better performance
        batch_size = 100
        
        # TODO: Implement the actual matching logic here
        # For now, just iterate through files and show the process
        for file in queryset.iterator(chunk_size=batch_size):
            processed_count += 1
            
            try:
                # TODO: Replace this with actual matching logic
                # This is where we need to determine which resource to link to
                # Options:
                # 1. Simple filename matching (strip extension, find Resource with matching value)
                # 2. More sophisticated matching based on metadata
                # 3. User-configured matching rules
                
                # For now, let's implement simple filename matching like manual linking would do
                file_name_without_extension = file.file_name.rsplit('.', 1)[0] if '.' in file.file_name else file.file_name
                
                # Try to find a resource with matching value (case-insensitive)
                matching_resources = Resource.objects.filter(value__iexact=file_name_without_extension)
                
                if matching_resources.count() == 1:
                    # Single match - link it (same as manual linking)
                    resource = matching_resources.first()
                    file.related_resource = resource
                    file.save()
                    linked_count += 1
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: Linked file {file.id} to resource {resource.id}")
                elif matching_resources.count() > 1:
                    # Multiple matches - ambiguous
                    ambiguous_count += 1
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: Multiple resources found for file {file.id}")
                else:
                    # No match found
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: No resource found for file {file.id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error processing file {file.id}: {e}")
            
            # Update progress
            if processed_count % 50 == 0:
                progress = min(20 + (processed_count / total_files * 60), 80)
                update_cache("processing", f"Processed {processed_count}/{total_files} files...", int(progress))
        
        update_cache("processing", f"Finalizing auto-link process...", 80)
        
        # Calculate success metrics
        success_rate = (linked_count / processed_count * 100) if processed_count > 0 else 0
        
        result = {
            'success': True,
            'processed_count': processed_count,
            'linked_count': linked_count,
            'ambiguous_count': ambiguous_count,
            'error_count': error_count,
            'success_rate': round(success_rate, 2),
            'organization': organization,
            'status_filter': status_filter,
            'task_id': actual_task_id
        }
        
        success_message = (
            f"Auto-link completed for {organization or 'all organizations'}. "
            f"Processed: {processed_count}, Linked: {linked_count}, Ambiguous: {ambiguous_count}, Errors: {error_count}."
        )
        update_cache("completed", success_message, 100, details=result)
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Auto-link task completed successfully: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Auto-link task failed: {str(e)}"
        logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}", exc_info=True)
        
        update_cache("failed", error_msg, 0, error_type=type(e).__name__)
        
        return {
            'success': False,
            'error': error_msg,
            'processed_count': 0,
            'linked_count': 0,
            'ambiguous_count': 0,
            'error_count': 0,
            'organization': organization,
            'status_filter': status_filter,
            'task_id': actual_task_id
        }


@db_task(retries=1, retry_delay=60)
def batch_link_selected_files_task(
    file_ids: list, 
    task_id_for_cache: Optional[str] = None
) -> Dict[str, Any]:
    """
    Huey task to link specific selected S3 files to metadata resources.
    Uses the same simple direct linking approach as manual linking.
    
    Args:
        file_ids: List of S3FileObject UUID IDs (as strings) to process
        task_id_for_cache: Explicit task ID for caching (optional)
    
    Returns:
        Dict with results: processed_count, linked_count, ambiguous_count, error_count, success
    """
    actual_task_id = task_id_for_cache
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(batch_link_selected_files_task, 'request') and batch_link_selected_files_task.request.id:
        actual_task_id = batch_link_selected_files_task.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for batch link: {len(file_ids)} files. Status polling may not work.")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache(status: str, message: str, progress: int, details: Optional[Dict] = None, error_type: Optional[str] = None):
        if cache_key:
            payload = {"status": status, "message": message, "progress": progress}
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
            cache.set(cache_key, payload, timeout=3600)

    update_cache("processing", f"Starting batch link for {len(file_ids)} files...", 5)
    
    logger.info(f"Task {actual_task_id or 'UnknownID'}: Starting batch link task for {len(file_ids)} files")
    
    try:
        from arkumu.storage.models import S3FileObject
        from arkumu.metadata.models import Resource
        from django.db import transaction
        
        # Validate and convert UUIDs if needed
        import uuid as uuid_module
        validated_ids = []
        for fid in file_ids:
            try:
                # Ensure it's a valid UUID and convert to proper format
                uuid_obj = uuid_module.UUID(fid)
                validated_ids.append(uuid_obj)
            except ValueError:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Invalid UUID format: {fid}")
                continue
        
        if not validated_ids:
            error_msg = "No valid file IDs provided"
            update_cache("failed", error_msg, 0, error_type="ValidationError")
            return {
                'success': False,
                'error': error_msg,
                'processed_count': 0,
                'linked_count': 0,
                'ambiguous_count': 0,
                'error_count': len(file_ids),
                'requested_files': len(file_ids),
                'task_id': actual_task_id
            }
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Validated {len(validated_ids)} UUIDs")
        
        # Get the specific files using UUID lookup
        queryset = S3FileObject.objects.filter(
            id__in=validated_ids,
            related_resource__isnull=True  # Only process unlinked files
        )
        
        actual_count = queryset.count()
        if actual_count != len(validated_ids):
            logger.warning(f"Task {actual_task_id or 'UnknownID'}: Requested {len(validated_ids)} files but found {actual_count} unlinked files")
        
        update_cache("processing", f"Processing {actual_count} selected files...", 10)
        
        # Simple linking logic - same as manual linking
        processed_count = 0
        linked_count = 0
        ambiguous_count = 0
        error_count = 0
        
        update_cache("processing", f"Matching files to resources...", 20)
        
        # Process each file with the same simple logic as manual linking
        for file in queryset:
            processed_count += 1
            
            try:
                # Use the same simple matching logic as auto-link
                file_name_without_extension = file.file_name.rsplit('.', 1)[0] if '.' in file.file_name else file.file_name
                
                # Try to find a resource with matching value (case-insensitive)
                matching_resources = Resource.objects.filter(value__iexact=file_name_without_extension)
                
                if matching_resources.count() == 1:
                    # Single match - link it (same as manual linking)
                    resource = matching_resources.first()
                    file.related_resource = resource
                    file.save()
                    linked_count += 1
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: Linked file {file.id} to resource {resource.id}")
                elif matching_resources.count() > 1:
                    # Multiple matches - ambiguous
                    ambiguous_count += 1
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: Multiple resources found for file {file.id}")
                else:
                    # No match found
                    logger.info(f"Task {actual_task_id or 'UnknownID'}: No resource found for file {file.id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error processing file {file.id}: {e}")
            
            # Update progress
            if processed_count % 10 == 0:
                progress = min(20 + (processed_count / actual_count * 60), 80)
                update_cache("processing", f"Processed {processed_count}/{actual_count} files...", int(progress))
        
        update_cache("processing", f"Finalizing batch link process...", 80)
        
        # Calculate success metrics
        success_rate = (linked_count / processed_count * 100) if processed_count > 0 else 0
        
        result = {
            'success': True,
            'processed_count': processed_count,
            'linked_count': linked_count,
            'ambiguous_count': ambiguous_count,
            'error_count': error_count,
            'success_rate': round(success_rate, 2),
            'requested_files': len(file_ids),
            'actual_files': actual_count,
            'task_id': actual_task_id
        }
        
        success_message = (
            f"Batch link completed. "
            f"Processed: {processed_count}, Linked: {linked_count}, Ambiguous: {ambiguous_count}, Errors: {error_count}."
        )
        update_cache("completed", success_message, 100, details=result)
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Batch link task completed successfully: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Batch link task failed: {str(e)}"
        logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}", exc_info=True)
        
        update_cache("failed", error_msg, 0, error_type=type(e).__name__)
        
        return {
            'success': False,
            'error': error_msg,
            'processed_count': 0,
            'linked_count': 0,
            'ambiguous_count': 0,
            'error_count': 0,
            'requested_files': len(file_ids),
            'task_id': actual_task_id
        }


@db_task(retries=1, retry_delay=60)
def discover_and_sync_s3_bucket_task(
    bucket_name: str, 
    prefix: str = "", 
    task_id_for_cache: Optional[str] = None
) -> Dict[str, Any]:
    """
    Huey task to discover and sync files from S3 bucket to database.
    
    Args:
        bucket_name: S3 bucket name
        prefix: S3 prefix/folder path (optional)
        task_id_for_cache: Explicit task ID for caching (optional)
    
    Returns:
        Dict with results: synced_count, created_count, skipped_count, error_count, success
    """
    actual_task_id = task_id_for_cache
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(discover_and_sync_s3_bucket_task, 'request') and discover_and_sync_s3_bucket_task.request.id:
        actual_task_id = discover_and_sync_s3_bucket_task.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for S3 discovery: {bucket_name}/{prefix}. Status polling may not work.")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache(status: str, message: str, progress: int, details: Optional[Dict] = None, error_type: Optional[str] = None):
        if cache_key:
            payload = {"status": status, "message": message, "progress": progress}
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
            cache.set(cache_key, payload, timeout=3600)

    update_cache("processing", f"Starting S3 discovery for {bucket_name}/{prefix or '(root)'}...", 5)
    
    logger.info(f"Task {actual_task_id or 'UnknownID'}: Starting S3 discovery task for bucket '{bucket_name}', prefix '{prefix}'")
    
    try:
        # Create custom logger for the service
        def task_logger(message: str):
            logger.info(f"[Task {actual_task_id or 'UnknownID'}] {message}")
        
        # Configure the service
        config = MatchingConfig(
            batch_size=1000,
            timeout_seconds=900,  # 15 minutes
            log_progress_every=100
        )
        
        # Initialize the service
        matcher_service = FileResourceMatcherService(
            logger_func=task_logger,
            config=config
        )
        
        update_cache("processing", f"Discovering files in {bucket_name}/{prefix or '(root)'}...", 10)
        
        # Perform the discovery and sync
        synced_count, created_count, skipped_count, error_count = matcher_service.discover_and_sync_s3_files(
            bucket_name=bucket_name,
            prefix=prefix
        )
        
        update_cache("processing", f"Finalizing S3 discovery process...", 80)
        
        total_processed = synced_count + created_count + skipped_count + error_count
        
        result = {
            'success': True,
            'synced_count': synced_count,
            'created_count': created_count,
            'skipped_count': skipped_count,
            'error_count': error_count,
            'total_processed': total_processed,
            'bucket_name': bucket_name,
            'prefix': prefix,
            'task_id': actual_task_id
        }
        
        success_message = (
            f"S3 discovery completed for {bucket_name}/{prefix or '(root)'}. "
            f"Synced: {synced_count}, Created: {created_count}, Skipped: {skipped_count}, Errors: {error_count}."
        )
        update_cache("completed", success_message, 100, details=result)
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: S3 discovery task completed successfully: {result}")
        return result
        
    except Exception as e:
        error_msg = f"S3 discovery task failed: {str(e)}"
        logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}", exc_info=True)
        
        update_cache("failed", error_msg, 0, error_type=type(e).__name__)
        
        return {
            'success': False,
            'error': error_msg,
            'synced_count': 0,
            'created_count': 0,
            'skipped_count': 0,
            'error_count': 0,
            'bucket_name': bucket_name,
            'prefix': prefix,
            'task_id': actual_task_id
        }
