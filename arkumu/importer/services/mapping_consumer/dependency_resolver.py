"""
Dependency Resolver

Handles FK dependencies and determines processing order for datasets.
"""

import logging
from typing import Dict, Any, List, Set, Tuple, Optional
from dataclasses import dataclass
from .config_translator import ExecutionConfig, DatasetConfig, FKRelationship

logger = logging.getLogger(__name__)


@dataclass
class DependencyGraph:
    """Represents dependencies between datasets"""
    nodes: Set[str]  # Dataset names
    edges: List[Tuple[str, str]]  # (source, target) pairs - source depends on target
    
    def get_dependencies(self, dataset: str) -> List[str]:
        """Get direct dependencies for a dataset"""
        return [target for source, target in self.edges if source == dataset]
    
    def get_dependents(self, dataset: str) -> List[str]:
        """Get datasets that depend on this dataset"""
        return [source for source, target in self.edges if target == dataset]
    
    def has_cycles(self) -> bool:
        """Check if the dependency graph has cycles"""
        return len(self.topological_sort()) != len(self.nodes)
    
    def topological_sort(self) -> List[str]:
        """Return datasets in dependency order (dependencies first)"""
        # Kahn's algorithm for topological sorting
        in_degree = {node: 0 for node in self.nodes}
        for source, target in self.edges:
            in_degree[source] += 1
        
        queue = [node for node in self.nodes if in_degree[node] == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            # Remove edges from this node
            for source, target in self.edges:
                if target == node:
                    in_degree[source] -= 1
                    if in_degree[source] == 0:
                        queue.append(source)
        
        return result


@dataclass
class ProcessingPhase:
    """A phase in the processing plan"""
    phase_number: int
    phase_name: str
    datasets: List[str]
    description: str
    can_parallel: bool = True
    estimated_complexity: str = "medium"
    
    def add_dataset(self, dataset_name: str):
        """Add a dataset to this phase"""
        if dataset_name not in self.datasets:
            self.datasets.append(dataset_name)


class DependencyResolver:
    """
    Resolves FK dependencies and determines optimal processing order.
    
    Analyzes FK relationships to build a dependency graph and creates
    processing phases that respect dependencies while maximizing parallelism.
    """
    
    def resolve_dependencies(self, execution_config: ExecutionConfig) -> List[ProcessingPhase]:
        """
        Resolve dependencies and create processing phases.
        
        Args:
            execution_config: Execution configuration with FK relationships
            
        Returns:
            List of processing phases in execution order
        """
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(execution_config)
        
        # Check for circular dependencies
        if dependency_graph.has_cycles():
            logger.warning("Circular dependencies detected - will process with warnings")
            return self._handle_circular_dependencies(execution_config, dependency_graph)
        
        # Create processing phases
        phases = self._create_processing_phases(execution_config, dependency_graph)
        
        # Update execution config
        execution_config.processing_phases = [
            # Convert our ProcessingPhase to ExecutionPhase format
            type('ExecutionPhase', (), {
                'phase_number': phase.phase_number,
                'phase_name': phase.phase_name,
                'datasets': phase.datasets,
                'description': phase.description,
                'dependencies': self._get_phase_dependencies(phase, dependency_graph)
            })()
            for phase in phases
        ]
        
        logger.info(f"Created {len(phases)} processing phases for {len(execution_config.datasets)} datasets")
        return phases
    
    def _build_dependency_graph(self, execution_config: ExecutionConfig) -> DependencyGraph:
        """Build dependency graph from FK relationships"""
        
        # Get all dataset names
        dataset_names = set(dataset.dataset_name for dataset in execution_config.datasets)
        
        # Build edges from FK relationships
        edges = []
        for fk in execution_config.fk_relationships:
            source_dataset = fk.source_dataset
            target_dataset = fk.target_dataset
            
            # Only add edge if both datasets are in our processing list
            if source_dataset in dataset_names and target_dataset in dataset_names:
                # Source dataset depends on target dataset
                if (source_dataset, target_dataset) not in edges:
                    edges.append((source_dataset, target_dataset))
                    logger.debug(f"Dependency: {source_dataset} depends on {target_dataset}")
        
        graph = DependencyGraph(nodes=dataset_names, edges=edges)
        logger.info(f"Built dependency graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        
        return graph
    
    def _create_processing_phases(self, execution_config: ExecutionConfig, 
                                dependency_graph: DependencyGraph) -> List[ProcessingPhase]:
        """Create processing phases respecting dependencies"""
        
        # Get topological order
        ordered_datasets = dependency_graph.topological_sort()
        
        if len(ordered_datasets) != len(dependency_graph.nodes):
            logger.warning("Could not resolve all dependencies - some datasets may be processed out of order")
            # Add any missing datasets
            for dataset_name in dependency_graph.nodes:
                if dataset_name not in ordered_datasets:
                    ordered_datasets.append(dataset_name)
        
        # Group datasets into phases
        phases = []
        processed_datasets = set()
        phase_number = 1
        
        while len(processed_datasets) < len(ordered_datasets):
            # Find datasets that can be processed in this phase
            phase_datasets = []
            
            for dataset_name in ordered_datasets:
                if dataset_name in processed_datasets:
                    continue
                
                # Check if all dependencies are satisfied
                dependencies = dependency_graph.get_dependencies(dataset_name)
                if all(dep in processed_datasets for dep in dependencies):
                    phase_datasets.append(dataset_name)
            
            if not phase_datasets:
                # No datasets can be processed - handle remaining datasets
                remaining = [d for d in ordered_datasets if d not in processed_datasets]
                logger.warning(f"Could not resolve dependencies for datasets: {remaining}")
                phase_datasets = remaining
            
            # Create phase
            phase = ProcessingPhase(
                phase_number=phase_number,
                phase_name=f"Phase {phase_number}",
                datasets=phase_datasets,
                description=self._generate_phase_description(phase_datasets, dependency_graph),
                can_parallel=len(phase_datasets) > 1
            )
            
            phases.append(phase)
            processed_datasets.update(phase_datasets)
            phase_number += 1
        
        # Enhance phases with additional information
        self._enhance_phases(phases, execution_config, dependency_graph)
        
        return phases
    
    def _generate_phase_description(self, datasets: List[str], 
                                  dependency_graph: DependencyGraph) -> str:
        """Generate description for a processing phase"""
        
        if len(datasets) == 1:
            dataset = datasets[0]
            dependencies = dependency_graph.get_dependencies(dataset)
            if dependencies:
                return f"Process {dataset} (depends on: {', '.join(dependencies)})"
            else:
                return f"Process {dataset} (no dependencies)"
        else:
            return f"Process {len(datasets)} datasets in parallel: {', '.join(datasets)}"
    
    def _enhance_phases(self, phases: List[ProcessingPhase], 
                       execution_config: ExecutionConfig,
                       dependency_graph: DependencyGraph):
        """Enhance phases with complexity estimates and better names"""
        
        for phase in phases:
            # Calculate complexity based on datasets in phase
            total_columns = 0
            total_fk_relationships = 0
            has_multi_value = False
            has_external_ontology = False
            
            for dataset_name in phase.datasets:
                dataset_config = execution_config.get_dataset_config(dataset_name)
                if dataset_config:
                    total_columns += len(dataset_config.columns)
                    
                    # Check for complex column types
                    for column in dataset_config.columns:
                        if column.is_multi_value:
                            has_multi_value = True
                        if column.is_external_ontology:
                            has_external_ontology = True
                
                # Count FK relationships
                fk_count = len([fk for fk in execution_config.fk_relationships 
                              if fk.source_dataset == dataset_name])
                total_fk_relationships += fk_count
            
            # Estimate complexity
            complexity_score = 0
            if total_columns > 20:
                complexity_score += 2
            elif total_columns > 10:
                complexity_score += 1
            
            if total_fk_relationships > 5:
                complexity_score += 2
            elif total_fk_relationships > 0:
                complexity_score += 1
            
            if has_multi_value:
                complexity_score += 1
            if has_external_ontology:
                complexity_score += 1
            
            if complexity_score >= 4:
                phase.estimated_complexity = "high"
            elif complexity_score >= 2:
                phase.estimated_complexity = "medium"
            else:
                phase.estimated_complexity = "low"
            
            # Generate better phase names
            if len(phase.datasets) == 1:
                dataset = phase.datasets[0]
                dependencies = dependency_graph.get_dependencies(dataset)
                if not dependencies:
                    phase.phase_name = f"Foundation Data ({dataset})"
                else:
                    phase.phase_name = f"Dependent Data ({dataset})"
            else:
                if phase.phase_number == 1:
                    phase.phase_name = "Foundation Datasets"
                else:
                    phase.phase_name = f"Dependent Datasets (Level {phase.phase_number})"
    
    def _get_phase_dependencies(self, phase: ProcessingPhase, 
                              dependency_graph: DependencyGraph) -> List[str]:
        """Get dependencies for a phase"""
        dependencies = set()
        
        for dataset in phase.datasets:
            dataset_deps = dependency_graph.get_dependencies(dataset)
            dependencies.update(dataset_deps)
        
        # Remove dependencies that are within the same phase
        return [dep for dep in dependencies if dep not in phase.datasets]
    
    def _handle_circular_dependencies(self, execution_config: ExecutionConfig,
                                    dependency_graph: DependencyGraph) -> List[ProcessingPhase]:
        """Handle circular dependencies by breaking cycles"""
        
        logger.warning("Handling circular dependencies - some FK relationships may be processed as post-processing")
        
        # Simple approach: process all datasets in a single phase
        # In a more sophisticated implementation, we could:
        # 1. Detect strongly connected components
        # 2. Break cycles by deferring some FK relationships
        # 3. Create multi-pass processing
        
        all_datasets = [dataset.dataset_name for dataset in execution_config.datasets]
        
        phase = ProcessingPhase(
            phase_number=1,
            phase_name="All Datasets (Circular Dependencies)",
            datasets=all_datasets,
            description="Process all datasets together due to circular dependencies",
            can_parallel=False,
            estimated_complexity="high"
        )
        
        return [phase]
    
    def analyze_dependencies(self, execution_config: ExecutionConfig) -> Dict[str, Any]:
        """
        Analyze dependencies and return detailed information.
        
        Args:
            execution_config: Execution configuration
            
        Returns:
            Dictionary with dependency analysis
        """
        dependency_graph = self._build_dependency_graph(execution_config)
        
        analysis = {
            'total_datasets': len(dependency_graph.nodes),
            'total_dependencies': len(dependency_graph.edges),
            'has_cycles': dependency_graph.has_cycles(),
            'independent_datasets': [],
            'dependent_datasets': [],
            'dependency_chains': [],
            'complexity_assessment': 'low'
        }
        
        # Classify datasets
        for dataset in dependency_graph.nodes:
            dependencies = dependency_graph.get_dependencies(dataset)
            if not dependencies:
                analysis['independent_datasets'].append(dataset)
            else:
                analysis['dependent_datasets'].append({
                    'dataset': dataset,
                    'dependencies': dependencies,
                    'dependency_count': len(dependencies)
                })
        
        # Find longest dependency chains
        for dataset in dependency_graph.nodes:
            chain = self._find_dependency_chain(dataset, dependency_graph)
            if len(chain) > 1:
                analysis['dependency_chains'].append(chain)
        
        # Assess complexity
        if analysis['has_cycles']:
            analysis['complexity_assessment'] = 'high'
        elif len(analysis['dependency_chains']) > 0:
            max_chain_length = max(len(chain) for chain in analysis['dependency_chains'])
            if max_chain_length > 3:
                analysis['complexity_assessment'] = 'high'
            elif max_chain_length > 2:
                analysis['complexity_assessment'] = 'medium'
        elif len(analysis['dependent_datasets']) > 0:
            analysis['complexity_assessment'] = 'medium'
        
        return analysis
    
    def _find_dependency_chain(self, dataset: str, dependency_graph: DependencyGraph, 
                              visited: Optional[Set[str]] = None) -> List[str]:
        """Find the longest dependency chain starting from a dataset"""
        
        if visited is None:
            visited = set()
        
        if dataset in visited:
            return [dataset]  # Cycle detected
        
        visited.add(dataset)
        dependencies = dependency_graph.get_dependencies(dataset)
        
        if not dependencies:
            return [dataset]
        
        # Find the longest chain among dependencies
        longest_chain = [dataset]
        for dep in dependencies:
            dep_chain = self._find_dependency_chain(dep, dependency_graph, visited.copy())
            if len(dep_chain) + 1 > len(longest_chain):
                longest_chain = [dataset] + dep_chain
        
        return longest_chain
    
    def get_processing_order_summary(self, phases: List[ProcessingPhase]) -> Dict[str, Any]:
        """
        Get a summary of the processing order.
        
        Args:
            phases: List of processing phases
            
        Returns:
            Summary dictionary
        """
        total_datasets = sum(len(phase.datasets) for phase in phases)
        parallel_phases = sum(1 for phase in phases if phase.can_parallel)
        
        return {
            'total_phases': len(phases),
            'total_datasets': total_datasets,
            'parallel_phases': parallel_phases,
            'sequential_phases': len(phases) - parallel_phases,
            'phase_details': [
                {
                    'phase_number': phase.phase_number,
                    'phase_name': phase.phase_name,
                    'datasets': phase.datasets,
                    'dataset_count': len(phase.datasets),
                    'can_parallel': phase.can_parallel,
                    'complexity': phase.estimated_complexity,
                    'description': phase.description
                }
                for phase in phases
            ],
            'processing_strategy_recommendation': self._recommend_processing_strategy(phases)
        }
    
    def _recommend_processing_strategy(self, phases: List[ProcessingPhase]) -> str:
        """Recommend optimal processing strategy based on phases"""
        
        total_datasets = sum(len(phase.datasets) for phase in phases)
        high_complexity_phases = sum(1 for phase in phases if phase.estimated_complexity == "high")
        
        if len(phases) == 1 and total_datasets <= 3:
            return "entity_centric"
        elif len(phases) <= 2 and high_complexity_phases == 0:
            return "streaming_entity_centric"
        else:
            return "multi_phase"