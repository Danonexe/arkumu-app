"""
Execution Strategy Recommender

Advanced service for analyzing mapping complexity and recommending optimal execution strategies.
This service provides intelligent strategy selection based on mapping configuration analysis,
performance estimation, and resource usage prediction.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math

from ..mapping_consumer.config_translator import ExecutionConfig, ColumnConfig, FKRelationship
from ..mapping_consumer.mapping_adapter import MappingAdapter

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Enhanced execution strategy types with comprehensive options"""
    ENTITY_CENTRIC = "entity_centric"
    MAPPING_DRIVEN = "mapping_driven"
    STREAMING = "streaming"
    MULTI_PHASE = "multi_phase"
    HYBRID = "hybrid"
    AUTO = "auto"


class ComplexityLevel(Enum):
    """Complexity levels for mapping analysis"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class FileInfo:
    """Information about input file characteristics"""
    file_size_mb: float
    estimated_rows: int
    estimated_columns: int
    csv_complexity_score: float = 0.0
    has_large_text_fields: bool = False
    has_numeric_fields: bool = False
    encoding: str = "utf-8"
    delimiter: str = ","
    header_rows: int = 1


@dataclass
class MappingComplexityMetrics:
    """Comprehensive metrics for mapping complexity analysis"""
    total_datasets: int = 0
    total_columns: int = 0
    total_relationships: int = 0
    external_ontology_count: int = 0
    multi_value_column_count: int = 0
    anchor_column_count: int = 0
    dependency_depth: int = 0
    relationship_complexity_score: float = 0.0
    data_transformation_complexity: float = 0.0
    integration_complexity: float = 0.0
    overall_complexity: ComplexityLevel = ComplexityLevel.LOW


@dataclass
class ResourceEstimation:
    """Resource usage estimation for strategy execution"""
    estimated_memory_mb: float
    estimated_cpu_cores: int
    estimated_execution_time_minutes: float
    estimated_disk_space_mb: float
    peak_memory_mb: float
    concurrent_processing_capability: int = 1
    scalability_factor: float = 1.0


@dataclass
class StrategyRecommendation:
    """Complete strategy recommendation with detailed analysis"""
    strategy: ExecutionStrategy
    confidence_score: float  # 0-1, higher is more confident
    complexity_metrics: MappingComplexityMetrics
    resource_estimation: ResourceEstimation
    advantages: List[str] = field(default_factory=list)
    disadvantages: List[str] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    performance_notes: List[str] = field(default_factory=list)
    reasoning: str = ""
    alternative_strategies: List[str] = field(default_factory=list)


class ExecutionStrategyRecommender:
    """
    Advanced execution strategy recommender that analyzes mapping complexity
    and provides intelligent strategy recommendations with detailed reasoning.
    """
    
    def __init__(self, mapping_adapter: Optional[MappingAdapter] = None):
        """
        Initialize the execution strategy recommender.
        
        Args:
            mapping_adapter: Optional MappingAdapter instance for loading configurations
        """
        self.mapping_adapter = mapping_adapter or MappingAdapter()
        
        # Complexity analysis thresholds
        self.complexity_thresholds = {
            'small_dataset_rows': 10000,
            'medium_dataset_rows': 100000,
            'large_dataset_rows': 1000000,
            'small_file_mb': 10,
            'medium_file_mb': 100,
            'large_file_mb': 1000,
            'high_relationship_count': 10,
            'high_column_count': 50,
            'high_dataset_count': 10,
            'high_dependency_depth': 5,
            'complex_transformation_threshold': 0.7,
            'memory_limit_mb': 8192,  # 8GB default limit
            'cpu_cores_available': 4
        }
        
        # Strategy-specific configurations
        self.strategy_configs = {
            ExecutionStrategy.ENTITY_CENTRIC: {
                'memory_multiplier': 4.0,
                'cpu_efficiency': 0.9,
                'max_recommended_file_mb': 200,
                'max_recommended_relationships': 15,
                'optimal_complexity': ComplexityLevel.LOW
            },
            ExecutionStrategy.MAPPING_DRIVEN: {
                'memory_multiplier': 2.5,
                'cpu_efficiency': 0.8,
                'max_recommended_file_mb': 500,
                'max_recommended_relationships': 25,
                'optimal_complexity': ComplexityLevel.MEDIUM
            },
            ExecutionStrategy.STREAMING: {
                'memory_multiplier': 1.5,
                'cpu_efficiency': 0.7,
                'max_recommended_file_mb': 2000,
                'max_recommended_relationships': 30,
                'optimal_complexity': ComplexityLevel.HIGH
            },
            ExecutionStrategy.MULTI_PHASE: {
                'memory_multiplier': 1.2,
                'cpu_efficiency': 0.6,
                'max_recommended_file_mb': 10000,
                'max_recommended_relationships': 50,
                'optimal_complexity': ComplexityLevel.EXTREME
            },
            ExecutionStrategy.HYBRID: {
                'memory_multiplier': 2.0,
                'cpu_efficiency': 0.8,
                'max_recommended_file_mb': 1000,
                'max_recommended_relationships': 40,
                'optimal_complexity': ComplexityLevel.HIGH
            }
        }
    
    def recommend_execution_strategy(self, 
                                   execution_config: ExecutionConfig,
                                   file_info: Optional[FileInfo] = None) -> StrategyRecommendation:
        """
        Recommend the optimal execution strategy based on mapping configuration analysis.
        
        Args:
            execution_config: The execution configuration to analyze
            file_info: Optional file information for better estimation
            
        Returns:
            StrategyRecommendation with detailed analysis and reasoning
        """
        logger.info("Starting execution strategy recommendation analysis")
        
        # Analyze mapping complexity
        complexity_metrics = self.analyze_mapping_complexity(execution_config)
        
        # Analyze all available strategies
        strategy_analyses = self._analyze_all_strategies(execution_config, complexity_metrics, file_info)
        
        # Select the best strategy
        best_strategy = max(strategy_analyses, key=lambda x: x.confidence_score)
        
        # Generate detailed reasoning
        best_strategy.reasoning = self._generate_strategy_reasoning(
            best_strategy, complexity_metrics, file_info
        )
        
        # Add alternative strategies
        sorted_strategies = sorted(strategy_analyses, key=lambda x: x.confidence_score, reverse=True)
        best_strategy.alternative_strategies = [
            s.strategy.value for s in sorted_strategies[1:3]  # Top 2 alternatives
        ]
        
        logger.info(f"Recommended strategy: {best_strategy.strategy.value} "
                   f"(confidence: {best_strategy.confidence_score:.2f})")
        
        return best_strategy
    
    def analyze_mapping_complexity(self, execution_config: ExecutionConfig) -> MappingComplexityMetrics:
        """
        Analyze the complexity of a mapping configuration.
        
        Args:
            execution_config: The execution configuration to analyze
            
        Returns:
            MappingComplexityMetrics with detailed complexity analysis
        """
        logger.debug("Analyzing mapping complexity")
        
        metrics = MappingComplexityMetrics()
        
        # Basic counts
        metrics.total_datasets = len(execution_config.datasets)
        metrics.total_columns = sum(len(ds.columns) for ds in execution_config.datasets)
        metrics.total_relationships = len(execution_config.fk_relationships)
        
        # Analyze column types
        all_columns = []
        for dataset in execution_config.datasets:
            all_columns.extend(dataset.columns)
        
        metrics.external_ontology_count = sum(1 for col in all_columns if col.is_external_ontology)
        metrics.multi_value_column_count = sum(1 for col in all_columns if col.is_multi_value)
        metrics.anchor_column_count = sum(1 for col in all_columns if col.is_anchor)
        
        # Calculate dependency depth
        metrics.dependency_depth = self._calculate_dependency_depth(execution_config)
        
        # Calculate relationship complexity
        metrics.relationship_complexity_score = self._calculate_relationship_complexity(execution_config)
        
        # Calculate data transformation complexity
        metrics.data_transformation_complexity = self._calculate_transformation_complexity(all_columns)
        
        # Calculate integration complexity
        metrics.integration_complexity = self._calculate_integration_complexity(execution_config)
        
        # Determine overall complexity level
        metrics.overall_complexity = self._determine_complexity_level(metrics)
        
        logger.debug(f"Mapping complexity analysis complete: {metrics.overall_complexity.value}")
        
        return metrics
    
    def estimate_performance_impact(self, 
                                  strategy: ExecutionStrategy,
                                  mapping_config: ExecutionConfig,
                                  file_info: Optional[FileInfo] = None) -> ResourceEstimation:
        """
        Estimate the performance impact and resource requirements for a strategy.
        
        Args:
            strategy: The execution strategy to analyze
            mapping_config: The mapping configuration
            file_info: Optional file information for better estimation
            
        Returns:
            ResourceEstimation with detailed resource usage predictions
        """
        logger.debug(f"Estimating performance impact for strategy: {strategy.value}")
        
        # Get strategy configuration
        strategy_config = self.strategy_configs.get(strategy, self.strategy_configs[ExecutionStrategy.ENTITY_CENTRIC])
        
        # Estimate base resource requirements
        base_memory_mb = self._estimate_base_memory_usage(mapping_config, file_info)
        estimated_memory_mb = base_memory_mb * strategy_config['memory_multiplier']
        
        # Estimate CPU requirements
        estimated_cpu_cores = max(1, min(
            self.complexity_thresholds['cpu_cores_available'],
            int(len(mapping_config.datasets) / 2) + 1
        ))
        
        # Estimate execution time
        estimated_execution_time_minutes = self._estimate_execution_time(
            strategy, mapping_config, file_info, strategy_config
        )
        
        # Estimate disk space
        estimated_disk_space_mb = self._estimate_disk_space_usage(mapping_config, file_info)
        
        # Calculate peak memory usage
        peak_memory_mb = estimated_memory_mb * 1.5  # Account for peak usage
        
        # Determine concurrent processing capability
        concurrent_processing_capability = self._calculate_concurrent_capability(
            strategy, mapping_config, estimated_memory_mb
        )
        
        # Calculate scalability factor
        scalability_factor = self._calculate_scalability_factor(strategy, mapping_config)
        
        return ResourceEstimation(
            estimated_memory_mb=estimated_memory_mb,
            estimated_cpu_cores=estimated_cpu_cores,
            estimated_execution_time_minutes=estimated_execution_time_minutes,
            estimated_disk_space_mb=estimated_disk_space_mb,
            peak_memory_mb=peak_memory_mb,
            concurrent_processing_capability=concurrent_processing_capability,
            scalability_factor=scalability_factor
        )
    
    def _analyze_all_strategies(self, 
                               execution_config: ExecutionConfig,
                               complexity_metrics: MappingComplexityMetrics,
                               file_info: Optional[FileInfo] = None) -> List[StrategyRecommendation]:
        """Analyze all available strategies and return recommendations"""
        
        recommendations = []
        
        for strategy in ExecutionStrategy:
            if strategy == ExecutionStrategy.AUTO:
                continue  # Skip AUTO as it's not a concrete strategy
            
            # Get resource estimation
            resource_estimation = self.estimate_performance_impact(strategy, execution_config, file_info)
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                strategy, complexity_metrics, resource_estimation, file_info
            )
            
            # Generate strategy-specific analysis
            advantages, disadvantages, requirements, risk_factors, performance_notes = self._analyze_strategy_characteristics(
                strategy, complexity_metrics, resource_estimation, file_info
            )
            
            recommendation = StrategyRecommendation(
                strategy=strategy,
                confidence_score=confidence_score,
                complexity_metrics=complexity_metrics,
                resource_estimation=resource_estimation,
                advantages=advantages,
                disadvantages=disadvantages,
                requirements=requirements,
                risk_factors=risk_factors,
                performance_notes=performance_notes
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def _calculate_dependency_depth(self, execution_config: ExecutionConfig) -> int:
        """Calculate the maximum dependency depth in the configuration"""
        if not execution_config.fk_relationships:
            return 0
        
        # Build dependency graph
        dependencies = {}
        for fk in execution_config.fk_relationships:
            if fk.source_dataset not in dependencies:
                dependencies[fk.source_dataset] = set()
            dependencies[fk.source_dataset].add(fk.target_dataset)
        
        # Calculate maximum depth using DFS
        max_depth = 0
        visited = set()
        
        def dfs(dataset: str, depth: int) -> int:
            if dataset in visited:
                return depth
            visited.add(dataset)
            
            max_child_depth = depth
            for child in dependencies.get(dataset, set()):
                child_depth = dfs(child, depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
            
            return max_child_depth
        
        for dataset in dependencies:
            depth = dfs(dataset, 0)
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _calculate_relationship_complexity(self, execution_config: ExecutionConfig) -> float:
        """Calculate complexity score based on relationship patterns"""
        if not execution_config.fk_relationships:
            return 0.0
        
        complexity_score = 0.0
        
        # Count different relationship types
        relationship_types = {}
        for fk in execution_config.fk_relationships:
            rel_type = fk.relationship_type
            if rel_type not in relationship_types:
                relationship_types[rel_type] = 0
            relationship_types[rel_type] += 1
        
        # Add complexity based on relationship diversity
        complexity_score += len(relationship_types) * 0.1
        
        # Add complexity based on multi-value relationships
        multi_value_count = sum(1 for fk in execution_config.fk_relationships if fk.is_multi_value)
        complexity_score += multi_value_count * 0.15
        
        # Add complexity based on total relationship count
        total_relationships = len(execution_config.fk_relationships)
        if total_relationships > self.complexity_thresholds['high_relationship_count']:
            complexity_score += 0.3
        elif total_relationships > 5:
            complexity_score += 0.2
        
        return min(complexity_score, 1.0)
    
    def _calculate_transformation_complexity(self, columns: List[ColumnConfig]) -> float:
        """Calculate complexity score based on data transformation requirements"""
        complexity_score = 0.0
        
        # External ontology complexity
        external_ontology_count = sum(1 for col in columns if col.is_external_ontology)
        complexity_score += external_ontology_count * 0.2
        
        # Multi-value complexity
        multi_value_count = sum(1 for col in columns if col.is_multi_value)
        complexity_score += multi_value_count * 0.15
        
        # Anchor column complexity
        anchor_count = sum(1 for col in columns if col.is_anchor)
        complexity_score += anchor_count * 0.1
        
        # Datatype diversity
        datatypes = set(col.datatype for col in columns)
        if len(datatypes) > 5:
            complexity_score += 0.2
        elif len(datatypes) > 3:
            complexity_score += 0.1
        
        return min(complexity_score, 1.0)
    
    def _calculate_integration_complexity(self, execution_config: ExecutionConfig) -> float:
        """Calculate complexity score based on integration requirements"""
        complexity_score = 0.0
        
        # Dataset count complexity
        dataset_count = len(execution_config.datasets)
        if dataset_count > self.complexity_thresholds['high_dataset_count']:
            complexity_score += 0.3
        elif dataset_count > 5:
            complexity_score += 0.2
        
        # Column count complexity
        total_columns = sum(len(ds.columns) for ds in execution_config.datasets)
        if total_columns > self.complexity_thresholds['high_column_count']:
            complexity_score += 0.2
        elif total_columns > 25:
            complexity_score += 0.1
        
        # Cross-dataset relationships
        cross_dataset_relationships = len(execution_config.fk_relationships)
        if cross_dataset_relationships > 0:
            complexity_score += min(cross_dataset_relationships * 0.05, 0.3)
        
        return min(complexity_score, 1.0)
    
    def _determine_complexity_level(self, metrics: MappingComplexityMetrics) -> ComplexityLevel:
        """Determine overall complexity level based on metrics"""
        
        # Calculate weighted complexity score
        weighted_score = (
            metrics.relationship_complexity_score * 0.4 +
            metrics.data_transformation_complexity * 0.3 +
            metrics.integration_complexity * 0.3
        )
        
        # Additional factors
        if metrics.total_datasets > 10 or metrics.total_relationships > 20:
            weighted_score += 0.2
        
        if metrics.external_ontology_count > 5 or metrics.dependency_depth > 5:
            weighted_score += 0.15
        
        # Determine level
        if weighted_score >= 0.8:
            return ComplexityLevel.EXTREME
        elif weighted_score >= 0.6:
            return ComplexityLevel.HIGH
        elif weighted_score >= 0.3:
            return ComplexityLevel.MEDIUM
        else:
            return ComplexityLevel.LOW
    
    def _estimate_base_memory_usage(self, 
                                   mapping_config: ExecutionConfig,
                                   file_info: Optional[FileInfo] = None) -> float:
        """Estimate base memory usage in MB"""
        
        if file_info:
            # Use file information for better estimation
            base_memory = file_info.file_size_mb * 2  # Basic multiplier for processing
        else:
            # Estimate based on mapping configuration
            total_columns = sum(len(ds.columns) for ds in mapping_config.datasets)
            estimated_rows = 50000  # Default assumption
            base_memory = (total_columns * estimated_rows * 50) / (1024 * 1024)  # 50 bytes per cell
        
        # Add overhead for relationships
        relationship_overhead = len(mapping_config.fk_relationships) * 10  # 10MB per relationship
        
        # Add overhead for external ontologies
        external_ontology_overhead = sum(
            sum(1 for col in ds.columns if col.is_external_ontology) * 5
            for ds in mapping_config.datasets
        )
        
        return base_memory + relationship_overhead + external_ontology_overhead
    
    def _estimate_execution_time(self, 
                                strategy: ExecutionStrategy,
                                mapping_config: ExecutionConfig,
                                file_info: Optional[FileInfo] = None,
                                strategy_config: Dict[str, Any] = None) -> float:
        """Estimate execution time in minutes"""
        
        if file_info:
            base_rows = file_info.estimated_rows
        else:
            base_rows = 50000  # Default assumption
        
        # Base processing rate (rows per minute)
        base_rate_map = {
            ExecutionStrategy.ENTITY_CENTRIC: 10000,
            ExecutionStrategy.MAPPING_DRIVEN: 8000,
            ExecutionStrategy.STREAMING: 6000,
            ExecutionStrategy.MULTI_PHASE: 4000,
            ExecutionStrategy.HYBRID: 7000
        }
        
        base_rate = base_rate_map.get(strategy, 5000)
        
        # Adjust for complexity
        complexity_multiplier = 1.0
        if len(mapping_config.fk_relationships) > 10:
            complexity_multiplier *= 1.5
        if sum(len(ds.columns) for ds in mapping_config.datasets) > 50:
            complexity_multiplier *= 1.3
        
        # Apply CPU efficiency
        cpu_efficiency = strategy_config.get('cpu_efficiency', 0.8) if strategy_config else 0.8
        effective_rate = base_rate * cpu_efficiency
        
        return (base_rows / effective_rate) * complexity_multiplier
    
    def _estimate_disk_space_usage(self, 
                                  mapping_config: ExecutionConfig,
                                  file_info: Optional[FileInfo] = None) -> float:
        """Estimate disk space usage in MB"""
        
        if file_info:
            base_size = file_info.file_size_mb
        else:
            # Estimate based on configuration
            total_columns = sum(len(ds.columns) for ds in mapping_config.datasets)
            estimated_rows = 50000
            base_size = (total_columns * estimated_rows * 50) / (1024 * 1024)
        
        # Add overhead for temporary files and indexes
        temp_file_overhead = base_size * 0.5
        index_overhead = len(mapping_config.fk_relationships) * 5  # 5MB per relationship index
        
        return base_size + temp_file_overhead + index_overhead
    
    def _calculate_concurrent_capability(self, 
                                       strategy: ExecutionStrategy,
                                       mapping_config: ExecutionConfig,
                                       estimated_memory_mb: float) -> int:
        """Calculate concurrent processing capability"""
        
        # Memory-based limit
        memory_limit = self.complexity_thresholds['memory_limit_mb']
        memory_based_limit = max(1, int(memory_limit / estimated_memory_mb))
        
        # Strategy-based limit
        strategy_limits = {
            ExecutionStrategy.ENTITY_CENTRIC: 2,
            ExecutionStrategy.MAPPING_DRIVEN: 4,
            ExecutionStrategy.STREAMING: 8,
            ExecutionStrategy.MULTI_PHASE: 6,
            ExecutionStrategy.HYBRID: 4
        }
        
        strategy_limit = strategy_limits.get(strategy, 2)
        
        # Dataset-based limit (avoid excessive parallelism with few datasets)
        dataset_limit = max(1, len(mapping_config.datasets))
        
        return min(memory_based_limit, strategy_limit, dataset_limit)
    
    def _calculate_scalability_factor(self, 
                                    strategy: ExecutionStrategy,
                                    mapping_config: ExecutionConfig) -> float:
        """Calculate scalability factor for the strategy"""
        
        base_factors = {
            ExecutionStrategy.ENTITY_CENTRIC: 0.6,
            ExecutionStrategy.MAPPING_DRIVEN: 0.8,
            ExecutionStrategy.STREAMING: 0.9,
            ExecutionStrategy.MULTI_PHASE: 0.95,
            ExecutionStrategy.HYBRID: 0.85
        }
        
        base_factor = base_factors.get(strategy, 0.7)
        
        # Adjust based on complexity
        relationship_count = len(mapping_config.fk_relationships)
        if relationship_count > 20:
            base_factor *= 0.9
        elif relationship_count > 10:
            base_factor *= 0.95
        
        return base_factor
    
    def _calculate_confidence_score(self, 
                                  strategy: ExecutionStrategy,
                                  complexity_metrics: MappingComplexityMetrics,
                                  resource_estimation: ResourceEstimation,
                                  file_info: Optional[FileInfo] = None) -> float:
        """Calculate confidence score for a strategy recommendation"""
        
        confidence = 0.5  # Base confidence
        
        # Get strategy configuration
        strategy_config = self.strategy_configs.get(strategy, {})
        optimal_complexity = strategy_config.get('optimal_complexity', ComplexityLevel.MEDIUM)
        
        # Complexity match bonus
        if complexity_metrics.overall_complexity == optimal_complexity:
            confidence += 0.3
        elif abs(list(ComplexityLevel).index(complexity_metrics.overall_complexity) - 
                list(ComplexityLevel).index(optimal_complexity)) == 1:
            confidence += 0.1
        else:
            confidence -= 0.2
        
        # Resource feasibility check
        if resource_estimation.estimated_memory_mb > self.complexity_thresholds['memory_limit_mb']:
            confidence -= 0.3
        
        # File size compatibility
        if file_info:
            max_file_mb = strategy_config.get('max_recommended_file_mb', 1000)
            if file_info.file_size_mb <= max_file_mb:
                confidence += 0.2
            else:
                confidence -= 0.1
        
        # Relationship complexity compatibility
        max_relationships = strategy_config.get('max_recommended_relationships', 25)
        if complexity_metrics.total_relationships <= max_relationships:
            confidence += 0.1
        else:
            confidence -= 0.15
        
        # Performance considerations
        if resource_estimation.estimated_execution_time_minutes < 30:
            confidence += 0.1
        elif resource_estimation.estimated_execution_time_minutes > 120:
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _analyze_strategy_characteristics(self, 
                                        strategy: ExecutionStrategy,
                                        complexity_metrics: MappingComplexityMetrics,
                                        resource_estimation: ResourceEstimation,
                                        file_info: Optional[FileInfo] = None) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
        """Analyze characteristics of a specific strategy"""
        
        advantages = []
        disadvantages = []
        requirements = []
        risk_factors = []
        performance_notes = []
        
        if strategy == ExecutionStrategy.ENTITY_CENTRIC:
            advantages.extend([
                "Complete entity creation in single pass",
                "Excellent for complex relationship handling",
                "Best debugging and error tracking capabilities",
                "Optimal for small to medium datasets"
            ])
            disadvantages.extend([
                "High memory usage for large datasets",
                "May exceed memory limits with complex mappings",
                "Not suitable for streaming scenarios"
            ])
            requirements.extend([
                f"Minimum {resource_estimation.estimated_memory_mb:.0f}MB RAM",
                "Complete dataset must fit in memory",
                "Stable network connection for external ontologies"
            ])
            if resource_estimation.estimated_memory_mb > 4000:
                risk_factors.append("High memory usage may cause system instability")
            if complexity_metrics.total_relationships > 20:
                risk_factors.append("Complex relationships may slow processing significantly")
        
        elif strategy == ExecutionStrategy.MAPPING_DRIVEN:
            advantages.extend([
                "Balanced memory usage and performance",
                "Good handling of moderate complexity",
                "Flexible adaptation to different data patterns",
                "Reasonable execution time for most datasets"
            ])
            disadvantages.extend([
                "May not be optimal for very simple or very complex scenarios",
                "Requires careful tuning for best performance",
                "Intermediate complexity in implementation"
            ])
            requirements.extend([
                f"Recommended {resource_estimation.estimated_memory_mb:.0f}MB RAM",
                "Moderate CPU resources",
                "Good I/O performance for temporary files"
            ])
            if complexity_metrics.overall_complexity == ComplexityLevel.EXTREME:
                risk_factors.append("May struggle with extremely complex mappings")
        
        elif strategy == ExecutionStrategy.STREAMING:
            advantages.extend([
                "Excellent memory efficiency",
                "Handles very large datasets well",
                "Good scalability characteristics",
                "Minimal memory footprint"
            ])
            disadvantages.extend([
                "Longer execution time due to streaming overhead",
                "Limited ability to handle complex cross-references",
                "May require multiple passes for complex relationships"
            ])
            requirements.extend([
                f"Minimum {resource_estimation.estimated_memory_mb:.0f}MB RAM",
                "Fast I/O subsystem",
                "Reliable storage for temporary streaming data"
            ])
            if complexity_metrics.total_relationships > 30:
                risk_factors.append("Many relationships may require multiple streaming passes")
        
        elif strategy == ExecutionStrategy.MULTI_PHASE:
            advantages.extend([
                "Most memory efficient approach",
                "Handles extremely large datasets",
                "Robust error recovery capabilities",
                "Excellent scalability"
            ])
            disadvantages.extend([
                "Longest execution time",
                "Most complex orchestration",
                "Requires careful phase planning",
                "Entity fragmentation across phases"
            ])
            requirements.extend([
                f"Minimum {resource_estimation.estimated_memory_mb:.0f}MB RAM",
                "High-performance storage system",
                "Robust error handling infrastructure"
            ])
            if complexity_metrics.dependency_depth > 5:
                risk_factors.append("Deep dependencies may require many phases")
        
        elif strategy == ExecutionStrategy.HYBRID:
            advantages.extend([
                "Combines benefits of multiple approaches",
                "Adaptive to different data characteristics",
                "Good performance across various scenarios",
                "Flexible resource utilization"
            ])
            disadvantages.extend([
                "More complex implementation",
                "May not be optimal for any single scenario",
                "Requires sophisticated coordination"
            ])
            requirements.extend([
                f"Recommended {resource_estimation.estimated_memory_mb:.0f}MB RAM",
                "Balanced CPU and I/O resources",
                "Advanced orchestration capabilities"
            ])
            risk_factors.append("Complex coordination may introduce edge cases")
        
        # Add performance notes
        performance_notes.append(f"Estimated execution time: {resource_estimation.estimated_execution_time_minutes:.1f} minutes")
        performance_notes.append(f"Peak memory usage: {resource_estimation.peak_memory_mb:.0f}MB")
        performance_notes.append(f"Concurrent processing capability: {resource_estimation.concurrent_processing_capability}")
        
        return advantages, disadvantages, requirements, risk_factors, performance_notes
    
    def _generate_strategy_reasoning(self, 
                                   recommendation: StrategyRecommendation,
                                   complexity_metrics: MappingComplexityMetrics,
                                   file_info: Optional[FileInfo] = None) -> str:
        """Generate detailed reasoning for strategy recommendation"""
        
        reasoning_parts = []
        
        # Complexity analysis
        reasoning_parts.append(f"Mapping complexity analysis: {complexity_metrics.overall_complexity.value} complexity")
        reasoning_parts.append(f"- {complexity_metrics.total_datasets} datasets with {complexity_metrics.total_columns} total columns")
        reasoning_parts.append(f"- {complexity_metrics.total_relationships} relationships, {complexity_metrics.external_ontology_count} external ontologies")
        
        # File characteristics
        if file_info:
            reasoning_parts.append(f"File characteristics: {file_info.file_size_mb:.1f}MB, ~{file_info.estimated_rows} rows")
        
        # Resource analysis
        reasoning_parts.append(f"Resource requirements: {recommendation.resource_estimation.estimated_memory_mb:.0f}MB memory, "
                             f"{recommendation.resource_estimation.estimated_execution_time_minutes:.1f} minutes execution time")
        
        # Strategy-specific reasoning
        strategy_config = self.strategy_configs.get(recommendation.strategy, {})
        optimal_complexity = strategy_config.get('optimal_complexity', ComplexityLevel.MEDIUM)
        
        if complexity_metrics.overall_complexity == optimal_complexity:
            reasoning_parts.append(f"Strategy {recommendation.strategy.value} is optimal for {optimal_complexity.value} complexity scenarios")
        else:
            reasoning_parts.append(f"Strategy {recommendation.strategy.value} selected despite complexity mismatch due to resource constraints")
        
        # Confidence justification
        if recommendation.confidence_score >= 0.8:
            reasoning_parts.append("High confidence due to excellent compatibility with data characteristics")
        elif recommendation.confidence_score >= 0.6:
            reasoning_parts.append("Good confidence with some minor compatibility concerns")
        else:
            reasoning_parts.append("Moderate confidence - consider alternative strategies for better optimization")
        
        return ". ".join(reasoning_parts) + "."