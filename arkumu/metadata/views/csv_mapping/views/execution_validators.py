"""
CSV Mapping Execution Validators

This module contains validation logic for CSV mapping execution:
- Pre-execution validation
- Configuration validation  
- Dataset availability validation
- Comprehensive mapping validation

Consolidated to use centralized validation services for consistency.
"""

import logging
from typing import Dict, List, Any, Optional

from arkumu.importer.services.execution.execution_engine import MappingExecutionEngine
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.importer.services.mapping_validation.validator import MappingValidator

logger = logging.getLogger(__name__)


class ExecutionValidator:
    """Handles validation of mapping configurations for execution."""
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def validate_mapping_for_execution(self, mapping_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate mapping configuration for execution readiness using centralized validation."""
        
        # Use centralized validation service for configuration structure
        validation_service = ValidationService()
        structure_result = validation_service.validate_mapping_config(mapping_config)
        
        validation_result = {
            'is_valid': structure_result.is_valid,
            'errors': structure_result.errors.copy(),
            'warnings': structure_result.warnings.copy()
        }
        
        try:
            # Additional execution-specific validation
            selected_datasets = mapping_config.get('selected_datasets', [])
            workspace_columns = mapping_config.get('workspace_columns', {})
            
            # Validate datasets are still available in S3
            if selected_datasets:
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
            
            # Check for at least one anchor column (execution-specific requirement)
            if workspace_columns:
                has_anchor = any(
                    any(col.get('is_anchor', False) for col in columns.values())
                    for columns in workspace_columns.values()
                )
                
                if not has_anchor:
                    validation_result['warnings'].append(
                        "No anchor columns defined - entities will be created with auto-generated IDs"
                    )
            
        except Exception as e:
            validation_result['errors'].append(f"Execution validation error: {str(e)}")
            validation_result['is_valid'] = False
        
        return validation_result
    
    def comprehensive_mapping_validation(self, mapping_config: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive mapping validation using centralized validation services."""
        
        # Use centralized validation service for comprehensive structure validation
        validation_service = ValidationService()
        structure_result = validation_service.validate_mapping_config(mapping_config)
        
        result = {
            'is_valid': structure_result.is_valid,
            'is_executable': structure_result.is_valid,
            'errors': structure_result.errors.copy(),
            'warnings': structure_result.warnings.copy(),
            'details': {}
        }
        
        try:
            # Support both old and new dataset format keys
            selected_datasets = mapping_config.get('workspace_datasets', mapping_config.get('selected_datasets', []))
            workspace_columns = mapping_config.get('workspace_columns', {})
            
            # Execution plan analysis (if we need the old GUIMappingProcessor)
            try:
                # Note: This should be migrated to use the new execution engine's analysis
                # For now, we'll skip this and rely on the centralized validation
                # processor = GUIMappingProcessor()
                # execution_plan = processor.analyze_gui_mapping_config(mapping_config)
                
                # Calculate plan details from validated config
                total_columns = sum(len(columns) for columns in workspace_columns.values())
                anchor_columns = sum(
                    sum(1 for col in columns.values() if col.get('is_anchor', False))
                    for columns in workspace_columns.values()
                )
                fk_relationships = len(mapping_config.get('fk_relationships', {}))
                
                result['details']['execution_plan'] = {
                    'total_columns': total_columns,
                    'anchor_columns': anchor_columns,
                    'fk_relationships': fk_relationships,
                    'external_ontologies': len(mapping_config.get('external_ontologies', {})),
                    'relationship_contexts': len(mapping_config.get('relationship_contexts', {}))
                }
            except Exception as e:
                result['warnings'].append(f"Could not analyze execution plan: {str(e)}")
            
            # Dataset availability check (execution-specific)
            if selected_datasets:
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
            result['errors'].append(f"Comprehensive validation error: {str(e)}")
            result['is_valid'] = False
            result['is_executable'] = False
        
        return result


class ExecutionAnalyzer:
    """Analyzes mapping configurations for execution planning."""
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def analyze_execution_plan(self, mapping_config: Dict[str, Any], analysis_name: str) -> Dict[str, Any]:
        """Analyze mapping for execution readiness using centralized validation."""
        
        # Use centralized validation for configuration analysis
        validation_service = ValidationService()
        validation_result = validation_service.validate_mapping_config(mapping_config)
        
        # Support both old and new dataset format
        selected_datasets = mapping_config.get('workspace_datasets', mapping_config.get('selected_datasets', []))
        workspace_columns = mapping_config.get('workspace_columns', {})
        
        # Dataset analysis with S3 availability check
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
        
        # Calculate column statistics from validated configuration
        total_columns = sum(len(columns) for columns in workspace_columns.values())
        anchor_columns = sum(
            sum(1 for col in columns.values() if col.get('is_anchor', False))
            for columns in workspace_columns.values()
        )
        fk_relationships = len(mapping_config.get('fk_relationships', {}))
        external_ontologies = len(mapping_config.get('external_ontologies', {}))
        relationship_contexts = len(mapping_config.get('relationship_contexts', {}))
        
        column_analysis = {
            'total_columns': total_columns,
            'anchor_columns': anchor_columns,
            'fk_columns': fk_relationships,
            'external_ontology_columns': external_ontologies,
            'relationship_context_columns': relationship_contexts
        }
        
        # Determine readiness based on validation and data availability
        all_datasets_available = all(
            ds.get('available', False) for ds in dataset_analysis.values()
        )
        has_columns = column_analysis['total_columns'] > 0
        config_valid = validation_result.is_valid
        ready_to_execute = all_datasets_available and has_columns and config_valid
        
        # Combine warnings from validation and analysis
        warnings = validation_result.warnings.copy()
        
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
            'validation_errors': validation_result.errors,
            'column_analysis': column_analysis,
            'dataset_analysis': dataset_analysis,
            'execution_phases': {
                'anchor_columns': column_analysis['anchor_columns'],
                'fk_relationships': column_analysis['fk_columns'],
                'external_ontologies': column_analysis['external_ontology_columns'],
                'relationship_contexts': column_analysis['relationship_context_columns']
            },
            'estimated_metrics': {
                'total_rows': total_estimated_rows,
                'estimated_resources': total_estimated_rows * column_analysis['total_columns'],
                'estimated_triples': total_estimated_rows * column_analysis['total_columns'] * 2  # Rough estimate
            },
            'warnings': warnings
        } 