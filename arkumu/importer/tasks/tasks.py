"""
Huey Task for Import Processing with SSE Progress Updates

This module contains the Huey task for running import jobs asynchronously
with real-time progress updates via Server-Sent Events (SSE).
"""

import logging
from huey.contrib.djhuey import task
from arkumu.importer.utils.progress import publish_progress, create_channel_id
from arkumu.importer.models import IngestSession

logger = logging.getLogger(__name__)


@task()
def run_import(session_pk: int):
    """
    Run import job asynchronously with progress updates.
    
    Args:
        session_pk: Primary key of the IngestSession to process
        
    Raises:
        Exception: Re-raises any exceptions for Huey retry mechanism
    """
    try:
        session = IngestSession.objects.get(pk=session_pk)
        channel = create_channel_id(session_pk)
        
        logger.info(f"Starting import for session {session_pk}")
        
        # Update status
        session.mark_started()
        
        # Initial notification
        publish_progress(channel, {
            'status': 'started',
            'message': 'Import job started',
            'percentage': 0
        })
        
        # Import the processor here to avoid circular imports
        from arkumu.importer.services.execution.mapping_aware_processor import MappingAwareProcessor
        from arkumu.importer.services.execution.statistics import ExecutionStatistics
        from arkumu.importer.services.mapping_consumer import ExecutionConfig
        from arkumu.importer.services.mapping_consumer.config_translator import ConfigTranslator
        
        # Create statistics tracker
        statistics = ExecutionStatistics()
        
        # Initialize processor
        processor = MappingAwareProcessor(
            institution=session.organization.code,
            base_uri=session.base_uri,
            statistics=statistics
        )
        
        # Translate mapping configuration
        if session.mapping:
            config_translator = ConfigTranslator()
            execution_config = config_translator.translate_mapping_config(
                session.mapping.mapping_config
            )
            
            # If no valid execution config, skip processing
            if not execution_config or not execution_config.datasets:
                logger.warning(f"No valid execution config for session {session_pk}")
                session.mark_completed({'message': 'No valid configuration'})
                return
            
            # Create mock CSV sources for testing
            # In production, this would load actual CSV data
            csv_sources = {}
            for dataset in execution_config.datasets:
                csv_sources[dataset.dataset_name] = {
                    'headers': ['id', 'name', 'value'],
                    'rows': [
                        {'id': '1', 'name': 'Test 1', 'value': 'Value 1'},
                        {'id': '2', 'name': 'Test 2', 'value': 'Value 2'},
                    ]
                }
            
            # Run processor with entity-centric strategy
            from arkumu.importer.services.mapping_consumer import ProcessingStrategy
            metrics = processor.process_with_execution_config(
                execution_config, 
                csv_sources, 
                ProcessingStrategy.ENTITY_CENTRIC
            )
            
            # Update session with results
            session.ingestion_stats = {
                'rows_processed': metrics.rows_processed,
                'resources_created': metrics.resources_created,
                'triples_created': metrics.triples_created,
                'errors': metrics.errors
            }
        
        # Success notification
        session.mark_completed(session.ingestion_stats)
        
        publish_progress(channel, {
            'status': 'complete',
            'message': 'Import completed successfully',
            'percentage': 100
        }, event='complete')
        
        logger.info(f"Import completed successfully for session {session_pk}")
        
    except Exception as exc:
        logger.error(f"Import failed for session {session_pk}: {exc}")
        
        # Error handling
        session.mark_failed(str(exc))
        
        publish_progress(channel, {
            'status': 'error',
            'message': f'Import failed: {str(exc)}',
            'percentage': session.get_progress_percentage()
        }, event='error')
        
        raise  # Re-raise for Huey retry mechanism