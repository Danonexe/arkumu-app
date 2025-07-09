"""
Task Integration for Execution Strategy Service

This module provides integration with the import_metadata.py task and other
Huey tasks for automatic execution strategy selection and enhanced import processing.
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

from .execution_strategy_recommender import (
    ExecutionStrategyRecommender,
    ExecutionStrategy,
    FileInfo,
    StrategyRecommendation
)
from .integration_helpers import ExecutionStrategyIntegrator
from ..mapping_consumer.config_translator import ExecutionConfig
from ..mapping_consumer.mapping_adapter import MappingAdapter
from ..orchestrator.strategy_selector import StrategySelector, ProcessingStrategy

logger = logging.getLogger(__name__)


class TaskExecutionStrategyService:
    """
    Service for integrating execution strategy recommendations with Huey tasks.
    Provides automatic strategy selection and enhanced import processing capabilities.
    """
    
    def __init__(self):
        self.recommender = ExecutionStrategyRecommender()
        self.integrator = ExecutionStrategyIntegrator()
        self.mapping_adapter = MappingAdapter()
        self.legacy_strategy_selector = StrategySelector()
    
    def select_optimal_strategy_for_import(self, 
                                         mapping_id: Optional[int] = None,
                                         execution_config: Optional[ExecutionConfig] = None,
                                         file_info: Optional[Dict[str, Any]] = None,
                                         csv_sources: Optional[Dict[str, Any]] = None,
                                         execution_strategy: str = "auto") -> Dict[str, Any]:
        """
        Select optimal execution strategy for an import task.
        
        Args:
            mapping_id: Optional mapping ID to analyze
            execution_config: Optional pre-loaded execution configuration
            file_info: Optional file information dictionary
            csv_sources: Optional CSV data sources (for legacy compatibility)
            execution_strategy: Strategy selection mode ("auto", "legacy", or specific strategy)
            
        Returns:
            Dictionary with selected strategy and analysis
        """
        try:
            # Handle legacy "auto" strategy selection
            if execution_strategy == "auto" and execution_config and csv_sources:
                return self._handle_legacy_auto_strategy(execution_config, csv_sources)
            
            # Handle specific strategy selection
            if execution_strategy != "auto":
                return self._handle_specific_strategy(execution_strategy, mapping_id, execution_config, file_info)
            
            # Handle advanced strategy recommendation
            if mapping_id or execution_config:
                return self._handle_advanced_strategy_recommendation(mapping_id, execution_config, file_info)
            
            # Fallback to default strategy
            return self._handle_default_strategy()
            
        except Exception as e:
            logger.error(f"Failed to select optimal strategy: {e}")
            return {
                'strategy': 'entity_centric',
                'source': 'fallback',
                'error': str(e),
                'confidence_score': 0.1,
                'reasoning': 'Fallback to entity-centric due to strategy selection error'
            }
    
    def prepare_execution_context(self, 
                                strategy_result: Dict[str, Any],
                                mapping_id: Optional[int] = None,
                                file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Prepare execution context with strategy-specific optimizations.
        
        Args:
            strategy_result: Result from strategy selection
            mapping_id: Optional mapping ID
            file_info: Optional file information
            
        Returns:
            Dictionary with execution context and optimizations
        """
        try:
            execution_context = {
                'strategy': strategy_result['strategy'],
                'confidence_score': strategy_result.get('confidence_score', 0.5),
                'optimizations': {},
                'resource_hints': {},
                'monitoring_config': {}
            }
            
            # Add strategy-specific optimizations
            strategy = strategy_result['strategy']
            
            if strategy == 'entity_centric':
                execution_context['optimizations'].update({
                    'batch_size': 1000,
                    'memory_buffer_size': '2GB',
                    'enable_relationship_caching': True,
                    'use_bulk_operations': True
                })
            elif strategy == 'mapping_driven':
                execution_context['optimizations'].update({
                    'batch_size': 2000,
                    'memory_buffer_size': '1GB',
                    'enable_streaming': True,
                    'chunk_processing': True
                })
            elif strategy == 'streaming':
                execution_context['optimizations'].update({
                    'batch_size': 5000,
                    'memory_buffer_size': '500MB',
                    'enable_streaming': True,
                    'streaming_chunk_size': 10000,
                    'temporary_storage': True
                })
            elif strategy == 'multi_phase':
                execution_context['optimizations'].update({
                    'batch_size': 10000,
                    'memory_buffer_size': '256MB',
                    'enable_phase_coordination': True,
                    'phase_checkpoint_interval': 50000,
                    'phase_recovery_enabled': True
                })
            elif strategy == 'hybrid':
                execution_context['optimizations'].update({
                    'batch_size': 3000,
                    'memory_buffer_size': '1.5GB',
                    'adaptive_processing': True,
                    'enable_smart_switching': True,
                    'performance_monitoring': True
                })
            
            # Add resource hints from recommendation
            if 'resource_estimation' in strategy_result:
                resource_est = strategy_result['resource_estimation']
                execution_context['resource_hints'].update({
                    'estimated_memory_mb': resource_est.get('estimated_memory_mb', 0),
                    'estimated_cpu_cores': resource_est.get('estimated_cpu_cores', 1),
                    'estimated_execution_time_minutes': resource_est.get('estimated_execution_time_minutes', 0),
                    'peak_memory_mb': resource_est.get('peak_memory_mb', 0),
                    'concurrent_capability': resource_est.get('concurrent_processing_capability', 1)
                })
            
            # Add monitoring configuration
            execution_context['monitoring_config'].update({
                'track_memory_usage': True,
                'track_execution_time': True,
                'track_error_rate': True,
                'checkpoint_interval': 10000,
                'progress_reporting_interval': 5000
            })
            
            # Add file-specific optimizations
            if file_info:
                if file_info.get('file_size_mb', 0) > 1000:
                    execution_context['optimizations']['large_file_mode'] = True
                    execution_context['optimizations']['streaming_required'] = True
                
                if file_info.get('estimated_rows', 0) > 1000000:
                    execution_context['optimizations']['high_volume_mode'] = True
                    execution_context['optimizations']['batch_size'] = min(
                        execution_context['optimizations'].get('batch_size', 1000), 2000
                    )
            
            return execution_context
            
        except Exception as e:
            logger.error(f"Failed to prepare execution context: {e}")
            return {
                'strategy': strategy_result.get('strategy', 'entity_centric'),
                'confidence_score': 0.1,
                'optimizations': {'batch_size': 1000},
                'resource_hints': {},
                'monitoring_config': {'track_memory_usage': True},
                'error': str(e)
            }
    
    def create_enhanced_import_metadata(self, 
                                      strategy_result: Dict[str, Any],
                                      execution_context: Dict[str, Any],
                                      mapping_id: Optional[int] = None,
                                      task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create enhanced import metadata with strategy information.
        
        Args:
            strategy_result: Result from strategy selection
            execution_context: Execution context from preparation
            mapping_id: Optional mapping ID
            task_id: Optional task ID for tracking
            
        Returns:
            Dictionary with enhanced import metadata
        """
        try:
            metadata = {
                'strategy_analysis': {
                    'selected_strategy': strategy_result['strategy'],
                    'confidence_score': strategy_result.get('confidence_score', 0.5),
                    'selection_source': strategy_result.get('source', 'unknown'),
                    'reasoning': strategy_result.get('reasoning', ''),
                    'alternative_strategies': strategy_result.get('alternative_strategies', [])
                },
                'execution_context': execution_context,
                'performance_predictions': {
                    'estimated_memory_mb': execution_context.get('resource_hints', {}).get('estimated_memory_mb', 0),
                    'estimated_time_minutes': execution_context.get('resource_hints', {}).get('estimated_execution_time_minutes', 0),
                    'expected_peak_memory_mb': execution_context.get('resource_hints', {}).get('peak_memory_mb', 0),
                    'concurrent_processing_capability': execution_context.get('resource_hints', {}).get('concurrent_capability', 1)
                },
                'monitoring_setup': execution_context.get('monitoring_config', {}),
                'optimization_flags': execution_context.get('optimizations', {}),
                'task_metadata': {
                    'task_id': task_id,
                    'mapping_id': mapping_id,
                    'strategy_service_version': '1.0.0',
                    'timestamp': None  # Could add current timestamp if needed
                }
            }
            
            # Add complexity analysis if available
            if 'complexity_metrics' in strategy_result:
                metadata['complexity_analysis'] = strategy_result['complexity_metrics']
            
            # Add risk assessment
            if 'risk_factors' in strategy_result:
                metadata['risk_assessment'] = {
                    'risk_factors': strategy_result['risk_factors'],
                    'mitigation_strategies': self._generate_risk_mitigation_strategies(strategy_result['risk_factors'])
                }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to create enhanced import metadata: {e}")
            return {
                'strategy_analysis': {
                    'selected_strategy': strategy_result.get('strategy', 'entity_centric'),
                    'confidence_score': 0.1,
                    'selection_source': 'fallback',
                    'reasoning': f'Fallback due to metadata creation error: {e}'
                },
                'error': str(e)
            }
    
    def _handle_legacy_auto_strategy(self, 
                                   execution_config: ExecutionConfig,
                                   csv_sources: Dict[str, Any]) -> Dict[str, Any]:
        """Handle legacy automatic strategy selection using existing StrategySelector"""
        try:
            # Use existing strategy selector for backward compatibility
            selected_strategy = self.legacy_strategy_selector.choose_optimal_strategy(
                execution_config, csv_sources
            )
            
            # Get detailed analysis
            analysis = self.legacy_strategy_selector.analyze_all_strategies(
                execution_config, csv_sources
            )
            
            # Get rationale
            rationale = self.legacy_strategy_selector.get_strategy_rationale(
                execution_config, csv_sources, selected_strategy
            )
            
            return {
                'strategy': selected_strategy.value,
                'source': 'legacy_auto',
                'confidence_score': 0.8,  # Legacy selector is trusted
                'reasoning': rationale,
                'detailed_analysis': analysis,
                'alternative_strategies': [
                    s['strategy'] for s in analysis.get('strategy_analyses', [])
                    if s['strategy'] != selected_strategy.value
                ][:2]  # Top 2 alternatives
            }
            
        except Exception as e:
            logger.error(f"Legacy auto strategy selection failed: {e}")
            return {
                'strategy': 'entity_centric',
                'source': 'fallback',
                'confidence_score': 0.1,
                'reasoning': f'Fallback due to legacy strategy selection error: {e}'
            }
    
    def _handle_specific_strategy(self, 
                                execution_strategy: str,
                                mapping_id: Optional[int] = None,
                                execution_config: Optional[ExecutionConfig] = None,
                                file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle specific strategy selection"""
        try:
            # Validate strategy
            valid_strategies = [s.value for s in ExecutionStrategy]
            if execution_strategy not in valid_strategies:
                raise ValueError(f"Invalid strategy: {execution_strategy}")
            
            # If we have mapping information, validate the choice
            if mapping_id or execution_config:
                # Get recommendation to validate the specific choice
                if mapping_id:
                    recommendation_data = self.integrator.get_strategy_recommendation_for_mapping(
                        mapping_id, file_info
                    )
                    
                    if 'error' not in recommendation_data:
                        recommended_strategy = recommendation_data['strategy']
                        confidence = recommendation_data['confidence_score']
                        
                        # Check if the specific strategy is reasonable
                        if execution_strategy == recommended_strategy:
                            return {
                                'strategy': execution_strategy,
                                'source': 'specific_optimal',
                                'confidence_score': confidence,
                                'reasoning': f"User-specified strategy matches recommended strategy: {recommended_strategy}",
                                'resource_estimation': recommendation_data.get('resource_estimation', {})
                            }
                        else:
                            return {
                                'strategy': execution_strategy,
                                'source': 'specific_override',
                                'confidence_score': max(0.3, confidence - 0.3),
                                'reasoning': f"User-specified strategy {execution_strategy} overrides recommended {recommended_strategy}",
                                'recommended_alternative': recommended_strategy
                            }
            
            # Return specific strategy without validation
            return {
                'strategy': execution_strategy,
                'source': 'specific_user',
                'confidence_score': 0.5,
                'reasoning': f"User-specified strategy: {execution_strategy}"
            }
            
        except Exception as e:
            logger.error(f"Specific strategy handling failed: {e}")
            return {
                'strategy': execution_strategy,
                'source': 'specific_fallback',
                'confidence_score': 0.2,
                'reasoning': f"Using specified strategy despite validation error: {e}"
            }
    
    def _handle_advanced_strategy_recommendation(self, 
                                               mapping_id: Optional[int] = None,
                                               execution_config: Optional[ExecutionConfig] = None,
                                               file_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle advanced strategy recommendation"""
        try:
            if mapping_id:
                # Use mapping-based recommendation
                recommendation_data = self.integrator.get_strategy_recommendation_for_mapping(
                    mapping_id, file_info
                )
                
                if 'error' in recommendation_data:
                    raise ValueError(f"Mapping recommendation failed: {recommendation_data['error']}")
                
                return {
                    'strategy': recommendation_data['strategy'],
                    'source': 'advanced_mapping',
                    'confidence_score': recommendation_data['confidence_score'],
                    'reasoning': recommendation_data['reasoning'],
                    'complexity_metrics': recommendation_data['complexity_metrics'],
                    'resource_estimation': recommendation_data['resource_estimation'],
                    'alternative_strategies': recommendation_data.get('alternative_strategies', []),
                    'advantages': recommendation_data.get('advantages', []),
                    'disadvantages': recommendation_data.get('disadvantages', []),
                    'risk_factors': recommendation_data.get('risk_factors', [])
                }
            
            elif execution_config:
                # Use execution config-based recommendation
                file_info_obj = None
                if file_info:
                    file_info_obj = FileInfo(**file_info)
                
                recommendation = self.recommender.recommend_execution_strategy(
                    execution_config, file_info_obj
                )
                
                return {
                    'strategy': recommendation.strategy.value,
                    'source': 'advanced_config',
                    'confidence_score': recommendation.confidence_score,
                    'reasoning': recommendation.reasoning,
                    'complexity_metrics': recommendation.complexity_metrics,
                    'resource_estimation': recommendation.resource_estimation,
                    'alternative_strategies': recommendation.alternative_strategies,
                    'advantages': recommendation.advantages,
                    'disadvantages': recommendation.disadvantages,
                    'risk_factors': recommendation.risk_factors
                }
            
            else:
                raise ValueError("No mapping ID or execution config provided for advanced recommendation")
                
        except Exception as e:
            logger.error(f"Advanced strategy recommendation failed: {e}")
            return {
                'strategy': 'entity_centric',
                'source': 'fallback',
                'confidence_score': 0.1,
                'reasoning': f'Fallback due to advanced recommendation error: {e}'
            }
    
    def _handle_default_strategy(self) -> Dict[str, Any]:
        """Handle default strategy selection"""
        return {
            'strategy': 'entity_centric',
            'source': 'default',
            'confidence_score': 0.5,
            'reasoning': 'Default entity-centric strategy selected due to insufficient information'
        }
    
    def _generate_risk_mitigation_strategies(self, risk_factors: List[str]) -> List[str]:
        """Generate risk mitigation strategies based on identified risk factors"""
        mitigation_strategies = []
        
        for risk_factor in risk_factors:
            if 'memory' in risk_factor.lower():
                mitigation_strategies.append("Monitor memory usage and implement memory cleanup checkpoints")
                mitigation_strategies.append("Consider switching to streaming strategy if memory issues persist")
            
            if 'relationship' in risk_factor.lower() or 'complex' in risk_factor.lower():
                mitigation_strategies.append("Implement relationship processing checkpoints")
                mitigation_strategies.append("Consider breaking complex relationships into simpler phases")
            
            if 'performance' in risk_factor.lower() or 'slow' in risk_factor.lower():
                mitigation_strategies.append("Enable performance monitoring and profiling")
                mitigation_strategies.append("Consider parallel processing optimizations")
            
            if 'dependency' in risk_factor.lower():
                mitigation_strategies.append("Implement dependency resolution validation")
                mitigation_strategies.append("Consider multi-phase processing for complex dependencies")
        
        # Remove duplicates and return
        return list(set(mitigation_strategies))


def integrate_strategy_with_import_task(mapping_id: Optional[int] = None,
                                      execution_config: Optional[ExecutionConfig] = None,
                                      file_info: Optional[Dict[str, Any]] = None,
                                      csv_sources: Optional[Dict[str, Any]] = None,
                                      execution_strategy: str = "auto",
                                      task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Integration function for import tasks to get strategy recommendations.
    
    This function can be called directly from import_metadata.py or other tasks
    to get comprehensive strategy analysis and execution context.
    
    Args:
        mapping_id: Optional mapping ID to analyze
        execution_config: Optional pre-loaded execution configuration
        file_info: Optional file information dictionary
        csv_sources: Optional CSV data sources (for legacy compatibility)
        execution_strategy: Strategy selection mode
        task_id: Optional task ID for tracking
        
    Returns:
        Dictionary with complete strategy analysis and execution context
    """
    service = TaskExecutionStrategyService()
    
    # Select optimal strategy
    strategy_result = service.select_optimal_strategy_for_import(
        mapping_id=mapping_id,
        execution_config=execution_config,
        file_info=file_info,
        csv_sources=csv_sources,
        execution_strategy=execution_strategy
    )
    
    # Prepare execution context
    execution_context = service.prepare_execution_context(
        strategy_result=strategy_result,
        mapping_id=mapping_id,
        file_info=file_info
    )
    
    # Create enhanced metadata
    enhanced_metadata = service.create_enhanced_import_metadata(
        strategy_result=strategy_result,
        execution_context=execution_context,
        mapping_id=mapping_id,
        task_id=task_id
    )
    
    return {
        'strategy_result': strategy_result,
        'execution_context': execution_context,
        'enhanced_metadata': enhanced_metadata,
        'integration_status': 'success'
    }