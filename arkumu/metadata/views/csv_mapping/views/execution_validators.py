"""
CSV Mapping Execution Validators

This module contains validation logic for CSV mapping execution:
- Pre-execution validation
- Configuration validation
- Dataset availability validation  
- Comprehensive mapping validation

Extracted from execution_views.py to improve maintainability.
"""

import logging
from typing import Dict, List, Any, Optional

from arkumu.importer.services.importer.mapping_processor import GUIMappingProcessor
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


class ExecutionValidator:
    """Handles validation of mapping configurations for execution."""
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def validate_mapping_for_execution(self, mapping_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate mapping configuration for execution readiness."""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Check workspace columns exist
            workspace_columns = mapping_config.get('workspace_columns', {})
            if not workspace_columns:
                validation_result['errors'].append("No workspace columns configured")
                validation_result['is_valid'] = False
            
            # Check selected datasets exist
            selected_datasets = mapping_config.get('selected_datasets', [])
            if not selected_datasets:
                validation_result['errors'].append("No datasets selected")
                validation_result['is_valid'] = False
            
            # Validate datasets are still available
            analyzer = S3DirectDataAnalyzer()
            available_sources = analyzer.discover_s3_data_sources(self.organization_id)
            available_dataset_names = set()
            
            for source in available_sources:
                datasets = analyzer.get_dataset_names_from_s3_source(source)
                available_dataset_names.update(datasets)
            
            missing_datasets = []
            for dataset_name in selected_datasets:
                if dataset_name not in available_dataset_names:
                    missing_datasets.append(dataset_name)
            
            if missing_datasets:
                validation_result['errors'].extend([
                    f"Dataset '{name}' is no longer available" for name in missing_datasets
                ])
                validation_result['is_valid'] = False
            
            # Check for at least one anchor column
            has_anchor = any(
                col.get('is_anchor', False) 
                for col in workspace_columns.values()
            )
            
            if not has_anchor:
                validation_result['warnings'].append(
                    "No anchor columns defined - entities will be created with auto-generated IDs"
                )
            
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            validation_result['is_valid'] = False
        
        return validation_result
    
    def comprehensive_mapping_validation(self, mapping_config: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive mapping validation."""
        result = {
            'is_valid': True,
            'is_executable': True,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        try:
            # 1. Structure validation
            required_keys = ['workspace_columns', 'metadata']
            for key in required_keys:
                if key not in mapping_config:
                    result['errors'].append(f"Missing required key: {key}")
                    result['is_valid'] = False
            
            # Check that at least one datasets key exists (backward compatibility)
            if 'selected_datasets' not in mapping_config and 'workspace_datasets' not in mapping_config:
                result['errors'].append("Missing datasets configuration: need either 'selected_datasets' or 'workspace_datasets'")
                result['is_valid'] = False
            
            # 2. Dataset availability validation (support both old and new format)
            selected_datasets = mapping_config.get('workspace_datasets', mapping_config.get('selected_datasets', []))
            if not selected_datasets:
                result['errors'].append("No datasets selected")
                result['is_executable'] = False
            
            # 3. Column validation
            workspace_columns = mapping_config.get('workspace_columns', {})
            if not workspace_columns:
                result['errors'].append("No workspace columns configured")
                result['is_executable'] = False
            
            # 4. Dependency validation (using mapping processor)
            processor = GUIMappingProcessor()
            try:
                execution_plan = processor.analyze_gui_mapping_config(mapping_config)
                result['details']['execution_plan'] = {
                    'phase_1_entities': len(execution_plan.phase_1_columns),
                    'phase_2_literals': len(execution_plan.phase_2_columns),
                    'phase_3_relationships': len(execution_plan.phase_3_columns),
                    'phase_4_contexts': len(execution_plan.phase_4_columns),
                    'external_ontology': len(execution_plan.external_ontology_columns)
                }
            except Exception as e:
                result['errors'].append(f"Execution plan creation failed: {str(e)}")
                result['is_executable'] = False
            
            # 5. Data availability check
            try:
                analyzer = S3DirectDataAnalyzer()
                available_sources = analyzer.discover_s3_data_sources(self.organization_id)
                available_datasets = set()
                
                for source in available_sources:
                    datasets = analyzer.get_dataset_names_from_s3_source(source)
                    available_datasets.update(datasets)
                
                missing_datasets = [
                    ds for ds in selected_datasets if ds not in available_datasets
                ]
                
                if missing_datasets:
                    result['errors'].extend([
                        f"Dataset '{ds}' is not available" for ds in missing_datasets
                    ])
                    result['is_executable'] = False
                
                result['details']['dataset_availability'] = {
                    'total_selected': len(selected_datasets),
                    'available': len(selected_datasets) - len(missing_datasets),
                    'missing': missing_datasets
                }
                
            except Exception as e:
                result['warnings'].append(f"Could not verify dataset availability: {str(e)}")
            
            # Update overall validity
            if result['errors']:
                result['is_valid'] = False
            
        except Exception as e:
            result['errors'].append(f"Validation process error: {str(e)}")
            result['is_valid'] = False
            result['is_executable'] = False
        
        return result


class ExecutionAnalyzer:
    """Analyzes mapping configurations for execution planning."""
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def analyze_execution_plan(self, mapping_config: Dict[str, Any], analysis_name: str) -> Dict[str, Any]:
        """Analyze mapping for execution readiness and create execution plan."""
        
        # Analyze mapping for execution readiness
        processor = GUIMappingProcessor()
        execution_plan = processor.analyze_gui_mapping_config(mapping_config)
        
        # Check data availability (support both old and new format)
        selected_datasets = mapping_config.get('workspace_datasets', mapping_config.get('selected_datasets', []))
        analyzer = S3DirectDataAnalyzer()
        
        dataset_analysis = {}
        total_estimated_rows = 0
        
        for dataset in selected_datasets:
            try:
                available_sources = analyzer.discover_s3_data_sources(self.organization_id)
                source_info = None
                
                for source in available_sources:
                    datasets = analyzer.get_dataset_names_from_s3_source(source)
                    if dataset in datasets:
                        source_info = source
                        break
                
                if source_info:
                    row_count = analyzer._get_total_row_count_safe(source_info, dataset)
                    dataset_analysis[dataset] = {
                        'available': True,
                        'estimated_rows': row_count,
                        'source': source_info.name
                    }
                    total_estimated_rows += row_count
                else:
                    dataset_analysis[dataset] = {
                        'available': False,
                        'estimated_rows': 0,
                        'error': 'Source not found'
                    }
            except Exception as e:
                dataset_analysis[dataset] = {
                    'available': False,
                    'estimated_rows': 0,
                    'error': str(e)
                }
        
        # Calculate column statistics
        workspace_columns = mapping_config.get('workspace_columns', {})
        column_analysis = {
            'total_columns': len(workspace_columns),
            'anchor_columns': len(execution_plan.phase_1_columns),
            'literal_columns': len(execution_plan.phase_2_columns),
            'fk_columns': len(execution_plan.phase_3_columns),
            'relationship_context_columns': len(execution_plan.phase_4_columns),
            'external_ontology_columns': len(execution_plan.external_ontology_columns)
        }
        
        # Determine readiness
        all_datasets_available = all(
            ds.get('available', False) for ds in dataset_analysis.values()
        )
        has_columns = column_analysis['total_columns'] > 0
        ready_to_execute = all_datasets_available and has_columns
        
        # Generate warnings
        warnings = []
        if not has_columns:
            warnings.append("No columns configured in workspace")
        if column_analysis['anchor_columns'] == 0:
            warnings.append("No anchor columns - entities will use auto-generated IDs")
        if total_estimated_rows > 10000:
            warnings.append(f"Large dataset ({total_estimated_rows:,} rows) - execution may take time")
        
        unavailable_datasets = [
            name for name, info in dataset_analysis.items() 
            if not info.get('available', False)
        ]
        if unavailable_datasets:
            warnings.extend([
                f"Dataset '{name}' is not available" for name in unavailable_datasets
            ])
        
        return {
            'status': 'analysis_complete',
            'analysis_name': analysis_name,
            'ready_to_execute': ready_to_execute,
            'column_analysis': column_analysis,
            'dataset_analysis': dataset_analysis,
            'execution_phases': {
                'phase_1_entities': column_analysis['anchor_columns'],
                'phase_2_literals': column_analysis['literal_columns'],
                'phase_3_relationships': column_analysis['fk_columns'],
                'phase_4_contexts': column_analysis['relationship_context_columns'],
                'external_ontology': column_analysis['external_ontology_columns']
            },
            'estimated_metrics': {
                'total_rows': total_estimated_rows,
                'estimated_resources': total_estimated_rows * column_analysis['total_columns'],
                'estimated_triples': total_estimated_rows * column_analysis['total_columns'] * 2  # Rough estimate
            },
            'warnings': warnings
        } 