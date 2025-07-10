"""
Helper class for extracting data from mapping configurations.

Provides utility methods to parse mapping configurations and extract
dataset names, column mappings, and type information needed for correlation analysis.
"""

import logging
from typing import Dict, List, Set, Any, Optional

from arkumu.importer.services.mapping_validation.validator import MappingValidator

logger = logging.getLogger(__name__)


class MappingExtractor:
    """Helper class for extracting data from mapping configurations."""
    
    @staticmethod
    def extract_expected_datasets(mapping_config: Dict) -> List[str]:
        """
        Extract unique dataset names from mapping configuration.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            List of unique dataset names found in the mapping
        """
        workspace_columns = mapping_config.get('workspace_columns', {})
        datasets = set()
        
        for col_id, col_data in MappingValidator.iterate_workspace_columns(workspace_columns):
            dataset_name = col_data.get('dataset')
            if dataset_name:
                datasets.add(dataset_name)
        
        result = list(datasets)
        logger.debug(f"Extracted {len(result)} datasets from mapping: {result}")
        return result
    
    @staticmethod
    def extract_columns_per_dataset(mapping_config: Dict) -> Dict[str, List[str]]:
        """
        Extract required columns per dataset.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            Dictionary mapping dataset names to their required column lists
        """
        workspace_columns = mapping_config.get('workspace_columns', {})
        dataset_columns = {}
        
        for col_id, col_data in MappingValidator.iterate_workspace_columns(workspace_columns):
            dataset_name = col_data.get('dataset')
            column_name = col_data.get('name')
            
            if dataset_name and column_name:
                if dataset_name not in dataset_columns:
                    dataset_columns[dataset_name] = []
                dataset_columns[dataset_name].append(column_name)
        
        logger.debug(f"Extracted columns for {len(dataset_columns)} datasets")
        return dataset_columns
    
    @staticmethod
    def extract_column_types_per_dataset(mapping_config: Dict) -> Dict[str, Dict[str, str]]:
        """
        Extract column types per dataset.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            Dictionary mapping dataset names to column name -> type mappings
        """
        workspace_columns = mapping_config.get('workspace_columns', {})
        dataset_types = {}
        
        for col_id, col_data in MappingValidator.iterate_workspace_columns(workspace_columns):
            dataset_name = col_data.get('dataset')
            column_name = col_data.get('name')
            column_type = col_data.get('type', 'string')
            
            if dataset_name and column_name:
                if dataset_name not in dataset_types:
                    dataset_types[dataset_name] = {}
                dataset_types[dataset_name][column_name] = column_type
        
        return dataset_types
    
    @staticmethod
    def extract_workspace_columns_for_dataset(mapping_config: Dict, dataset_name: str) -> Dict[str, Any]:
        """
        Extract workspace columns for a specific dataset from mapping configuration.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            dataset_name: Name of the dataset to extract columns for
            
        Returns:
            Dictionary of workspace columns for the specified dataset
        """
        workspace_columns = {}
        all_workspace_columns = mapping_config.get('workspace_columns', {})
        
        for col_id, col_data in MappingValidator.iterate_workspace_columns(all_workspace_columns):
            if col_data.get('dataset') == dataset_name:
                workspace_columns[col_id] = col_data
        
        logger.debug(f"Extracted {len(workspace_columns)} columns for dataset '{dataset_name}'")
        return workspace_columns
    
    @staticmethod
    def extract_relationships(mapping_config: Dict) -> List[Dict]:
        """
        Extract foreign key relationships from mapping configuration.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            List of relationship configurations
        """
        relationships = []
        
        # Check for relationships in the mapping config
        if 'fk_relationships' in mapping_config:
            fk_relationships = mapping_config['fk_relationships']
            if isinstance(fk_relationships, dict):
                for fk_id, fk_config in fk_relationships.items():
                    if isinstance(fk_config, dict):
                        relationships.append({
                            'id': fk_id,
                            'source_dataset': fk_config.get('source_dataset'),
                            'source_column': fk_config.get('source_column'),
                            'target_dataset': fk_config.get('target_dataset'),
                            'target_column': fk_config.get('target_column')
                        })
        
        logger.debug(f"Extracted {len(relationships)} relationships from mapping")
        return relationships
    
    @staticmethod
    def validate_mapping_structure(mapping_config: Dict) -> Dict[str, Any]:
        """
        Validate the basic structure of a mapping configuration.
        Uses existing MappingValidator for consistency.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            Dictionary with validation results
        """
        # Use existing MappingValidator for validation
        validation_result = MappingValidator.validate_mapping_completeness(mapping_config)
        
        # Extract datasets for additional info
        datasets = set()
        workspace_columns = mapping_config.get('workspace_columns', {})
        
        for col_id, col_data in MappingValidator.iterate_workspace_columns(workspace_columns):
            dataset_name = col_data.get('dataset')
            if dataset_name:
                datasets.add(dataset_name)
        
        # Convert to expected format
        return {
            'is_valid': validation_result['is_complete'],
            'issues': [issue['message'] for issue in validation_result['issues']],
            'has_workspace_columns': 'workspace_columns' in mapping_config and bool(mapping_config['workspace_columns']),
            'has_datasets': len(datasets) > 0,
            'dataset_count': len(datasets)
        }