#!/usr/bin/env python
"""
Test script for executing a saved mapping with real CSV data.

Usage:
    python manage.py shell < test_mapping_execution.py
"""

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.mapping_executor import MappingExecutor
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.metadata.services.mapping import MappingCoordinator
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_mapping_execution(mapping_id, organization_id):
    """
    Test execution of a saved mapping.
    
    Args:
        mapping_id: ID of the mapping to execute
        organization_id: Organization ID
    """
    try:
        # 1. Load the mapping
        logger.info(f"Loading mapping {mapping_id}...")
        mapping = Mapping.objects.get(id=mapping_id, organization_id=organization_id)
        logger.info(f"Found mapping: {mapping.name}")
        logger.info(f"Source datasets: {mapping.source_datasets}")
        logger.info(f"Workspace columns: {len(mapping.mapping_config.get('workspace_columns', {}))}")
        
        # 2. Initialize services
        logger.info("Initializing services...")
        
        # Option A: Use MappingExecutor for entity-based mapping (traditional approach)
        if mapping.mapping_config.get('subject_column'):
            logger.info("Using MappingExecutor for entity-based mapping...")
            executor = MappingExecutor(base_uri="http://arkumu.org/data")
            
            # Load CSV data from S3
            analyzer = S3DirectDataAnalyzer()
            csv_data = []
            
            for dataset_name in mapping.source_datasets:
                logger.info(f"Loading data for dataset: {dataset_name}")
                # This is a simplified example - you'd need to adapt based on your S3 setup
                # dataset_data = analyzer.get_dataset_sample(organization_id, dataset_name, limit=None)
                # csv_data.extend(dataset_data)
            
            # Execute mapping
            stats = executor.execute_mapping(mapping, csv_data)
            
            logger.info(f"Execution complete!")
            logger.info(f"Entities created: {stats.entities_created}")
            logger.info(f"Entities updated: {stats.entities_updated}")
            logger.info(f"Triples created: {stats.triples_created}")
            logger.info(f"Rows processed: {stats.rows_processed}")
            
        # Option B: Use SmartBulkUpdaterPolars for cell-based mapping (GUI approach)
        else:
            logger.info("Using SmartBulkUpdaterPolars for cell-based mapping...")
            
            # Initialize coordinator for sophisticated mapping analysis
            coordinator = MappingCoordinator(
                organization_id=organization_id,
                base_uri="http://arkumu.org/data"
            )
            
            # Build processing plan
            workspace_columns = mapping.mapping_config.get('workspace_columns', {})
            selected_datasets = mapping.mapping_config.get('selected_datasets', [])
            
            processing_plan = coordinator.build_processing_plan(
                workspace_columns=workspace_columns,
                selected_datasets=selected_datasets
            )
            
            # Validate plan
            validation = coordinator.validate_processing_plan(processing_plan, selected_datasets)
            if not validation.is_valid:
                logger.error(f"Invalid mapping: {validation.errors}")
                return
            
            # Initialize updater
            updater = SmartBulkUpdaterPolars(
                default_strategy=UpdateStrategy.SKIP_EXISTING,
                institution=organization_id,
                base_uri="http://arkumu.org/data",
                link_row_cells=True,
                link_topology="first_column"
            )
            
            # Process each dataset
            analyzer = S3DirectDataAnalyzer()
            
            for dataset_name in selected_datasets:
                logger.info(f"Processing dataset: {dataset_name}")
                
                # Get CSV data from S3
                csv_path = f"s3://your-bucket/{organization_id}/{dataset_name}.csv"
                
                # Import with column mapping configuration
                stats = updater.import_csv_with_column_configs(
                    csv_file=csv_path,
                    dataset_name=dataset_name,
                    column_configs=workspace_columns,
                    fk_relationships=mapping.mapping_config.get('fk_relationships', {}),
                    create_dataset_class=True
                )
                
                logger.info(f"Dataset {dataset_name} processed:")
                logger.info(f"  Resources created: {stats.resources_created}")
                logger.info(f"  Triples created: {stats.triples_created}")
                logger.info(f"  Relationships created: {stats.relationships_created}")
        
        # 3. Update mapping execution stats
        mapping.last_executed = timezone.now()
        mapping.execution_stats = {
            'resources_created': stats.resources_created if hasattr(stats, 'resources_created') else 0,
            'triples_created': stats.triples_created if hasattr(stats, 'triples_created') else 0,
            'rows_processed': stats.rows_processed if hasattr(stats, 'rows_processed') else 0,
            'executed_at': timezone.now().isoformat()
        }
        mapping.save()
        
        logger.info("Mapping execution completed successfully!")
        
    except Mapping.DoesNotExist:
        logger.error(f"Mapping {mapping_id} not found for organization {organization_id}")
    except Exception as e:
        logger.error(f"Error executing mapping: {e}", exc_info=True)


# Example usage
if __name__ == "__main__":
    # Replace with your actual mapping ID and organization
    MAPPING_ID = "your-mapping-id-here"
    ORGANIZATION_ID = "your-org-id"
    
    test_mapping_execution(MAPPING_ID, ORGANIZATION_ID)