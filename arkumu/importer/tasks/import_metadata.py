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
from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy, BulkUpdateStats
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
    upload_session_id: Optional[UUID] = None, # Added ingest_session_id (keeping param name for compatibility)
    # New mapping parameters
    mapping_id: Optional[str] = None,
    use_mapping: bool = False,
    use_table_services: bool = False
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
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Cache updated - Key: {cache_key}, Status: {status}, Message: {message[:50]}...")
        else:
            logger.warning(f"Task {actual_task_id or 'UnknownID'}: Cannot update cache - cache_key is None")

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
        f"IngestSession ID: {upload_session_id}. Cache key: {cache_key}"
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
        
        # Handle mapping configuration if provided
        mapping_config = None
        if use_mapping and mapping_id:
            try:
                from arkumu.metadata.models import Mapping
                from arkumu.metadata.services.mapping_consumer.mapping_adapter import MappingAdapter
                
                update_cache("processing", f"Loading mapping configuration...", 25)
                
                # Load the mapping
                mapping = Mapping.objects.get(id=mapping_id)
                adapter = MappingAdapter()
                mapping_config = adapter.translate_to_execution_config(mapping_id)
                
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Using mapping '{mapping.name}' (ID: {mapping_id})")
                
            except Exception as e:
                logger.warning(f"Task {actual_task_id or 'UnknownID'}: Failed to load mapping {mapping_id}: {e}")
                update_cache("processing", f"Warning: Failed to load mapping, using entity-based import", 30)
        
        # Choose import method based on configuration
        if use_table_services or (use_mapping and mapping_config):
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Using table-based services with mapping")
            stats: BulkUpdateStats = ImportWorkflowService.import_csv_with_table_services(
                csv_path=temp_local_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                auto_mapping=True,
                session_dict={'mapping_config': mapping_config} if mapping_config else None
            )
        else:
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Using standard import workflow")
            stats: BulkUpdateStats = ImportWorkflowService.import_csv(
                csv_path=temp_local_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                link_row_cells=link_row_cells,
                link_to_first_column=link_to_first_column,
                use_smart_updater=True,
                use_polars=True,
                update_strategy=update_strategy,
                use_table_services=use_table_services
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
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Updated cache with 'completed' status. Cache key: {cache_key}")
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

@db_task(retries=1, retry_delay=60)
def run_csv_directory_import_workflow(
    s3_bucket_name: str,
    s3_folder_prefix: str,
    dataset_name: str,
    institution: str,
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = True,
    link_row_cells: bool = True,
    link_to_first_column: bool = False,
    use_smart_updater: bool = False,
    use_polars: bool = False,
    update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
    relationship_config_json: Optional[Dict] = None,
    file_columns: Optional[Dict[str, List[str]]] = None,
    timestamp_column: Optional[str] = None,
    task_id_for_cache: Optional[str] = None,
    upload_session_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Huey task to import all CSV files from an S3 folder using ImportWorkflowService.import_csv_directory().
    The task downloads all CSV files from the S3 folder to a local temporary directory before processing.
    It updates its status in Django's cache, updates the corresponding IngestSession,
    and cleans up the temporary files.

    Args:
        s3_bucket_name: Name of the S3 bucket where the CSV files are located.
        s3_folder_prefix: The S3 folder prefix (path) containing the CSV files.
        dataset_name: Base name to assign to the datasets being imported.
        institution: Identifier for the institution owning the data.
        base_uri: Base URI for generating resource URIs.
        delimiter: Character used as a delimiter in the CSV files.
        has_quoted_fields: Boolean indicating if fields in CSV are quoted.
        link_row_cells: Whether to create links between cells of the same row.
        link_to_first_column: Specific linking strategy for row links.
        use_smart_updater: Whether to use smart bulk updater for processing.
        use_polars: Whether to use Polars-optimized version for better performance.
        update_strategy: The strategy to use for handling existing data.
        relationship_config_json: JSON configuration for relationship handling between files.
        file_columns: Dict mapping dataset names to file column lists.
        timestamp_column: Column name for timestamp-based updates.
        task_id_for_cache: Explicit task ID for caching.
        upload_session_id: ID of the IngestSession to update.

    Returns:
        A dictionary containing the status of the import and aggregate statistics.
    """
    actual_task_id = task_id_for_cache
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(run_csv_directory_import_workflow, 'request') and run_csv_directory_import_workflow.request.id:
        actual_task_id = run_csv_directory_import_workflow.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for CSV directory import: {dataset_name}, S3 folder: {s3_bucket_name}/{s3_folder_prefix}. Status polling may not work.")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache(status: str, message: str, progress: int, details: Optional[Dict] = None, error_type: Optional[str] = None):
        if cache_key:
            payload = {"status": status, "message": message, "progress": progress}
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
            cache.set(cache_key, payload, timeout=3600)
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Cache updated - Key: {cache_key}, Status: {status}, Message: {message[:50]}...")
        else:
            logger.warning(f"Task {actual_task_id or 'UnknownID'}: Cannot update cache - cache_key is None")

    # Update IngestSession helper
    def update_upload_session_status(status: str, message: Optional[str] = None, files_processed: int = 0, errors_count: int = 0):
        if upload_session_id:
            try:
                session = IngestSession.objects.get(id=upload_session_id)
                session.status = status
                session.completed_at = timezone.now()
                if message:
                    session.error_message = message[:1024]
                if status == 'completed':
                    session.successful_rows = files_processed # Track number of files processed
                    session.failed_rows = errors_count
                elif status == 'failed':
                    session.failed_rows = 1
                session.save()
            except IngestSession.DoesNotExist:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: IngestSession with ID {upload_session_id} not found for update.")
            except Exception as e_us:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error updating IngestSession {upload_session_id}: {e_us}", exc_info=True)

    update_cache("processing", f"Starting directory import for {dataset_name} from S3 folder: {s3_bucket_name}/{s3_folder_prefix}...", 5)

    logger.info(
        f"Task {actual_task_id or 'UnknownID'}: Starting CSV directory import workflow for dataset '{dataset_name}' "
        f"from S3 folder '{s3_bucket_name}/{s3_folder_prefix}' for institution '{institution}'. "
        f"Smart updater: {use_smart_updater}, Strategy: {update_strategy.name if use_smart_updater else 'N/A'}. "
        f"IngestSession ID: {upload_session_id}. Cache key: {cache_key}"
    )
    
    temp_directory_path = None
    final_aggregate_stats = {}

    try:
        bucket_service = BucketService()

        # Create a temporary directory for downloading all CSV files
        temp_directory_path = tempfile.mkdtemp(prefix='arkumu_csv_directory_import_')
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Created temporary directory: {temp_directory_path}")

        update_cache("processing", "Discovering CSV files in S3 folder...", 10)

        # List all objects in the S3 folder with CSV extension
        s3_client = bucket_service.base_s3_service.s3_client
        
        # Ensure folder prefix ends with / if it's not empty
        if s3_folder_prefix and not s3_folder_prefix.endswith('/'):
            s3_folder_prefix += '/'
        
        # List objects in the S3 folder
        response = s3_client.list_objects_v2(
            Bucket=s3_bucket_name,
            Prefix=s3_folder_prefix
        )
        
        if 'Contents' not in response:
            raise ValueError(f"No files found in S3 folder {s3_bucket_name}/{s3_folder_prefix}")
        
        # Filter for CSV files only
        csv_objects = [
            obj for obj in response['Contents']
            if obj['Key'].lower().endswith('.csv') and obj['Size'] > 0
        ]
        
        if not csv_objects:
            raise ValueError(f"No CSV files found in S3 folder {s3_bucket_name}/{s3_folder_prefix}")
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Found {len(csv_objects)} CSV files in S3 folder")
        for obj in csv_objects:
            logger.info(f"  - {obj['Key']} ({obj['Size']} bytes)")

        update_cache("processing", f"Downloading {len(csv_objects)} CSV files from S3...", 20)

        # Download all CSV files to the temporary directory
        downloaded_files = []
        for i, obj in enumerate(csv_objects):
            s3_object_key = obj['Key']
            filename = os.path.basename(s3_object_key)
            local_file_path = os.path.join(temp_directory_path, filename)
            
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Downloading file {i+1}/{len(csv_objects)}: {s3_object_key}")
            
            try:
                s3_client.download_file(s3_bucket_name, s3_object_key, local_file_path)
                downloaded_files.append(local_file_path)
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully downloaded {filename}")
            except Exception as download_error:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Failed to download {s3_object_key}: {download_error}")
                raise download_error
            
            # Update progress during download
            download_progress = 20 + (30 * (i + 1) / len(csv_objects))
            update_cache("processing", f"Downloaded {i+1}/{len(csv_objects)} files...", int(download_progress))

        logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully downloaded all {len(downloaded_files)} CSV files to {temp_directory_path}")

        update_cache("processing", f"Processing {len(downloaded_files)} CSV files...", 50)

        # Save relationship config to a temporary file if provided
        relationship_config_path = None
        if relationship_config_json:
            import json
            relationship_config_path = os.path.join(temp_directory_path, 'relationship_config.json')
            with open(relationship_config_path, 'w') as f:
                json.dump(relationship_config_json, f)
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Saved relationship config to {relationship_config_path}")

        # Call the directory import service
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Starting ImportWorkflowService.import_csv_directory() on {temp_directory_path}")
        
        # Start processing with initial progress
        import threading
        import time
        
        # Progress tracking for long-running import
        processing_complete = False
        def update_processing_progress():
            """Background thread to update progress during long directory processing"""
            progress_start = 55  # Start after download phase
            progress_end = 85    # End before finalization
            elapsed_time = 0
            estimated_total_time = len(downloaded_files) * 30  # Estimate 30 seconds per file
            
            while not processing_complete and elapsed_time < estimated_total_time * 2:  # Max 2x estimated time
                time.sleep(10)  # Update every 10 seconds
                elapsed_time += 10
                
                if not processing_complete:
                    # Calculate progress based on time elapsed
                    time_progress = min(elapsed_time / estimated_total_time, 0.9)  # Cap at 90%
                    current_progress = int(progress_start + (progress_end - progress_start) * time_progress)
                    
                    update_cache(
                        "processing", 
                        f"Processing {len(downloaded_files)} CSV files... ({elapsed_time//60}m {elapsed_time%60}s elapsed)",
                        current_progress,
                        details={"csv_files_found": len(csv_objects), "csv_files_downloaded": len(downloaded_files)}
                    )
        
        # Start progress thread
        progress_thread = threading.Thread(target=update_processing_progress, daemon=True)
        progress_thread.start()
        
        try:
            aggregate_stats = ImportWorkflowService.import_csv_directory(
                directory_path=temp_directory_path,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                relationship_config_path=relationship_config_path,
                file_columns=file_columns,
                files_base_directory=temp_directory_path,
                upload_service=None,
                link_row_cells=link_row_cells,
                link_to_first_column=link_to_first_column,
                use_smart_updater=use_smart_updater,
                use_polars=use_polars,
                update_strategy=update_strategy,
                timestamp_column=timestamp_column
            )
        finally:
            # Stop the progress thread
            processing_complete = True
        
        update_cache("processing", f"Finalizing directory import for {dataset_name}...", 90)

        # Prepare final statistics
        final_aggregate_stats = {
            "files_processed": aggregate_stats.get("files_processed", 0),
            "resources_created": aggregate_stats.get("resources_created", 0),
            "triples_created": aggregate_stats.get("triples_created", 0),
            "row_links_created": aggregate_stats.get("row_links_created", 0),
            "files_uploaded": aggregate_stats.get("files_uploaded", 0),
            "upload_errors": aggregate_stats.get("upload_errors", 0),
            "errors": aggregate_stats.get("errors", 0),
            "csv_files_found": len(csv_objects),
            "csv_files_downloaded": len(downloaded_files)
        }
        
        success_message = (
            f"Directory '{dataset_name}' (from S3 folder {s3_folder_prefix}) imported successfully. "
            f"Processed: {final_aggregate_stats['files_processed']} files. "
            f"Created: {final_aggregate_stats['resources_created']} resources, {final_aggregate_stats['triples_created']} triples. "
            f"Errors: {final_aggregate_stats['errors']}."
        )
        
        update_cache("completed", success_message, 100, details=final_aggregate_stats)
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Updated cache with 'completed' status. Cache key: {cache_key}")
        
        update_upload_session_status(
            'completed', 
            success_message, 
            final_aggregate_stats['files_processed'], 
            final_aggregate_stats['errors']
        )
        
        logger.info(
            f"Task {actual_task_id or 'UnknownID'}: CSV directory import workflow for dataset '{dataset_name}' "
            f"(from S3 folder {s3_folder_prefix}) completed successfully. "
            f"Files processed: {final_aggregate_stats['files_processed']}, "
            f"Resources created: {final_aggregate_stats['resources_created']}, "
            f"Triples created: {final_aggregate_stats['triples_created']}, "
            f"Errors: {final_aggregate_stats['errors']}"
        )
        
        return {
            "status": "success",
            "dataset_name": dataset_name,
            "s3_folder_prefix": s3_folder_prefix,
            **final_aggregate_stats
        }
        
    except Exception as e:
        error_message = f"Error importing directory '{dataset_name}' from S3 folder {s3_bucket_name}/{s3_folder_prefix}: {str(e)}"
        logger.error(
            f"Task {actual_task_id or 'UnknownID'}: Error during CSV directory import workflow for dataset '{dataset_name}' "
            f"from S3 folder '{s3_bucket_name}/{s3_folder_prefix}': {e}",
            exc_info=True
        )
        update_cache("failed", error_message, 0, error_type=type(e).__name__)
        update_upload_session_status('failed', error_message)
        return {
            "status": "error",
            "dataset_name": dataset_name,
            "s3_folder_prefix": s3_folder_prefix,
            "error_message": str(e),
            "error_type": type(e).__name__
        }
    finally:
        # Clean up the temporary directory and all downloaded files
        if temp_directory_path and os.path.exists(temp_directory_path):
            try:
                import shutil
                shutil.rmtree(temp_directory_path)
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully deleted temporary directory {temp_directory_path}")
            except OSError as e_cleanup:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error deleting temporary directory {temp_directory_path}: {e_cleanup}")
        elif temp_directory_path:
            logger.warning(f"Task {actual_task_id or 'UnknownID'}: Temporary directory {temp_directory_path} not found for deletion.")



