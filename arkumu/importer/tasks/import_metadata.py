"""
Enhanced Import Metadata Tasks

This module provides Huey tasks for CSV import with enhanced mapping integration support.
The tasks now support:

1. Mapping-driven imports with MappingAdapter integration
2. Automatic execution strategy selection
3. File-to-dataset validation and matching
4. Enhanced error handling and progress tracking
5. Backward compatibility with existing API

Key Features:
- run_csv_import_workflow_with_mapping: Enhanced task with mapping support
- run_csv_import_workflow: Legacy wrapper for backward compatibility
- Execution strategies: auto, mapping_driven, entity_centric
- File validation against mapping requirements
- Enhanced progress tracking with mapping-aware status updates
"""

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
from arkumu.importer.services.orchestrator.import_orchestrator import ImportOrchestrator
from arkumu.common.enums import UpdateStrategy
from arkumu.common.data_types import BulkUpdateStats
from arkumu.common.import_service_bridge import bridge_service
from arkumu.storage.services.bucket_service import BucketService # Added to download S3 file

# Django cache
from django.core.cache import cache
from arkumu.importer.models import IngestSession # Import IngestSession instead of UploadSession
from django.utils import timezone # To set completion time

# Import progress estimation
from arkumu.importer.services.progress import progress_estimator, ExecutionStrategy

logger = logging.getLogger(__name__)

@db_task(retries=1, retry_delay=60)
def run_mapping_aware_import_workflow(
    s3_bucket_name: str,
    s3_object_key: str,
    dataset_name: str,
    institution: str,
    mapping_id: str,
    base_uri: str = "http://arkumu.org/data",
    task_id_for_cache: Optional[str] = None,
    upload_session_id: Optional[UUID] = None,
    csv_sources: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Mapping-aware Huey task that implements the full production integration workflow
    from test_00_full_integration.py. This task processes CSV files using the
    MappingAwareProcessor with real execution config and CSV data.

    Args:
        s3_bucket_name: Name of the S3 bucket where the CSV file is located
        s3_object_key: The S3 object key (path) for the CSV file
        dataset_name: Name to assign to the dataset being imported
        institution: Identifier for the institution owning the data
        mapping_id: ID of the mapping configuration to use (required)
        base_uri: Base URI for generating resource URIs
        task_id_for_cache: Explicit task ID for caching
        upload_session_id: ID of the IngestSession to update
        csv_sources: Optional pre-loaded CSV data sources

    Returns:
        A dictionary containing the status of the import and execution metrics
    """
    actual_task_id = task_id_for_cache
    
    if not actual_task_id and hasattr(run_mapping_aware_import_workflow, 'request') and run_mapping_aware_import_workflow.request.id:
        actual_task_id = run_mapping_aware_import_workflow.request.id
    
    if not actual_task_id:
        logger.warning(f"Task ID for caching not available for mapping-aware import: {dataset_name}, S3 key: {s3_object_key}")
    
    cache_key = f"task_status_{actual_task_id}" if actual_task_id else None

    def update_cache_with_phase_info(status: str, message: str, progress: int, 
                                   phase_info: Optional[Dict] = None, 
                                   details: Optional[Dict] = None, 
                                   error_type: Optional[str] = None):
        if cache_key:
            payload = {
                "status": status,
                "message": message,
                "progress": progress,
                "timestamp": timezone.now().isoformat()
            }
            
            if phase_info:
                payload["phase_info"] = phase_info
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
                
            cache.set(cache_key, payload, timeout=3600)
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Cache updated - Status: {status}, Message: {message[:50]}...")

    def update_upload_session_status(status: str, message: Optional[str] = None, files_processed: int = 0, errors_count: int = 0):
        if upload_session_id:
            try:
                session = IngestSession.objects.get(id=upload_session_id)
                session.status = status
                session.completed_at = timezone.now()
                if message:
                    session.error_message = message[:1024]
                if status == 'completed':
                    session.successful_rows = files_processed
                    session.failed_rows = errors_count
                elif status == 'failed':
                    session.failed_rows = 1
                session.save()
            except IngestSession.DoesNotExist:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: IngestSession with ID {upload_session_id} not found")
            except Exception as e:
                logger.error(f"Task {actual_task_id or 'UnknownID'}: Error updating IngestSession {upload_session_id}: {e}")

    # Initialize mapping-aware phases
    mapping_phases = [
        "initialization",
        "mapping_load",
        "data_preparation", 
        "mapping_aware_processing",
        "finalization"
    ]
    
    def get_mapping_phase_info(phase_name: str, phase_progress: int = 0) -> Dict:
        try:
            phase_index = mapping_phases.index(phase_name)
        except ValueError:
            phase_index = 0
        
        return {
            "current_phase": phase_name,
            "current_phase_index": phase_index,
            "total_phases": len(mapping_phases),
            "phase_progress": phase_progress,
            "phase_description": get_mapping_phase_description(phase_name),
            "execution_strategy": "mapping_aware"
        }
    
    def get_mapping_phase_description(phase_name: str) -> str:
        descriptions = {
            "initialization": "Initializing mapping-aware import",
            "mapping_load": "Loading and translating mapping configuration",
            "data_preparation": "Preparing CSV data sources",
            "mapping_aware_processing": "Processing with MappingAwareProcessor",
            "finalization": "Finalizing mapping-aware import"
        }
        return descriptions.get(phase_name, "Processing")
    
    logger.info(
        f"Task {actual_task_id or 'UnknownID'}: Starting mapping-aware import workflow for dataset '{dataset_name}' "
        f"from S3 object '{s3_bucket_name}/{s3_object_key}' with mapping ID '{mapping_id}' for institution '{institution}'"
    )
    
    final_metrics = {}

    try:
        # Phase 1: Initialization
        phase_info = get_mapping_phase_info("initialization", 100)
        update_cache_with_phase_info("processing", f"Starting mapping-aware import for {dataset_name}...", 5, phase_info)
        
        # Phase 2: Load and translate mapping using MappingAdapter
        phase_info = get_mapping_phase_info("mapping_load", 25)
        update_cache_with_phase_info("processing", "Loading mapping configuration...", 15, phase_info)
        
        from arkumu.metadata.models import Mapping
        from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
        from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
        from arkumu.importer.services.execution.statistics import ExecutionStatistics
        from arkumu.importer.services.mapping_consumer.config_translator import ProcessingStrategy
        
        # Ensure mapping exists
        mapping = Mapping.objects.get(id=mapping_id)
        mapping_adapter = MappingAdapter()
        
        # Load and translate mapping using the automated system from test
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Loading mapping: ID={mapping.id}, Name={mapping.name}")
        
        execution_config = mapping_adapter.translate_to_execution_config(mapping_id)
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Loaded execution config with {len(execution_config.datasets)} datasets")
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Total columns: {sum(len(ds.columns) for ds in execution_config.datasets)}")
        logger.info(f"Task {actual_task_id or 'UnknownID'}: FK relationships: {len(execution_config.fk_relationships)}")
        
        phase_info = get_mapping_phase_info("mapping_load", 100)
        update_cache_with_phase_info("processing", "Mapping configuration loaded", 25, phase_info)
        
        # Phase 3: Prepare CSV data sources
        phase_info = get_mapping_phase_info("data_preparation", 25)
        update_cache_with_phase_info("processing", "Preparing CSV data sources...", 35, phase_info)
        
        if csv_sources is None:
            # Download and parse CSV from S3 using the same pattern as tests
            import csv
            import io
            
            bucket_service = BucketService()
            
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Loading CSV data from S3 object {s3_bucket_name}/{s3_object_key}")
            
            # Get file content directly using BucketService (same as tests)
            result = bucket_service.get_file_content(s3_bucket_name, s3_object_key)
            
            if isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
            else:
                raise Exception(f"Unexpected result format from get_file_content: {result}")
            
            # Parse CSV with semicolon delimiter (same as tests)
            csv_reader = csv.DictReader(io.StringIO(content), delimiter=';')
            rows = list(csv_reader)
            
            # Create csv_sources dict in the same format as test fixture
            csv_sources = {dataset_name: {
                'headers': csv_reader.fieldnames,
                'rows': rows,
                'row_count': len(rows)
            }}
            
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Loaded {len(rows)} rows from S3 CSV")
        
        logger.info(f"Task {actual_task_id or 'UnknownID'}: CSV sources prepared with {len(csv_sources)} datasets")
        
        phase_info = get_mapping_phase_info("data_preparation", 100)
        update_cache_with_phase_info("processing", "CSV data sources prepared", 45, phase_info)
        
        # Phase 4: Initialize MappingAwareProcessor and execute
        phase_info = get_mapping_phase_info("mapping_aware_processing", 10)
        update_cache_with_phase_info("processing", "Initializing MappingAwareProcessor...", 50, phase_info)
        
        # Initialize execution statistics
        execution_statistics = ExecutionStatistics()
        
        # Initialize processor
        processor = MappingAwareProcessor(
            institution=institution,
            base_uri=base_uri,
            statistics=execution_statistics
        )
        
        # Track processing time like in the test
        from datetime import datetime, timezone as dt_timezone
        start_time = datetime.now(dt_timezone.utc)
        
        phase_info = get_mapping_phase_info("mapping_aware_processing", 30)
        update_cache_with_phase_info("processing", "Executing mapping-aware processing...", 60, phase_info)
        
        # Execute the mapping-aware processing using STREAMING_ENTITY_CENTRIC strategy
        metrics = processor.process_with_execution_config(
            execution_config=execution_config,
            csv_sources=csv_sources,
            strategy=ProcessingStrategy.STREAMING_ENTITY_CENTRIC
        )
        
        end_time = datetime.now(dt_timezone.utc)
        processing_time = (end_time - start_time).total_seconds()
        
        phase_info = get_mapping_phase_info("mapping_aware_processing", 100)
        update_cache_with_phase_info("processing", "Mapping-aware processing completed", 80, phase_info)
        
        # Phase 5: Finalization
        phase_info = get_mapping_phase_info("finalization", 50)
        update_cache_with_phase_info("processing", "Finalizing mapping-aware import...", 85, phase_info)
        
        # Verify processing completed successfully
        if not isinstance(metrics, type(metrics)) or metrics.rows_processed <= 0:
            raise ValueError("No rows were processed by MappingAwareProcessor")
        
        final_metrics = {
            "rows_processed": metrics.rows_processed,
            "resources_created": metrics.resources_created,
            "triples_created": metrics.triples_created,
            "properties_created": metrics.properties_created,
            "processing_time_seconds": processing_time,
            "execution_strategy": "mapping_aware",
            "mapping_id": mapping_id,
            "mapping_name": mapping.name,
            "datasets_processed": len(csv_sources),
            "execution_config_datasets": len(execution_config.datasets),
            "execution_config_columns": sum(len(ds.columns) for ds in execution_config.datasets),
            "execution_config_relationships": len(execution_config.fk_relationships)
        }
        
        success_message = (
            f"Mapping-aware import for '{dataset_name}' completed successfully using mapping '{mapping.name}'. "
            f"Processed: {metrics.rows_processed} rows in {processing_time:.2f}s. "
            f"Created: {metrics.resources_created} resources, {metrics.triples_created} triples, {metrics.properties_created} properties."
        )
        
        logger.info("=== MAPPING-AWARE IMPORT RESULTS ===")
        logger.info(f"Task {actual_task_id or 'UnknownID'}: {success_message}")
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Execution config: {len(execution_config.datasets)} datasets, {sum(len(ds.columns) for ds in execution_config.datasets)} columns, {len(execution_config.fk_relationships)} FK relationships")
        logger.info("=== MAPPING-AWARE IMPORT COMPLETED ===")
        
        phase_info = get_mapping_phase_info("finalization", 100)
        update_cache_with_phase_info("completed", success_message, 100, phase_info, details=final_metrics)
        update_upload_session_status('completed', success_message, 1, 0)
        
        return {
            "status": "success",
            "dataset_name": dataset_name,
            "s3_object_key": s3_object_key,
            **final_metrics
        }
        
    except Exception as e:
        error_message = f"Error in mapping-aware import for dataset '{dataset_name}' from S3 object {s3_bucket_name}/{s3_object_key}: {str(e)}"
        logger.error(
            f"Task {actual_task_id or 'UnknownID'}: Mapping-aware import failed: {e}",
            exc_info=True
        )
        
        phase_info = get_mapping_phase_info("initialization", 0)
        update_cache_with_phase_info("failed", error_message, 0, phase_info, error_type=type(e).__name__)
        update_upload_session_status('failed', error_message)
        
        return {
            "status": "error",
            "dataset_name": dataset_name,
            "s3_object_key": s3_object_key,
            "error_message": str(e),
            "error_type": type(e).__name__
        }
    
    finally:
        # No cleanup needed - using in-memory processing like tests
        pass


@db_task(retries=1, retry_delay=60)
def run_csv_import_workflow_with_mapping(
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
    # Enhanced mapping parameters
    mapping_id: Optional[str] = None,
    execution_strategy: str = "auto",
    validation_mode: bool = True,
    file_dataset_mapping: Optional[Dict[str, str]] = None,
    use_mapping: bool = False,
    use_table_services: bool = False
) -> Dict[str, Any]:
    """
    Enhanced Huey task to import a CSV file with mapping integration support.
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
        mapping_id: Optional ID of the mapping configuration to use.
        execution_strategy: Strategy for execution ("auto", "entity_centric", "mapping_driven").
        validation_mode: Whether to validate files against mapping requirements.
        file_dataset_mapping: Optional manual mapping of files to datasets.
        use_mapping: Whether to use mapping-based processing.
        use_table_services: Whether to use table-based services.

    Returns:
        A dictionary containing the status of the import and key statistics.
    """
    actual_task_id = task_id_for_cache  # Prioritize the custom task ID for consistent polling
    
    # Only use Huey's task ID if no custom ID was provided
    if not actual_task_id and hasattr(run_csv_import_workflow_with_mapping, 'request') and run_csv_import_workflow_with_mapping.request.id:
        actual_task_id = run_csv_import_workflow_with_mapping.request.id
    
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
    
    def update_cache_with_phase_info(status: str, message: str, progress: int, 
                                   phase_info: Optional[Dict] = None, 
                                   details: Optional[Dict] = None, 
                                   error_type: Optional[str] = None):
        """
        Enhanced cache update function with phase information support.
        
        Args:
            status: Task status (pending, processing, completed, failed)
            message: Progress message
            progress: Overall progress percentage (0-100)
            phase_info: Dict containing phase information:
                - current_phase: Name of current phase
                - current_phase_index: Index of current phase (0-based)
                - total_phases: Total number of phases
                - phase_progress: Progress within current phase (0-100)
                - phase_description: Description of current phase
                - execution_strategy: Strategy being used (mapping_driven, entity_centric, etc.)
            details: Additional details about the task
            error_type: Error type if status is failed
        """
        if cache_key:
            payload = {
                "status": status,
                "message": message,
                "progress": progress,
                "timestamp": timezone.now().isoformat()
            }
            
            if phase_info:
                payload["phase_info"] = {
                    "current_phase": phase_info.get("current_phase", "unknown"),
                    "current_phase_index": phase_info.get("current_phase_index", 0),
                    "total_phases": phase_info.get("total_phases", 1),
                    "phase_progress": phase_info.get("phase_progress", 0),
                    "phase_description": phase_info.get("phase_description", ""),
                    "execution_strategy": phase_info.get("execution_strategy", "standard")
                }
            
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
                
            cache.set(cache_key, payload, timeout=3600)
            
            phase_msg = f" (Phase {phase_info.get('current_phase_index', 0) + 1}/{phase_info.get('total_phases', 1)}: {phase_info.get('current_phase', 'unknown')})" if phase_info else ""
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Cache updated - Key: {cache_key}, Status: {status}, Message: {message[:50]}...{phase_msg}")
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

    # Initialize phase tracking
    execution_phases = [
        "initialization",
        "file_download", 
        "mapping_validation",
        "file_validation",
        "strategy_selection",
        "data_import",
        "finalization"
    ]
    
    def get_phase_info(phase_name: str, phase_progress: int = 0) -> Dict:
        """Get phase information for progress tracking with complexity estimation."""
        try:
            phase_index = execution_phases.index(phase_name)
        except ValueError:
            phase_index = 0
        
        # Basic phase info
        phase_info = {
            "current_phase": phase_name,
            "current_phase_index": phase_index,
            "total_phases": len(execution_phases),
            "phase_progress": phase_progress,
            "phase_description": get_phase_description(phase_name),
            "execution_strategy": chosen_strategy if 'chosen_strategy' in locals() else "auto"
        }
        
        # Enhance with complexity-aware progress estimation if mapping is available
        if 'execution_config' in locals() and execution_config:
            try:
                strategy = ExecutionStrategy.MAPPING_DRIVEN if chosen_strategy == "mapping_driven" else ExecutionStrategy.ENTITY_CENTRIC
                enhanced_info = progress_estimator.get_enhanced_progress_info(
                    current_phase=phase_name,
                    phase_progress=phase_progress,
                    strategy=strategy,
                    mapping_config=execution_config.dict() if hasattr(execution_config, 'dict') else None
                )
                
                # Add enhanced information
                phase_info.update({
                    "enhanced_progress": enhanced_info["overall_progress"],
                    "complexity_score": enhanced_info["complexity_score"],
                    "estimated_duration": enhanced_info["current_phase_estimate"]["estimated_duration"] if enhanced_info["current_phase_estimate"] else None,
                    "complexity_factor": enhanced_info["current_phase_estimate"]["complexity_factor"] if enhanced_info["current_phase_estimate"] else None
                })
            except Exception as e:
                logger.warning(f"Failed to get enhanced progress info: {e}")
        
        return phase_info
    
    def get_phase_description(phase_name: str) -> str:
        """Get user-friendly description for each phase."""
        descriptions = {
            "initialization": "Preparing import task",
            "file_download": "Downloading file from S3",
            "mapping_validation": "Validating mapping configuration",
            "file_validation": "Validating file structure",
            "strategy_selection": "Selecting execution strategy",
            "data_import": "Importing data",
            "finalization": "Finalizing import"
        }
        return descriptions.get(phase_name, "Processing")
    
    # Phase 1: Initialization
    phase_info = get_phase_info("initialization", 50)
    update_cache_with_phase_info("processing", f"Starting import for {dataset_name} from S3: {s3_bucket_name}/{s3_object_key}...", 5, phase_info)

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
        
        # Phase 2: File Download
        phase_info = get_phase_info("file_download", 25)
        update_cache_with_phase_info("processing", f"Downloading file {os.path.basename(s3_object_key)}...", 10, phase_info)

        bucket_service.base_s3_service.s3_client.download_file(
            s3_bucket_name, 
            s3_object_key, 
            temp_local_path
        )
        logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully downloaded to {temp_local_path}")
        
        # Update file download phase completion
        phase_info = get_phase_info("file_download", 100)
        update_cache_with_phase_info("processing", f"File download completed", 15, phase_info)
        
        # Transition to next phase
        phase_info = get_phase_info("mapping_validation", 0)
        update_cache_with_phase_info("processing", f"Processing downloaded file {os.path.basename(temp_local_path)} for {dataset_name}...", 20, phase_info)
        
        # Enhanced mapping configuration handling
        mapping_config = None
        execution_config = None
        file_matcher = None
        
        # Phase 1: Load and validate mapping configuration
        if use_mapping and mapping_id:
            try:
                from arkumu.metadata.models import Mapping
                from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
                from arkumu.importer.services.file_matching.file_dataset_matcher import FileDatasetMatcher
                
                # Phase 3: Mapping Validation - Loading
                phase_info = get_phase_info("mapping_validation", 20)
                update_cache_with_phase_info("processing", f"Loading mapping configuration...", 25, phase_info)
                
                # Load the mapping
                mapping = Mapping.objects.get(id=mapping_id)
                adapter = MappingAdapter()
                
                # Validate mapping if validation mode is enabled
                if validation_mode:
                    # Phase 3: Mapping Validation - Validating
                    phase_info = get_phase_info("mapping_validation", 50)
                    update_cache_with_phase_info("processing", f"Validating mapping configuration...", 27, phase_info)
                    validation_result = adapter.validate_mapping(mapping_id)
                    
                    if not validation_result.is_valid:
                        error_msg = f"Mapping validation failed: {'; '.join(validation_result.errors)}"
                        logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}")
                        phase_info = get_phase_info("mapping_validation", 100)
                        update_cache_with_phase_info("failed", error_msg, 0, phase_info, error_type="MappingValidationError")
                        update_upload_session_status('failed', error_msg)
                        return {
                            "status": "error",
                            "dataset_name": dataset_name,
                            "s3_object_key": s3_object_key,
                            "error_message": error_msg,
                            "error_type": "MappingValidationError"
                        }
                
                # Translate mapping to execution config
                execution_config = adapter.translate_to_execution_config(mapping_id)
                
                # Initialize file matcher for dataset matching
                file_matcher = FileDatasetMatcher()
                
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Using mapping '{mapping.name}' (ID: {mapping_id})")
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Execution config loaded with {len(execution_config.datasets)} datasets")
                
            except Exception as e:
                error_msg = f"Failed to load mapping {mapping_id}: {str(e)}"
                logger.warning(f"Task {actual_task_id or 'UnknownID'}: {error_msg}")
                
                if validation_mode:
                    # In validation mode, mapping errors are fatal
                    phase_info = get_phase_info("mapping_validation", 100)
                    update_cache_with_phase_info("failed", error_msg, 0, phase_info, error_type="MappingLoadError")
                    update_upload_session_status('failed', error_msg)
                    return {
                        "status": "error",
                        "dataset_name": dataset_name,
                        "s3_object_key": s3_object_key,
                        "error_message": error_msg,
                        "error_type": "MappingLoadError"
                    }
                else:
                    # In non-validation mode, fall back to entity-based import
                    phase_info = get_phase_info("mapping_validation", 100)
                    update_cache_with_phase_info("processing", f"Warning: Failed to load mapping, using entity-based import", 30, phase_info)
        
        # Phase 4: File validation and dataset matching
        if execution_config and file_matcher:
            try:
                # Phase 4: File Validation
                phase_info = get_phase_info("file_validation", 30)
                update_cache_with_phase_info("processing", f"Validating file structure against mapping...", 35, phase_info)
                
                # Validate file against mapping requirements
                selected_files = [temp_local_path]
                match_result = file_matcher.match_files_to_datasets(
                    selected_files=selected_files,
                    execution_config=execution_config,
                    base_directory=None
                )
                
                if not match_result.successful_matches:
                    if validation_mode:
                        error_msg = f"File {os.path.basename(temp_local_path)} does not match any dataset in mapping"
                        logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}")
                        phase_info = get_phase_info("file_validation", 100)
                        update_cache_with_phase_info("failed", error_msg, 0, phase_info, error_type="FileValidationError")
                        update_upload_session_status('failed', error_msg)
                        return {
                            "status": "error",
                            "dataset_name": dataset_name,
                            "s3_object_key": s3_object_key,
                            "error_message": error_msg,
                            "error_type": "FileValidationError"
                        }
                    else:
                        logger.warning(f"Task {actual_task_id or 'UnknownID'}: File validation failed, proceeding with entity-based import")
                else:
                    # Log successful matches
                    for match in match_result.successful_matches:
                        logger.info(f"Task {actual_task_id or 'UnknownID'}: File matched to dataset '{match.dataset_name}' with confidence {match.confidence:.2f}")
                        
                        # Update file_dataset_mapping if not provided
                        if not file_dataset_mapping:
                            file_dataset_mapping = {temp_local_path: match.dataset_name}
                
            except Exception as e:
                error_msg = f"File validation failed: {str(e)}"
                logger.error(f"Task {actual_task_id or 'UnknownID'}: {error_msg}")
                
                if validation_mode:
                    phase_info = get_phase_info("file_validation", 100)
                    update_cache_with_phase_info("failed", error_msg, 0, phase_info, error_type="FileValidationError")
                    update_upload_session_status('failed', error_msg)
                    return {
                        "status": "error",
                        "dataset_name": dataset_name,
                        "s3_object_key": s3_object_key,
                        "error_message": error_msg,
                        "error_type": "FileValidationError"
                    }
                else:
                    logger.warning(f"Task {actual_task_id or 'UnknownID'}: File validation failed, proceeding with entity-based import")
        
        # Phase 5: Determine execution strategy
        chosen_strategy = execution_strategy
        
        # Phase 5: Strategy Selection
        phase_info = get_phase_info("strategy_selection", 50)
        update_cache_with_phase_info("processing", f"Determining execution strategy...", 38, phase_info)
        
        if execution_strategy == "auto":
            if execution_config and file_matcher:
                # Use mapping-driven strategy if mapping is available and valid
                chosen_strategy = "mapping_driven"
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Auto-selected mapping_driven strategy")
            else:
                # Fall back to entity-centric strategy
                chosen_strategy = "entity_centric"
                logger.info(f"Task {actual_task_id or 'UnknownID'}: Auto-selected entity_centric strategy")
        
        # Update strategy selection completion
        phase_info = get_phase_info("strategy_selection", 100)
        phase_info["execution_strategy"] = chosen_strategy
        update_cache_with_phase_info("processing", f"Using {chosen_strategy} execution strategy...", 40, phase_info)
        
        # Phase 6: Execute import based on chosen strategy
        # Get organization (this is a simplified version - in production you'd get it from the session)
        from arkumu.metadata.models import Organization
        organization = Organization.objects.get(code=institution)
        
        # Prepare session dictionary for advanced features
        session_dict = {}
        if execution_config:
            session_dict['execution_config'] = execution_config
        if file_dataset_mapping:
            session_dict['file_dataset_mapping'] = file_dataset_mapping
        
        # Execute import based on strategy
        if chosen_strategy == "mapping_driven" and execution_config:
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Executing mapping-driven import with enhanced configuration")
            
            # Phase 6: Data Import - Mapping-driven
            phase_info = get_phase_info("data_import", 10)
            phase_info["execution_strategy"] = chosen_strategy
            update_cache_with_phase_info("processing", f"Executing mapping-driven import...", 45, phase_info)
            
            # Use table services with mapping configuration
            stats: BulkUpdateStats = bridge_service.import_csv_with_table_services(
                file_path=temp_local_path,
                organization=organization,
                user=None,  # TODO: Get user from session
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                auto_mapping=True,
                session_dict=session_dict
            )
            
        elif chosen_strategy == "entity_centric" or (use_table_services and not execution_config):
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Executing entity-centric import with table services")
            
            # Phase 6: Data Import - Entity-centric
            phase_info = get_phase_info("data_import", 10)
            phase_info["execution_strategy"] = chosen_strategy
            update_cache_with_phase_info("processing", f"Executing entity-centric import...", 45, phase_info)
            
            # Use table services without mapping configuration
            stats: BulkUpdateStats = bridge_service.import_csv_with_table_services(
                file_path=temp_local_path,
                organization=organization,
                user=None,  # TODO: Get user from session
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                auto_mapping=False,
                session_dict=session_dict if session_dict else None
            )
            
        else:
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Using standard import workflow")
            
            # Phase 6: Data Import - Standard
            phase_info = get_phase_info("data_import", 10)
            phase_info["execution_strategy"] = "standard"
            update_cache_with_phase_info("processing", f"Executing standard import...", 45, phase_info)
            
            # Use standard import workflow
            stats: BulkUpdateStats = bridge_service.import_csv(
                file_path=temp_local_path,
                organization=organization,
                user=None,  # TODO: Get user from session
                update_strategy=update_strategy.value,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                link_row_cells=link_row_cells,
                link_to_first_column=link_to_first_column,
                use_smart_updater=True,
                use_polars=True,
                use_table_services=use_table_services
            )
        
        # Phase 6: Data Import - Completion
        phase_info = get_phase_info("data_import", 100)
        phase_info["execution_strategy"] = chosen_strategy
        update_cache_with_phase_info("processing", f"Data import completed, processing results...", 70, phase_info)
        
        # Phase 7: Finalization
        phase_info = get_phase_info("finalization", 30)
        phase_info["execution_strategy"] = chosen_strategy
        update_cache_with_phase_info("processing", f"Finalizing import for {dataset_name}...", 80, phase_info)

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
            # Enhanced mapping-aware statistics
            "execution_strategy": chosen_strategy,
            "mapping_used": mapping_id is not None,
            "mapping_id": mapping_id,
            "file_dataset_mapping": file_dataset_mapping,
            "validation_mode": validation_mode
        }
        
        # Enhanced success message with mapping information
        success_message = (
            f"Dataset '{dataset_name}' (from S3 object {s3_object_key}) imported successfully using {chosen_strategy} strategy. "
            f"Processed: {actual_stats_data.get('rows_processed', 0)} rows. "
            f"Created: {actual_stats_data.get('resources_created', 0)} resources, {actual_stats_data.get('triples_created', 0)} triples. "
            f"Errors: {actual_stats_data.get('errors', 0)}."
        )
        
        if mapping_id:
            success_message += f" Mapping ID: {mapping_id}."
        
        if file_dataset_mapping:
            matched_dataset = file_dataset_mapping.get(temp_local_path, "unknown")
            success_message += f" Matched to dataset: {matched_dataset}."
        # Phase 7: Finalization - Complete
        phase_info = get_phase_info("finalization", 100)
        phase_info["execution_strategy"] = chosen_strategy
        update_cache_with_phase_info("completed", success_message, 100, phase_info, details=final_stats_dict)
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
        # Use generic error phase info if no specific phase is available
        phase_info = get_phase_info("initialization", 0)
        update_cache_with_phase_info("failed", error_message, 0, phase_info, error_type=type(e).__name__)
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
def run_csv_import_workflow(
    s3_bucket_name: str,
    s3_object_key: str,
    dataset_name: str,
    institution: str,
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = True,
    link_row_cells: bool = True,
    link_to_first_column: bool = False,
    update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
    task_id_for_cache: Optional[str] = None,
    upload_session_id: Optional[UUID] = None,
    # Legacy mapping parameters for backward compatibility
    mapping_id: Optional[str] = None,
    use_mapping: bool = False,
    use_table_services: bool = False
) -> Dict[str, Any]:
    """
    Legacy wrapper function for backward compatibility.
    
    This function maintains the existing API while delegating to the enhanced
    run_csv_import_workflow_with_mapping function with default parameters.
    """
    logger.info(f"Legacy function called, delegating to enhanced function with default parameters")
    
    return run_csv_import_workflow_with_mapping(
        s3_bucket_name=s3_bucket_name,
        s3_object_key=s3_object_key,
        dataset_name=dataset_name,
        institution=institution,
        base_uri=base_uri,
        delimiter=delimiter,
        has_quoted_fields=has_quoted_fields,
        link_row_cells=link_row_cells,
        link_to_first_column=link_to_first_column,
        update_strategy=update_strategy,
        task_id_for_cache=task_id_for_cache,
        upload_session_id=upload_session_id,
        mapping_id=mapping_id,
        execution_strategy="auto",
        validation_mode=False,
        file_dataset_mapping=None,
        use_mapping=use_mapping,
        use_table_services=use_table_services
    )


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
    
    def update_cache_with_phase_info(status: str, message: str, progress: int, 
                                   phase_info: Optional[Dict] = None, 
                                   details: Optional[Dict] = None, 
                                   error_type: Optional[str] = None):
        """Enhanced cache update function with phase information support for directory imports."""
        if cache_key:
            payload = {
                "status": status,
                "message": message,
                "progress": progress,
                "timestamp": timezone.now().isoformat()
            }
            
            if phase_info:
                payload["phase_info"] = {
                    "current_phase": phase_info.get("current_phase", "unknown"),
                    "current_phase_index": phase_info.get("current_phase_index", 0),
                    "total_phases": phase_info.get("total_phases", 1),
                    "phase_progress": phase_info.get("phase_progress", 0),
                    "phase_description": phase_info.get("phase_description", ""),
                    "execution_strategy": phase_info.get("execution_strategy", "directory")
                }
            
            if details:
                payload["details"] = details
            if error_type:
                payload["error_type"] = error_type
                
            cache.set(cache_key, payload, timeout=3600)
            
            phase_msg = f" (Phase {phase_info.get('current_phase_index', 0) + 1}/{phase_info.get('total_phases', 1)}: {phase_info.get('current_phase', 'unknown')})" if phase_info else ""
            logger.info(f"Task {actual_task_id or 'UnknownID'}: Cache updated - Key: {cache_key}, Status: {status}, Message: {message[:50]}...{phase_msg}")
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

    # Initialize phase tracking for directory import
    directory_phases = [
        "initialization",
        "discovery",
        "download",
        "processing",
        "finalization"
    ]
    
    def get_directory_phase_info(phase_name: str, phase_progress: int = 0) -> Dict:
        """Get phase information for directory import progress tracking."""
        try:
            phase_index = directory_phases.index(phase_name)
        except ValueError:
            phase_index = 0
        
        return {
            "current_phase": phase_name,
            "current_phase_index": phase_index,
            "total_phases": len(directory_phases),
            "phase_progress": phase_progress,
            "phase_description": get_directory_phase_description(phase_name),
            "execution_strategy": "directory"
        }
    
    def get_directory_phase_description(phase_name: str) -> str:
        """Get user-friendly description for each directory import phase."""
        descriptions = {
            "initialization": "Initializing directory import",
            "discovery": "Discovering CSV files",
            "download": "Downloading files",
            "processing": "Processing CSV files",
            "finalization": "Finalizing directory import"
        }
        return descriptions.get(phase_name, "Processing")
    
    # Phase 1: Initialization
    phase_info = get_directory_phase_info("initialization", 100)
    update_cache_with_phase_info("processing", f"Starting directory import for {dataset_name} from S3 folder: {s3_bucket_name}/{s3_folder_prefix}...", 5, phase_info)

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

        # Phase 2: Discovery
        phase_info = get_directory_phase_info("discovery", 25)
        update_cache_with_phase_info("processing", "Discovering CSV files in S3 folder...", 10, phase_info)

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

        # Phase 2: Discovery - Complete
        phase_info = get_directory_phase_info("discovery", 100)
        update_cache_with_phase_info("processing", f"Found {len(csv_objects)} CSV files", 15, phase_info)

        # Phase 3: Download
        phase_info = get_directory_phase_info("download", 0)
        update_cache_with_phase_info("processing", f"Downloading {len(csv_objects)} CSV files from S3...", 20, phase_info)

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
            file_progress = int(100 * (i + 1) / len(csv_objects))
            overall_progress = 20 + (30 * (i + 1) / len(csv_objects))
            phase_info = get_directory_phase_info("download", file_progress)
            update_cache_with_phase_info("processing", f"Downloaded {i+1}/{len(csv_objects)} files...", int(overall_progress), phase_info)

        logger.info(f"Task {actual_task_id or 'UnknownID'}: Successfully downloaded all {len(downloaded_files)} CSV files to {temp_directory_path}")

        # Phase 3: Download - Complete
        phase_info = get_directory_phase_info("download", 100)
        update_cache_with_phase_info("processing", f"Download completed", 45, phase_info)

        # Phase 4: Processing
        phase_info = get_directory_phase_info("processing", 0)
        update_cache_with_phase_info("processing", f"Processing {len(downloaded_files)} CSV files...", 50, phase_info)

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
                    
                    # Update with phase information
                    phase_info = get_directory_phase_info("processing", int(time_progress * 100))
                    update_cache_with_phase_info(
                        "processing", 
                        f"Processing {len(downloaded_files)} CSV files... ({elapsed_time//60}m {elapsed_time%60}s elapsed)",
                        current_progress,
                        phase_info,
                        details={"csv_files_found": len(csv_objects), "csv_files_downloaded": len(downloaded_files)}
                    )
        
        # Start progress thread
        progress_thread = threading.Thread(target=update_processing_progress, daemon=True)
        progress_thread.start()
        
        try:
            # Get organization (this is a simplified version - in production you'd get it from the session)
            from arkumu.metadata.models import Organization
            organization = Organization.objects.get(code=institution)
            
            aggregate_stats = bridge_service.import_csv_directory(
                directory_path=temp_directory_path,
                organization=organization,
                user=None,  # TODO: Get user from session
                update_strategy=update_strategy.value,
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
                timestamp_column=timestamp_column
            )
        finally:
            # Stop the progress thread
            processing_complete = True
        
        # Phase 4: Processing - Complete
        phase_info = get_directory_phase_info("processing", 100)
        update_cache_with_phase_info("processing", f"Processing completed", 85, phase_info)

        # Phase 5: Finalization
        phase_info = get_directory_phase_info("finalization", 50)
        update_cache_with_phase_info("processing", f"Finalizing directory import for {dataset_name}...", 90, phase_info)

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
        
        # Phase 5: Finalization - Complete
        phase_info = get_directory_phase_info("finalization", 100)
        update_cache_with_phase_info("completed", success_message, 100, phase_info, details=final_aggregate_stats)
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
        # Use generic error phase info if no specific phase is available
        phase_info = get_directory_phase_info("initialization", 0)
        update_cache_with_phase_info("failed", error_message, 0, phase_info, error_type=type(e).__name__)
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



