"""
Integration Helpers for Execution Strategy Service

This module provides integration helpers for the execution strategy service
to work with mapping analysis views, Django templates, and other components.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from django.http import JsonResponse
from django.template.loader import render_to_string

from .execution_strategy_recommender import (
    ExecutionStrategyRecommender, 
    StrategyRecommendation,
    FileInfo,
    ExecutionStrategy,
    ComplexityLevel,
    MappingComplexityMetrics,
    ResourceEstimation
)
from ..mapping_consumer.config_translator import ExecutionConfig
from ..mapping_consumer.mapping_adapter import MappingAdapter

logger = logging.getLogger(__name__)


class ExecutionStrategyIntegrator:
    """
    Integration helper class for execution strategy service.
    Provides methods to integrate strategy recommendations with Django views,
    templates, and other components.
    """
    
    def __init__(self):
        self.recommender = ExecutionStrategyRecommender()
        self.mapping_adapter = MappingAdapter()
    
    def get_strategy_recommendation_for_mapping(self, 
                                              mapping_id: int,
                                              file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get strategy recommendation for a specific mapping ID.
        
        Args:
            mapping_id: ID of the mapping to analyze
            file_info: Optional file information dictionary
            
        Returns:
            Dictionary containing strategy recommendation and metadata
        """
        try:
            # Load mapping configuration
            mapping_config = self.mapping_adapter.load_mapping_config(mapping_id)
            
            # Convert to ExecutionConfig
            execution_config = self.mapping_adapter.config_translator.translate_mapping_config(mapping_config)
            
            # Convert file info if provided
            file_info_obj = None
            if file_info:
                file_info_obj = FileInfo(
                    file_size_mb=file_info.get('file_size_mb', 0),
                    estimated_rows=file_info.get('estimated_rows', 0),
                    estimated_columns=file_info.get('estimated_columns', 0),
                    csv_complexity_score=file_info.get('csv_complexity_score', 0.0),
                    has_large_text_fields=file_info.get('has_large_text_fields', False),
                    has_numeric_fields=file_info.get('has_numeric_fields', False),
                    encoding=file_info.get('encoding', 'utf-8'),
                    delimiter=file_info.get('delimiter', ','),
                    header_rows=file_info.get('header_rows', 1)
                )
            
            # Get strategy recommendation
            recommendation = self.recommender.recommend_execution_strategy(
                execution_config, file_info_obj
            )
            
            return self._serialize_recommendation(recommendation, mapping_id)
            
        except Exception as e:
            logger.error(f"Failed to get strategy recommendation for mapping {mapping_id}: {e}")
            return {
                'error': str(e),
                'mapping_id': mapping_id,
                'status': 'error'
            }
    
    def analyze_mapping_complexity_for_view(self, mapping_id: int) -> Dict[str, Any]:
        """
        Analyze mapping complexity for view consumption.
        
        Args:
            mapping_id: ID of the mapping to analyze
            
        Returns:
            Dictionary with complexity analysis suitable for views
        """
        try:
            # Load mapping configuration
            mapping_config = self.mapping_adapter.load_mapping_config(mapping_id)
            execution_config = self.mapping_adapter.config_translator.translate_mapping_config(mapping_config)
            
            # Analyze complexity
            complexity_metrics = self.recommender.analyze_mapping_complexity(execution_config)
            
            return self._serialize_complexity_metrics(complexity_metrics, mapping_id)
            
        except Exception as e:
            logger.error(f"Failed to analyze mapping complexity for {mapping_id}: {e}")
            return {
                'error': str(e),
                'mapping_id': mapping_id,
                'status': 'error'
            }
    
    def get_all_strategy_analyses(self, 
                                 mapping_id: int,
                                 file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get analysis of all available strategies for a mapping.
        
        Args:
            mapping_id: ID of the mapping to analyze
            file_info: Optional file information dictionary
            
        Returns:
            Dictionary with all strategy analyses
        """
        try:
            # Load mapping configuration
            mapping_config = self.mapping_adapter.load_mapping_config(mapping_id)
            execution_config = self.mapping_adapter.config_translator.translate_mapping_config(mapping_config)
            
            # Convert file info if provided
            file_info_obj = None
            if file_info:
                file_info_obj = FileInfo(**file_info)
            
            # Get complexity metrics
            complexity_metrics = self.recommender.analyze_mapping_complexity(execution_config)
            
            # Analyze all strategies
            strategy_analyses = []
            for strategy in ExecutionStrategy:
                if strategy == ExecutionStrategy.AUTO:
                    continue
                
                # Get resource estimation
                resource_estimation = self.recommender.estimate_performance_impact(
                    strategy, execution_config, file_info_obj
                )
                
                # Create a basic recommendation for this strategy
                recommendation = StrategyRecommendation(
                    strategy=strategy,
                    confidence_score=self.recommender._calculate_confidence_score(
                        strategy, complexity_metrics, resource_estimation, file_info_obj
                    ),
                    complexity_metrics=complexity_metrics,
                    resource_estimation=resource_estimation
                )
                
                # Add strategy-specific analysis
                advantages, disadvantages, requirements, risk_factors, performance_notes = (
                    self.recommender._analyze_strategy_characteristics(
                        strategy, complexity_metrics, resource_estimation, file_info_obj
                    )
                )
                
                recommendation.advantages = advantages
                recommendation.disadvantages = disadvantages
                recommendation.requirements = requirements
                recommendation.risk_factors = risk_factors
                recommendation.performance_notes = performance_notes
                
                strategy_analyses.append(self._serialize_recommendation(recommendation, mapping_id))
            
            # Sort by confidence score
            strategy_analyses.sort(key=lambda x: x['confidence_score'], reverse=True)
            
            return {
                'mapping_id': mapping_id,
                'complexity_metrics': self._serialize_complexity_metrics(complexity_metrics, mapping_id),
                'strategy_analyses': strategy_analyses,
                'recommended_strategy': strategy_analyses[0]['strategy'] if strategy_analyses else None,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Failed to get all strategy analyses for {mapping_id}: {e}")
            return {
                'error': str(e),
                'mapping_id': mapping_id,
                'status': 'error'
            }
    
    def render_strategy_recommendation_template(self, 
                                              mapping_id: int,
                                              file_info: Optional[Dict[str, Any]] = None,
                                              template_name: str = 'execution_strategy/recommendation.html') -> str:
        """
        Render strategy recommendation as HTML template.
        
        Args:
            mapping_id: ID of the mapping to analyze
            file_info: Optional file information dictionary
            template_name: Template name to render
            
        Returns:
            Rendered HTML string
        """
        try:
            # Get strategy recommendation
            recommendation_data = self.get_strategy_recommendation_for_mapping(mapping_id, file_info)
            
            # Render template
            return render_to_string(template_name, {
                'recommendation': recommendation_data,
                'mapping_id': mapping_id,
                'file_info': file_info
            })
            
        except Exception as e:
            logger.error(f"Failed to render strategy recommendation template: {e}")
            return f"<div class='error'>Error rendering strategy recommendation: {e}</div>"
    
    def get_strategy_comparison_data(self, 
                                   mapping_id: int,
                                   file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get data for strategy comparison visualization.
        
        Args:
            mapping_id: ID of the mapping to analyze
            file_info: Optional file information dictionary
            
        Returns:
            Dictionary with comparison data suitable for charts/tables
        """
        try:
            all_analyses = self.get_all_strategy_analyses(mapping_id, file_info)
            
            if all_analyses.get('status') == 'error':
                return all_analyses
            
            # Prepare comparison data
            comparison_data = {
                'strategies': [],
                'metrics': {
                    'memory_usage': [],
                    'execution_time': [],
                    'confidence_score': [],
                    'cpu_cores': [],
                    'disk_space': []
                },
                'chart_data': {
                    'labels': [],
                    'datasets': []
                }
            }
            
            for analysis in all_analyses['strategy_analyses']:
                strategy_name = analysis['strategy']
                resource_est = analysis['resource_estimation']
                
                comparison_data['strategies'].append({
                    'name': strategy_name,
                    'display_name': strategy_name.replace('_', ' ').title(),
                    'confidence': analysis['confidence_score'],
                    'recommended': analysis.get('recommended', False)
                })
                
                comparison_data['metrics']['memory_usage'].append(resource_est['estimated_memory_mb'])
                comparison_data['metrics']['execution_time'].append(resource_est['estimated_execution_time_minutes'])
                comparison_data['metrics']['confidence_score'].append(analysis['confidence_score'])
                comparison_data['metrics']['cpu_cores'].append(resource_est['estimated_cpu_cores'])
                comparison_data['metrics']['disk_space'].append(resource_est['estimated_disk_space_mb'])
                
                comparison_data['chart_data']['labels'].append(
                    strategy_name.replace('_', ' ').title()
                )
            
            # Create chart datasets
            comparison_data['chart_data']['datasets'] = [
                {
                    'label': 'Memory Usage (MB)',
                    'data': comparison_data['metrics']['memory_usage'],
                    'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                    'borderColor': 'rgba(255, 99, 132, 1)',
                    'borderWidth': 1
                },
                {
                    'label': 'Execution Time (minutes)',
                    'data': comparison_data['metrics']['execution_time'],
                    'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                    'borderColor': 'rgba(54, 162, 235, 1)',
                    'borderWidth': 1
                },
                {
                    'label': 'Confidence Score',
                    'data': comparison_data['metrics']['confidence_score'],
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                    'borderColor': 'rgba(75, 192, 192, 1)',
                    'borderWidth': 1
                }
            ]
            
            return comparison_data
            
        except Exception as e:
            logger.error(f"Failed to get strategy comparison data: {e}")
            return {
                'error': str(e),
                'mapping_id': mapping_id,
                'status': 'error'
            }
    
    def _serialize_recommendation(self, recommendation: StrategyRecommendation, mapping_id: int) -> Dict[str, Any]:
        """Serialize a strategy recommendation for JSON response"""
        return {
            'mapping_id': mapping_id,
            'strategy': recommendation.strategy.value,
            'confidence_score': recommendation.confidence_score,
            'complexity_metrics': {
                'total_datasets': recommendation.complexity_metrics.total_datasets,
                'total_columns': recommendation.complexity_metrics.total_columns,
                'total_relationships': recommendation.complexity_metrics.total_relationships,
                'external_ontology_count': recommendation.complexity_metrics.external_ontology_count,
                'multi_value_column_count': recommendation.complexity_metrics.multi_value_column_count,
                'anchor_column_count': recommendation.complexity_metrics.anchor_column_count,
                'dependency_depth': recommendation.complexity_metrics.dependency_depth,
                'relationship_complexity_score': recommendation.complexity_metrics.relationship_complexity_score,
                'data_transformation_complexity': recommendation.complexity_metrics.data_transformation_complexity,
                'integration_complexity': recommendation.complexity_metrics.integration_complexity,
                'overall_complexity': recommendation.complexity_metrics.overall_complexity.value
            },
            'resource_estimation': {
                'estimated_memory_mb': recommendation.resource_estimation.estimated_memory_mb,
                'estimated_cpu_cores': recommendation.resource_estimation.estimated_cpu_cores,
                'estimated_execution_time_minutes': recommendation.resource_estimation.estimated_execution_time_minutes,
                'estimated_disk_space_mb': recommendation.resource_estimation.estimated_disk_space_mb,
                'peak_memory_mb': recommendation.resource_estimation.peak_memory_mb,
                'concurrent_processing_capability': recommendation.resource_estimation.concurrent_processing_capability,
                'scalability_factor': recommendation.resource_estimation.scalability_factor
            },
            'advantages': recommendation.advantages,
            'disadvantages': recommendation.disadvantages,
            'requirements': recommendation.requirements,
            'risk_factors': recommendation.risk_factors,
            'performance_notes': recommendation.performance_notes,
            'reasoning': recommendation.reasoning,
            'alternative_strategies': recommendation.alternative_strategies,
            'timestamp': None  # Could add timestamp if needed
        }
    
    def _serialize_complexity_metrics(self, metrics: MappingComplexityMetrics, mapping_id: int) -> Dict[str, Any]:
        """Serialize complexity metrics for JSON response"""
        return {
            'mapping_id': mapping_id,
            'total_datasets': metrics.total_datasets,
            'total_columns': metrics.total_columns,
            'total_relationships': metrics.total_relationships,
            'external_ontology_count': metrics.external_ontology_count,
            'multi_value_column_count': metrics.multi_value_column_count,
            'anchor_column_count': metrics.anchor_column_count,
            'dependency_depth': metrics.dependency_depth,
            'relationship_complexity_score': metrics.relationship_complexity_score,
            'data_transformation_complexity': metrics.data_transformation_complexity,
            'integration_complexity': metrics.integration_complexity,
            'overall_complexity': metrics.overall_complexity.value,
            'complexity_summary': self._generate_complexity_summary(metrics)
        }
    
    def _generate_complexity_summary(self, metrics: MappingComplexityMetrics) -> Dict[str, Any]:
        """Generate a human-readable complexity summary"""
        summary = {
            'level': metrics.overall_complexity.value,
            'description': '',
            'key_factors': [],
            'recommendations': []
        }
        
        # Generate description based on complexity level
        if metrics.overall_complexity == ComplexityLevel.LOW:
            summary['description'] = "Simple mapping with basic data transformation requirements"
            summary['recommendations'].append("Consider entity-centric strategy for optimal performance")
        elif metrics.overall_complexity == ComplexityLevel.MEDIUM:
            summary['description'] = "Moderate mapping complexity with some advanced features"
            summary['recommendations'].append("Mapping-driven strategy recommended for balanced performance")
        elif metrics.overall_complexity == ComplexityLevel.HIGH:
            summary['description'] = "Complex mapping with significant relationship and transformation requirements"
            summary['recommendations'].append("Streaming or hybrid strategy recommended for scalability")
        else:  # EXTREME
            summary['description'] = "Highly complex mapping requiring advanced processing capabilities"
            summary['recommendations'].append("Multi-phase strategy recommended for reliability")
        
        # Add key factors
        if metrics.total_relationships > 10:
            summary['key_factors'].append(f"High relationship count ({metrics.total_relationships})")
        
        if metrics.external_ontology_count > 0:
            summary['key_factors'].append(f"External ontology integration ({metrics.external_ontology_count})")
        
        if metrics.multi_value_column_count > 0:
            summary['key_factors'].append(f"Multi-value columns ({metrics.multi_value_column_count})")
        
        if metrics.dependency_depth > 3:
            summary['key_factors'].append(f"Deep dependency chains ({metrics.dependency_depth} levels)")
        
        if metrics.total_datasets > 5:
            summary['key_factors'].append(f"Multiple datasets ({metrics.total_datasets})")
        
        return summary


def create_strategy_recommendation_view_response(mapping_id: int, 
                                               file_info: Optional[Dict[str, Any]] = None) -> JsonResponse:
    """
    Create a JSON response for strategy recommendation view.
    
    Args:
        mapping_id: ID of the mapping to analyze
        file_info: Optional file information dictionary
        
    Returns:
        JsonResponse with strategy recommendation data
    """
    integrator = ExecutionStrategyIntegrator()
    
    try:
        recommendation_data = integrator.get_strategy_recommendation_for_mapping(mapping_id, file_info)
        
        if 'error' in recommendation_data:
            return JsonResponse({
                'success': False,
                'error': recommendation_data['error'],
                'mapping_id': mapping_id
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': recommendation_data
        })
        
    except Exception as e:
        logger.error(f"Failed to create strategy recommendation view response: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'mapping_id': mapping_id
        }, status=500)


def create_strategy_comparison_view_response(mapping_id: int, 
                                           file_info: Optional[Dict[str, Any]] = None) -> JsonResponse:
    """
    Create a JSON response for strategy comparison view.
    
    Args:
        mapping_id: ID of the mapping to analyze
        file_info: Optional file information dictionary
        
    Returns:
        JsonResponse with strategy comparison data
    """
    integrator = ExecutionStrategyIntegrator()
    
    try:
        comparison_data = integrator.get_strategy_comparison_data(mapping_id, file_info)
        
        if 'error' in comparison_data:
            return JsonResponse({
                'success': False,
                'error': comparison_data['error'],
                'mapping_id': mapping_id
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': comparison_data
        })
        
    except Exception as e:
        logger.error(f"Failed to create strategy comparison view response: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'mapping_id': mapping_id
        }, status=500)