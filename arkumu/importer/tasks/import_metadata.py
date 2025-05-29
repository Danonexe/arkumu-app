import logging
from typing import List, Dict, Optional, Tuple, Set, Any
from uuid import UUID
import os
import tempfile # Added for temporary file creation in the task

# Huey imports
from huey.contrib.djhuey import db_task, task, db_periodic_task
# Try importing configured Huey instance, fallback to default djhuey
# This mirrors the pattern in lacos/lacos/ingest/tasks.py for consistency
try:
    # Assuming arkumu might have a similar central huey config in the future
    # For now, this will likely use the except block if 'arkumu.config.huey' doesn't exist.
    from arkumu.config.huey import HUEY as arkumu_huey_instance
except ImportError:
    # Fallback to the HUEY instance presumably configured for djhuey globally, 
    # often imported from settings or a central djhuey config.
    # If config.settings.base.HUEY is the one djhuey uses by default, 
    # then @db_task() will pick it up automatically.
    from config.settings.base import HUEY as arkumu_huey_instance 
    # If huey is imported here, it represents the default instance djhuey should be using.
    # Thus, it should not be passed explicitly to @db_task.

# Arkumu specific imports
from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy, BulkUpdateStats
from arkumu.storage.services.bucket_service import BucketService # Added to download S3 file

# Django cache
from django.core.cache import cache
from arkumu.importer.models import IngestSession # Import IngestSession instead of UploadSession
from django.utils import timezone # To set completion time

logger = logging.getLogger(__name__)

@db_task(retries=1, retry_delay=60)
def run_csv_import_workflow(
    # csv_path: str, # Removed: task will download its own file
    s3_bucket_name: str, # Added
    s3_object_key: str,  # Added
    dataset_name: str,
    institution: str,
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = True,
    link_row_cells: bool = True,
    link_to_first_column: bool = False,
    update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
    task_id_for_cache: Optional[str] = None,
    upload_session_id: Optional[UUID] = None # Added ingest_session_id (keeping param name for compatibility)
) -> Dict[str, Any]:
    """
    Huey task to import a CSV file using the ImportWorkflowService.
    The task now downloads the CSV from S3 to a local temporary file before processing.
    It updates its status in Django's cache, updates the corresponding IngestSession,
    and cleans up the temporary file.

    Args:
        s3_bucket_name: Name of the S3 bucket where the CSV file is located.
        s3_object_key: The S3 object key (path) for the CSV file.
        dataset_name: Name to assign to the dataset being imported.
        institution: Identifier for the institution owning the data.
        base_uri: Base URI for generating resource URIs.
        delimiter: Character used as a delimiter in the CSV file.
        has_quoted_fields: Boolean indicating if fields in CSV are quoted.
        link_row_cells: Whether to create links between cells of the same row.
        link_to_first_column: Specific linking strategy (maps to SmartBulkUpdater's topology via WorkflowService).
        update_strategy: The strategy to use for handling existing data (e.g., SKIP_EXISTING, UPDATE_VALUES).
        task_id_for_cache: Explicit task ID for caching.
        upload_session_id: ID of the IngestSession to update (keeping param name for compatibility).

    Returns:
        A dictionary containing the status of the import and key statistics.
    """
    actual_task_id = task_id_for_cache  # Prioritize the custom task ID for consistent polling
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(run_csv_import_workflow, 'request') and run_csv_import_workflow.request.id:
        actual_task_id = run_csv_import_workflow.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for CSV import: {dataset_name}, S3 key: {s3_object_key}. Status polling may not work.")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache(status: str, message: str, progress: int, details: Optional[Dict] = None, error_type: Optional[str] = None):
        if cache_key:
            payload = {"status": status, "message": message, "progress": progress}
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
            cache.set(cache_key, payload, timeout=3600)

    # Update IngestSession helper (updated from UploadSession)
    def update_upload_session_status(status: str, message: Optional[str] = None, files_processed: int = 0, errors_count: int = 0):
        if upload_session_id:
            try:
                session = IngestSession.objects.get(id=upload_session_id)
                session.status = status
                session.completed_at = timezone.now()
                if message:
                    session.error_message = message[:1024] # Using error_message field from IngestSession
                if status == 'completed':
                    session.successful_rows = files_processed # Track successful rows instead of files processed
                    session.failed_rows = errors_count
                elif status == 'failed':
                    session.failed_rows = 1 # Or a more specific count if available
                session.save()
            except IngestSession.DoesNotExist:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: IngestSession with ID {upload_session_id} not found for update.")
            except Exception as e_us:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error updating IngestSession {upload_session_id}: {e_us}", exc_info=True)

    update_cache("processing", f"Starting import for {dataset_name} from S3: {s3_bucket_name}/{s3_object_key}...", 5)

    logger.info(
        f"Task {actual_task_id or 'UnknownID'}: Starting CSV import workflow for dataset '{dataset_name}' "
        f"from S3 object '{s3_bucket_name}/{s3_object_key}' for institution '{institution}'. Strategy: {update_strategy.name}. "
        f"IngestSession ID: {upload_session_id}"
    )
    
    temp_local_path = None # To store the path of the downloaded temp file
    final_stats_dict = {}

    try:
        bucket_service = BucketService() # Instantiate service for S3 ops

        # Create a temporary file for downloading the CSV
        # The file will be created in the Huey worker's /tmp directory (or OS default)
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as temp_file_obj:
            temp_local_path = temp_file_obj.name
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Downloading S3 object {s3_bucket_name}/{s3_object_key} to temporary file {temp_local_path}")
        update_cache("processing", f"Downloading file {os.path.basename(s3_object_key)}...", 10)

        bucket_service.base_s3_service.s3_client.download_file(
            s3_bucket_name, 
            s3_object_key, 
            temp_local_path
        )
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully downloaded to {temp_local_path}")

        update_cache("processing", f"Processing downloaded file {os.path.basename(temp_local_path)} for {dataset_name}...", 20)
        
        stats: BulkUpdateStats = ImportWorkflowService.import_csv(
            csv_path=temp_local_path, # Use the new local temp path
            dataset_name=dataset_name,
            institution=institution.upper(),
            base_uri=base_uri,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields,
            link_row_cells=link_row_cells,
            link_to_first_column=link_to_first_column,
            use_smart_updater=True,
            update_strategy=update_strategy
        )
        
        update_cache("processing", f"Finalizing import for {dataset_name}...", 80)

        # The 'stats' variable here is the dictionary returned by ImportWorkflowService,
        # and the actual BulkUpdateStats fields are in a nested dictionary under the key "stats".
        actual_stats_data = stats.get("stats", {}) 

        final_stats_dict = {
            "rows_processed": actual_stats_data.get("rows_processed", 0),
            "cells_processed": actual_stats_data.get("cells_processed", 0),
            "resources_created": actual_stats_data.get("resources_created", 0),
            "resources_updated": actual_stats_data.get("resources_updated", 0),
            "resources_skipped": actual_stats_data.get("resources_skipped", 0),
            "triples_created": actual_stats_data.get("triples_created", 0),
            "triples_updated": actual_stats_data.get("triples_updated", 0),
            "triples_skipped": actual_stats_data.get("triples_skipped", 0),
            # "row_links_created": actual_stats_data.get("row_links_created", 0), # This might not be in smart_updater stats, check SmartBulkUpdater return
            "errors": actual_stats_data.get("errors", 0),
            # "truncated_values": actual_stats_data.get("truncated_values", 0) # This might not be in smart_updater stats
        }
        
        success_message = (
            f"Dataset '{dataset_name}' (from S3 object {s3_object_key}) imported successfully. "
            f"Processed: {actual_stats_data.get('rows_processed', 0)} rows. "
            f"Created: {actual_stats_data.get('resources_created', 0)} resources, {actual_stats_data.get('triples_created', 0)} triples."
            f" Errors: {actual_stats_data.get('errors', 0)}."
        )
        update_cache("completed", success_message, 100, details=final_stats_dict)
        update_upload_session_status('completed', success_message, 1, final_stats_dict['errors']) # 1 file processed
        
        logger.info(
            f"Task {actual_task_id or 'UnknownID'}: CSV import workflow for dataset '{dataset_name}' (from S3 object {s3_object_key}) completed successfully. "
            f"Stats - Rows: {actual_stats_data.get('rows_processed', 0)}, Resources Created: {actual_stats_data.get('resources_created', 0)}, "
            f"Triples Created: {actual_stats_data.get('triples_created', 0)}, Errors: {actual_stats_data.get('errors', 0)}"
        )
        
        return {
            "status": "success",
            "dataset_name": dataset_name,
            "s3_object_key": s3_object_key, # For reference
            **final_stats_dict
        }
        
    except Exception as e:
        error_message = f"Error importing dataset '{dataset_name}' from S3 object {s3_bucket_name}/{s3_object_key}: {str(e)}"
        logger.error(
            f"Task {actual_task_id or 'UnknownID'}: Error during CSV import workflow for dataset '{dataset_name}' from S3 object '{s3_bucket_name}/{s3_object_key}': {e}",
            exc_info=True
        )
        update_cache("failed", error_message, 0, error_type=type(e).__name__)
        update_upload_session_status('failed', error_message)
        return {
            "status": "error",
            "dataset_name": dataset_name,
            "s3_object_key": s3_object_key,
            "error_message": str(e),
            "error_type": type(e).__name__
        }
    finally:
        # Clean up the temporary file created by this task
        if temp_local_path and os.path.exists(temp_local_path):
            try:
                os.unlink(temp_local_path)
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully deleted temporary file {temp_local_path} created by task.")
            except OSError as e_unlink:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error deleting temporary file {temp_local_path} created by task: {e_unlink}")
        elif temp_local_path: # If path was set but file doesn't exist (e.g. download failed before file fully written)
             logger.warning(f"Task {actual_task_id or 'UnknownID'}: Temporary file {temp_local_path} (intended for task use) not found for deletion.")



