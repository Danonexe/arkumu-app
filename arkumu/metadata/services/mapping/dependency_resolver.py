"""
Dependency Resolver - Builds processing order for datasets with FK relationships.

This module is responsible for:
- Analyzing FK dependencies between datasets
- Creating topological sort for processing order
- Optimizing processing layers for parallel execution
"""

import logging
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, deque

from .processing_plan import FKConfig

logger = logging.getLogger(__name__)


class DependencyResolver:
    """Resolves FK dependencies and determines optimal processing order."""
    
    def __init__(self):
        pass
    
    def build_processing_order(self, 
                             fk_configs: Dict[str, FKConfig],
                             all_datasets: List[str]) -> List[List[str]]:
        """
        Build processing order for datasets based on FK dependencies.
        
        Args:
            fk_configs: FK configurations
            all_datasets: All available datasets
            
        Returns:
            List of processing layers, where each layer can be processed in parallel
            Example: [['institutions'], ['researchers', 'departments'], ['projects']]
        """
        logger.info(f"Building processing order for {len(all_datasets)} datasets with {len(fk_configs)} FK relationships")
        
        # Build dependency graph
        dependencies = self._build_dependency_graph(fk_configs, all_datasets)
        
        # Perform topological sort with layering
        processing_layers = self._topological_sort_with_layers(dependencies, all_datasets)
        
        logger.info(f"Built processing order with {len(processing_layers)} layers: {processing_layers}")
        return processing_layers
    
    def _build_dependency_graph(self, 
                              fk_configs: Dict[str, FKConfig],
                              all_datasets: List[str]) -> Dict[str, Set[str]]:
        """
        Build dependency graph from FK configurations.
        
        Args:
            fk_configs: FK configurations
            all_datasets: All available datasets
            
        Returns:
            Dict mapping dataset to set of datasets it depends on
        """
        dependencies = defaultdict(set)
        
        # Initialize all datasets with empty dependencies
        for dataset in all_datasets:
            dependencies[dataset] = set()
        
        # Add FK dependencies
        for fk_config in fk_configs.values():
            source = fk_config.source_dataset
            target = fk_config.target_dataset
            
            # Source dataset depends on target dataset
            dependencies[source].add(target)
            
            logger.debug(f"Added dependency: {source} depends on {target}")
        
        return dict(dependencies)
    
    def _topological_sort_with_layers(self, 
                                    dependencies: Dict[str, Set[str]],
                                    all_datasets: List[str]) -> List[List[str]]:
        """
        Perform topological sort with layer grouping for parallel processing.
        
        Args:
            dependencies: Dependency graph
            all_datasets: All datasets to sort
            
        Returns:
            List of processing layers
        """
        # Calculate in-degrees (number of dependencies)
        in_degree = {dataset: 0 for dataset in all_datasets}
        
        for dataset, deps in dependencies.items():
            for dep in deps:
                if dep in in_degree:  # Only count dependencies that exist in our dataset list
                    in_degree[dataset] += 1
        
        processing_layers = []
        remaining_datasets = set(all_datasets)
        
        while remaining_datasets:
            # Find all datasets with no remaining dependencies (in-degree = 0)
            current_layer = [
                dataset for dataset in remaining_datasets 
                if in_degree[dataset] == 0
            ]
            
            if not current_layer:
                # Circular dependency detected - break the cycle by selecting arbitrary dataset
                logger.warning("Circular dependency detected, breaking cycle")
                current_layer = [min(remaining_datasets)]  # Take alphabetically first
            
            processing_layers.append(current_layer)
            
            # Remove processed datasets and update in-degrees
            for dataset in current_layer:
                remaining_datasets.remove(dataset)
                
                # Decrease in-degree for datasets that depend on this one
                for other_dataset in remaining_datasets:
                    if dataset in dependencies[other_dataset]:
                        in_degree[other_dataset] -= 1
        
        return processing_layers
    
    def validate_processing_order(self, 
                                processing_layers: List[List[str]],
                                fk_configs: Dict[str, FKConfig]) -> List[str]:
        """
        Validate that processing order respects FK dependencies.
        
        Args:
            processing_layers: Proposed processing order
            fk_configs: FK configurations to validate against
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Build dataset to layer mapping
        dataset_to_layer = {}
        for layer_num, layer_datasets in enumerate(processing_layers):
            for dataset in layer_datasets:
                dataset_to_layer[dataset] = layer_num
        
        # Check each FK relationship
        for fk_config in fk_configs.values():
            source = fk_config.source_dataset
            target = fk_config.target_dataset
            
            source_layer = dataset_to_layer.get(source)
            target_layer = dataset_to_layer.get(target)
            
            if source_layer is None:
                errors.append(f"Source dataset '{source}' not found in processing order")
                continue
            
            if target_layer is None:
                errors.append(f"Target dataset '{target}' not found in processing order")
                continue
            
            # Source should be processed after target (higher layer number)
            if source_layer <= target_layer:
                errors.append(
                    f"FK dependency violation: {source} (layer {source_layer}) "
                    f"depends on {target} (layer {target_layer}), but is processed before or at same time"
                )
        
        return errors
    
    def optimize_processing_order(self, 
                                processing_layers: List[List[str]],
                                dataset_sizes: Dict[str, int] = None) -> List[List[str]]:
        """
        Optimize processing order within layers based on dataset characteristics.
        
        Args:
            processing_layers: Current processing order
            dataset_sizes: Optional mapping of dataset to size (rows)
            
        Returns:
            Optimized processing order
        """
        optimized_layers = []
        
        for layer in processing_layers:
            if len(layer) <= 1:
                optimized_layers.append(layer)
                continue
            
            # Sort within layer for optimization
            if dataset_sizes:
                # Process smaller datasets first (faster completion)
                sorted_layer = sorted(layer, key=lambda d: dataset_sizes.get(d, 0))
            else:
                # Alphabetical sort for consistency
                sorted_layer = sorted(layer)
            
            optimized_layers.append(sorted_layer)
        
        return optimized_layers
    
    def analyze_processing_complexity(self, 
                                   processing_layers: List[List[str]],
                                   fk_configs: Dict[str, FKConfig]) -> Dict[str, Any]:
        """
        Analyze the complexity of the processing order.
        
        Args:
            processing_layers: Processing order to analyze
            fk_configs: FK configurations
            
        Returns:
            Analysis results
        """
        total_datasets = sum(len(layer) for layer in processing_layers)
        max_parallel = max(len(layer) for layer in processing_layers) if processing_layers else 0
        
        # Calculate FK relationships per layer
        fk_relationships_per_layer = []
        for layer_num, layer_datasets in enumerate(processing_layers):
            layer_fks = [
                fk for fk in fk_configs.values()
                if fk.source_dataset in layer_datasets
            ]
            fk_relationships_per_layer.append(len(layer_fks))
        
        analysis = {
            'total_datasets': total_datasets,
            'total_layers': len(processing_layers),
            'max_parallel_datasets': max_parallel,
            'avg_datasets_per_layer': total_datasets / len(processing_layers) if processing_layers else 0,
            'fk_relationships_per_layer': fk_relationships_per_layer,
            'parallelization_efficiency': max_parallel / total_datasets if total_datasets > 0 else 0,
            'processing_layers': processing_layers
        }
        
        return analysis
    
    def suggest_optimizations(self, 
                            processing_layers: List[List[str]],
                            fk_configs: Dict[str, FKConfig]) -> List[str]:
        """
        Suggest optimizations for processing order.
        
        Args:
            processing_layers: Current processing order
            fk_configs: FK configurations
            
        Returns:
            List of optimization suggestions
        """
        suggestions = []
        
        # Check for very large layers
        for layer_num, layer in enumerate(processing_layers):
            if len(layer) > 10:
                suggestions.append(
                    f"Layer {layer_num} has {len(layer)} datasets - consider splitting FK relationships to improve parallelization"
                )
        
        # Check for very deep dependency chains
        if len(processing_layers) > 5:
            suggestions.append(
                f"Processing requires {len(processing_layers)} sequential layers - consider if all FK relationships are necessary"
            )
        
        # Check for datasets with many dependencies
        dependency_counts = defaultdict(int)
        for fk_config in fk_configs.values():
            dependency_counts[fk_config.source_dataset] += 1
        
        for dataset, dep_count in dependency_counts.items():
            if dep_count > 5:
                suggestions.append(
                    f"Dataset '{dataset}' has {dep_count} FK dependencies - consider data model simplification"
                )
        
        return suggestions 