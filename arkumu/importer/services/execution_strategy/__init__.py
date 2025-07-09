"""
Execution Strategy Service

This module provides intelligent execution strategy recommendation services for the arkumu importer.
It analyzes mapping complexity, estimates performance impact, and recommends optimal execution strategies
based on data characteristics and system constraints.

Main Components:
- ExecutionStrategyRecommender: Core recommendation engine
- ExecutionStrategyIntegrator: Integration helpers for views and templates
- TaskExecutionStrategyService: Integration with Huey tasks and import workflows

Key Features:
- Automatic strategy selection based on mapping complexity analysis
- Performance estimation for different strategies
- Resource usage predictions
- Integration with existing execution engines
- Support for both simple and complex mapping scenarios
- Comprehensive reasoning for strategy decisions

Usage:
    from arkumu.importer.services.execution_strategy import (
        ExecutionStrategyRecommender,
        ExecutionStrategyIntegrator,
        integrate_strategy_with_import_task
    )
    
    # Basic strategy recommendation
    recommender = ExecutionStrategyRecommender()
    recommendation = recommender.recommend_execution_strategy(execution_config)
    
    # Integration with Django views
    integrator = ExecutionStrategyIntegrator()
    view_data = integrator.get_strategy_recommendation_for_mapping(mapping_id)
    
    # Integration with import tasks
    strategy_data = integrate_strategy_with_import_task(
        mapping_id=mapping_id,
        execution_strategy="auto"
    )
"""

from .execution_strategy_recommender import (
    ExecutionStrategyRecommender,
    ExecutionStrategy,
    ComplexityLevel,
    FileInfo,
    MappingComplexityMetrics,
    ResourceEstimation,
    StrategyRecommendation
)

from .integration_helpers import (
    ExecutionStrategyIntegrator,
    create_strategy_recommendation_view_response,
    create_strategy_comparison_view_response
)

from .task_integration import (
    TaskExecutionStrategyService,
    integrate_strategy_with_import_task
)

__all__ = [
    # Core recommender
    'ExecutionStrategyRecommender',
    'ExecutionStrategy',
    'ComplexityLevel',
    'FileInfo',
    'MappingComplexityMetrics',
    'ResourceEstimation',
    'StrategyRecommendation',
    
    # Integration helpers
    'ExecutionStrategyIntegrator',
    'create_strategy_recommendation_view_response',
    'create_strategy_comparison_view_response',
    
    # Task integration
    'TaskExecutionStrategyService',
    'integrate_strategy_with_import_task'
]

# Module version
__version__ = '1.0.0'

# Module metadata
__author__ = 'Arkumu Development Team'
__description__ = 'Intelligent execution strategy recommendation service for arkumu importer'