"""
Orchestrator Package

This package handles the orchestration of mapping-driven CSV imports.
It coordinates between the mapping consumer and execution engine to
provide a unified interface for executing complex import workflows.

Key Components:
- ImportOrchestrator: Main orchestration logic
- StrategySelector: Intelligent processing strategy selection
- ProgressTracker: Progress tracking for multi-dataset imports
- ResultAggregator: Aggregates results across datasets
"""

from .import_orchestrator import ImportOrchestrator, ImportResult
from .strategy_selector import StrategySelector, ProcessingStrategy
from .progress_tracker import ProgressTracker, ProgressUpdate
from .result_aggregator import ResultAggregator, AggregatedResult

__all__ = [
    'ImportOrchestrator',
    'ImportResult', 
    'StrategySelector',
    'ProcessingStrategy',
    'ProgressTracker',
    'ProgressUpdate',
    'ResultAggregator',
    'AggregatedResult'
]