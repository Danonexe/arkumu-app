"""
CSV Mapping Execution Utilities

This module contains utility functions and helpers for CSV mapping execution:
- Strategy conversion utilities
- Report data preparation
- Dataset source preparation
- Validation helpers

Extracted from execution_views.py to improve maintainability.
"""

import logging
from typing import Dict, List, Any, Optional
from django.utils import timezone

from arkumu.importer.services.importer.smart_bulk_updater_polars import UpdateStrategy
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


class ExecutionUtils:
    """Utility functions for execution orchestration."""
    
    @staticmethod
    def convert_strategy_string(strategy_str: str) -> UpdateStrategy:
        """Convert string strategy to UpdateStrategy enum."""
        strategy_map = {
            'SKIP_EXISTING': UpdateStrategy.SKIP_EXISTING,
            'UPDATE_VALUES': UpdateStrategy.UPDATE_VALUES,
            'REPLACE_ALL': UpdateStrategy.UPDATE_VALUES,  # Map to UPDATE_VALUES
            'TIMESTAMP_BASED': UpdateStrategy.TIMESTAMP_BASED
        }
        return strategy_map.get(strategy_str, UpdateStrategy.SKIP_EXISTING)
    
    @staticmethod
    def prepare_dataset_sources(organization_id: str, 
                               mapping_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepare dataset source information without loading full data."""
        selected_datasets = mapping_config.get('selected_datasets', [])
        
        analyzer = S3DirectDataAnalyzer()
        dataset_sources = []
        
        try:
            available_sources = analyzer.discover_s3_data_sources(organization_id)
            
            for dataset_name in selected_datasets:
                # Find source for this dataset
                source_info = None
                for source in available_sources:
                    datasets = analyzer.get_dataset_names_from_s3_source(source)
                    if dataset_name in datasets:
                        source_info = source
                        break
                
                if source_info:
                    dataset_sources.append({
                        'dataset_name': dataset_name,
                        'source_info': source_info,
                        'organization_id': organization_id
                    })
                    logger.info(f"Prepared source for dataset: {dataset_name}")
                else:
                    logger.warning(f"Source not found for dataset: {dataset_name}")
            
            logger.info(f"Prepared {len(dataset_sources)} dataset sources")
            return dataset_sources
            
        except Exception as e:
            logger.error(f"Error preparing dataset sources: {e}", exc_info=True)
            return []
    
    @staticmethod
    def prepare_report_data(execution_results: Dict[str, Any], 
                           execution_name: str, mapping_config: Dict[str, Any],
                           mapping_id: str = None, dataset_name: str = None,
                           strategy: str = 'SKIP_EXISTING') -> Dict[str, Any]:
        """Prepare data for the service_execution_results.html template."""
        
        # Extract statistics from execution results
        stats = execution_results.get('statistics', {})
        phase_results = execution_results.get('phase_results', [])
        
        # Calculate totals across all phases
        total_entities_processed = sum(phase.get('entities_processed', 0) for phase in phase_results)
        total_triples_created = sum(phase.get('triples_created', 0) for phase in phase_results)
        
        # Format execution time
        execution_time_seconds = execution_results.get('total_execution_time', 0)
        if execution_time_seconds < 60:
            formatted_time = f"{execution_time_seconds:.1f}s"
        elif execution_time_seconds < 3600:
            formatted_time = f"{execution_time_seconds/60:.1f}m"
        else:
            formatted_time = f"{execution_time_seconds/3600:.1f}h"
        
        # Prepare phase timing metrics
        phase_timings = {}
        for phase in phase_results:
            phase_name = phase.get('phase', 'Unknown')
            phase_time = phase.get('execution_time', 0)
            if phase_time < 60:
                phase_timings[phase_name] = f"{phase_time:.1f}s"
            else:
                phase_timings[phase_name] = f"{phase_time/60:.1f}m"
        
        # Create pipeline result data
        pipeline_result = {
            'entities_processed': total_entities_processed,
            'triples_created': total_triples_created,
            'execution_time': formatted_time,
            'service_metrics': phase_timings,
        }
        
        # Extract mapping rules for display
        workspace_columns = mapping_config.get('workspace_columns', {})
        mapping_rules = []
        
        for column_name, column_config in workspace_columns.items():
            arkumu_type = column_config.get('arkumu_type', 'Unknown')
            confidence = column_config.get('confidence')
            
            mapping_rules.append({
                'pattern_value': column_name,
                'arkumu_type': arkumu_type,
                'confidence': confidence
            })
        
        # Extract services used
        services_used = ['GUIMappingProcessor', 'SmartBulkUpdaterPolars', 'S3DirectDataAnalyzer']
        
        # Prepare warnings from execution
        warnings = execution_results.get('warnings', [])
        for phase in phase_results:
            warnings.extend(phase.get('warnings', []))
        
        return {
            'dry_run': False,  # CSV mapping execution is always real
            'service_powered': True,
            'pipeline_result': pipeline_result,
            'mapping_rules': mapping_rules,
            'services_used': services_used,
            'dataset_name': dataset_name or 'Unknown',
            'organization': mapping_config.get('organization', 'Unknown'),
            'success': execution_results.get('success', True),
            'phase_results': phase_results,
            'warnings': warnings,
            'execution_name': execution_name,
            'strategy_used': strategy,
            'mapping_id': mapping_id,
        }
    
    @staticmethod
    def execute_with_batch_processing(processor, mapping_config, dataset_sources, 
                                     organization_id, dataset_name):
        """Fallback batch processing for non-Polars execution."""
        # For the original processor, we need some data
        # But we can still load in reasonable chunks
        analyzer = S3DirectDataAnalyzer()
        sample_data = []
        
        for source_data in dataset_sources:
            source_info = source_data['source_info']
            ds_name = source_data['dataset_name']
            
            # Load a reasonable sample (not full dataset)
            preview = analyzer.get_s3_table_preview(source_info, ds_name, limit=1000)
            for row in preview.data_rows:
                row_dict = {col: val for col, val in zip(preview.column_headers, row)}
                row_dict['__dataset_name__'] = ds_name
                sample_data.append(row_dict)
        
        return processor.process_gui_mapping(
            mapping_config=mapping_config,
            csv_data=sample_data,  # Use sample instead of full data
            organization_id=organization_id,
            dataset_name=dataset_name
        ) 