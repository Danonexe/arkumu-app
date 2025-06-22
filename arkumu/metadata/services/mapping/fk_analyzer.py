"""
FK Analyzer - Extracts and analyzes foreign key configurations.

This module is responsible for:
- Parsing FK configurations from workspace_columns
- Validating FK target existence 
- Building FK relationship maps
"""

import logging
from typing import Dict, List, Any, Optional
import re

from .processing_plan import FKConfig, FKDirection, ValidationResult

logger = logging.getLogger(__name__)


class FKAnalyzer:
    """Analyzes foreign key configurations from GUI mapping data."""
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def extract_fk_configurations(self, workspace_columns: Dict[str, Any]) -> Dict[str, FKConfig]:
        """
        Extract FK configurations from workspace_columns mapping.
        
        Args:
            workspace_columns: GUI mapping configuration
            
        Returns:
            Dictionary mapping column_id to FKConfig
        """
        fk_configs = {}
        
        for column_id, column_config in workspace_columns.items():
            if not column_config.get('is_fk', False):
                continue
                
            fk_config_data = column_config.get('fk_config', {})
            if not fk_config_data:
                logger.warning(f"Column {column_id} marked as FK but missing fk_config")
                continue
            
            try:
                # Parse column_id: "org::dataset::column"
                source_info = self._parse_column_id(column_id)
                if not source_info:
                    logger.error(f"Could not parse column_id: {column_id}")
                    continue
                
                # Create FK configuration
                fk_config = FKConfig(
                    source_dataset=source_info['dataset'],
                    source_column=source_info['column'],
                    target_dataset=fk_config_data.get('target_dataset', ''),
                    target_column=fk_config_data.get('target_column', ''),
                    direction=FKDirection(fk_config_data.get('direction', 'outbound')),
                    predicate_uri=fk_config_data.get('predicate_uri')
                )
                
                fk_configs[column_id] = fk_config
                logger.info(f"Extracted FK: {fk_config.source_dataset}.{fk_config.source_column} → {fk_config.target_dataset}.{fk_config.target_column}")
                
            except Exception as e:
                logger.error(f"Error processing FK config for {column_id}: {e}")
                continue
        
        logger.info(f"Extracted {len(fk_configs)} FK configurations")
        return fk_configs
    
    def validate_fk_configurations(self, 
                                 fk_configs: Dict[str, FKConfig],
                                 available_datasets: List[str]) -> ValidationResult:
        """
        Validate FK configurations against available datasets.
        
        Args:
            fk_configs: FK configurations to validate
            available_datasets: List of available dataset names
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        for column_id, fk_config in fk_configs.items():
            # Check source dataset availability
            if fk_config.source_dataset not in available_datasets:
                result.add_error(
                    f"FK source dataset '{fk_config.source_dataset}' not found in available datasets"
                )
            
            # Check target dataset availability
            if fk_config.target_dataset not in available_datasets:
                result.add_error(
                    f"FK target dataset '{fk_config.target_dataset}' not found in available datasets"
                )
            
            # Validate FK configuration completeness
            if not fk_config.target_column:
                result.add_error(
                    f"FK configuration for {column_id} missing target_column"
                )
            
            # Check for self-references (warnings only)
            if fk_config.source_dataset == fk_config.target_dataset:
                if fk_config.source_column == fk_config.target_column:
                    result.add_error(
                        f"FK configuration for {column_id} references itself"
                    )
                else:
                    result.add_warning(
                        f"FK configuration for {column_id} is a self-reference within dataset {fk_config.source_dataset}"
                    )
        
        # Check for circular dependencies
        circular_deps = self._detect_circular_dependencies(fk_configs)
        if circular_deps:
            result.add_error(f"Circular FK dependencies detected: {circular_deps}")
        
        return result
    
    def get_fk_dependencies(self, fk_configs: Dict[str, FKConfig]) -> Dict[str, List[str]]:
        """
        Build dependency map: dataset -> [datasets it depends on].
        
        Args:
            fk_configs: FK configurations
            
        Returns:
            Dictionary mapping dataset to list of dependencies
        """
        dependencies = {}
        
        for fk_config in fk_configs.values():
            source = fk_config.source_dataset
            target = fk_config.target_dataset
            
            if source not in dependencies:
                dependencies[source] = []
            
            if target not in dependencies[source]:
                dependencies[source].append(target)
        
        return dependencies
    
    def _parse_column_id(self, column_id: str) -> Optional[Dict[str, str]]:
        """
        Parse column_id format: "org::dataset::column"
        
        Args:
            column_id: Column identifier from workspace_columns
            
        Returns:
            Dictionary with parsed components or None if invalid
        """
        try:
            # Expected format: "org::dataset.csv::column_name"
            parts = column_id.split('::')
            if len(parts) != 3:
                return None
            
            org, dataset, column = parts
            
            # Remove .csv extension if present
            if dataset.endswith('.csv'):
                dataset = dataset[:-4]
            
            return {
                'organization': org,
                'dataset': dataset,
                'column': column
            }
            
        except Exception as e:
            logger.error(f"Error parsing column_id '{column_id}': {e}")
            return None
    
    def _detect_circular_dependencies(self, fk_configs: Dict[str, FKConfig]) -> List[str]:
        """
        Detect circular dependencies in FK relationships.
        
        Args:
            fk_configs: FK configurations to check
            
        Returns:
            List of datasets involved in circular dependencies
        """
        dependencies = self.get_fk_dependencies(fk_configs)
        
        def has_cycle(dataset: str, visited: set, rec_stack: set) -> bool:
            """DFS to detect cycles in dependency graph."""
            visited.add(dataset)
            rec_stack.add(dataset)
            
            for dep in dependencies.get(dataset, []):
                if dep not in visited:
                    if has_cycle(dep, visited, rec_stack):
                        return True
                elif dep in rec_stack:
                    return True
            
            rec_stack.remove(dataset)
            return False
        
        visited = set()
        circular_datasets = []
        
        for dataset in dependencies:
            if dataset not in visited:
                if has_cycle(dataset, visited, set()):
                    circular_datasets.append(dataset)
        
        return circular_datasets
    
    def analyze_fk_complexity(self, fk_configs: Dict[str, FKConfig]) -> Dict[str, Any]:
        """
        Analyze FK relationship complexity for processing optimization.
        
        Args:
            fk_configs: FK configurations to analyze
            
        Returns:
            Dictionary with complexity analysis
        """
        analysis = {
            'total_fk_relationships': len(fk_configs),
            'datasets_with_fks': len(set(fk.source_dataset for fk in fk_configs.values())),
            'target_datasets': len(set(fk.target_dataset for fk in fk_configs.values())),
            'self_references': 0,
            'cross_dataset_refs': 0,
            'bidirectional_refs': 0
        }
        
        for fk_config in fk_configs.values():
            if fk_config.source_dataset == fk_config.target_dataset:
                analysis['self_references'] += 1
            else:
                analysis['cross_dataset_refs'] += 1
            
            if fk_config.direction == FKDirection.BIDIRECTIONAL:
                analysis['bidirectional_refs'] += 1
        
        return analysis
