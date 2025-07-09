"""
Mapping Progress Estimator

This module provides progress estimation capabilities based on mapping complexity
and execution strategy. It helps provide more accurate progress tracking for
different types of imports.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Execution strategy enumeration."""
    MAPPING_DRIVEN = "mapping_driven"
    ENTITY_CENTRIC = "entity_centric"
    STANDARD = "standard"
    DIRECTORY = "directory"
    STRUCTURED = "structured"


@dataclass
class MappingComplexity:
    """Data class representing mapping complexity metrics."""
    dataset_count: int
    column_count: int
    relationship_count: int
    foreign_key_count: int
    transformation_count: int
    validation_rule_count: int
    
    @property
    def complexity_score(self) -> float:
        """Calculate overall complexity score."""
        # Base score from datasets and columns
        base_score = (self.dataset_count * 2) + (self.column_count * 0.5)
        
        # Relationship complexity
        relationship_score = self.relationship_count * 3
        
        # Foreign key complexity
        fk_score = self.foreign_key_count * 2
        
        # Transformation complexity
        transformation_score = self.transformation_count * 4
        
        # Validation complexity
        validation_score = self.validation_rule_count * 1.5
        
        return base_score + relationship_score + fk_score + transformation_score + validation_score


@dataclass
class PhaseEstimate:
    """Data class representing phase duration estimates."""
    phase_name: str
    estimated_duration_seconds: float
    complexity_factor: float
    base_duration: float
    
    @property
    def progress_weight(self) -> float:
        """Calculate progress weight for this phase."""
        return self.estimated_duration_seconds


class MappingProgressEstimator:
    """Estimates progress based on mapping complexity and execution strategy."""
    
    # Base duration estimates in seconds for each phase
    BASE_DURATIONS = {
        ExecutionStrategy.MAPPING_DRIVEN: {
            "initialization": 2.0,
            "file_download": 5.0,
            "mapping_validation": 8.0,
            "file_validation": 15.0,
            "strategy_selection": 1.0,
            "data_import": 30.0,
            "finalization": 3.0
        },
        ExecutionStrategy.ENTITY_CENTRIC: {
            "initialization": 2.0,
            "file_download": 5.0,
            "mapping_validation": 3.0,
            "file_validation": 5.0,
            "strategy_selection": 1.0,
            "data_import": 20.0,
            "finalization": 2.0
        },
        ExecutionStrategy.STANDARD: {
            "initialization": 1.0,
            "file_download": 5.0,
            "mapping_validation": 1.0,
            "file_validation": 2.0,
            "strategy_selection": 0.5,
            "data_import": 15.0,
            "finalization": 1.5
        },
        ExecutionStrategy.DIRECTORY: {
            "initialization": 2.0,
            "discovery": 10.0,
            "download": 20.0,
            "processing": 60.0,
            "finalization": 5.0
        },
        ExecutionStrategy.STRUCTURED: {
            "file_download": 5.0,
            "mapping_validation": 10.0,
            "data_import": 25.0,
            "finalization": 3.0
        }
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_mapping_complexity(self, mapping_config: Optional[Dict] = None) -> MappingComplexity:
        """Analyze mapping configuration to determine complexity metrics."""
        if not mapping_config:
            return MappingComplexity(
                dataset_count=1,
                column_count=5,
                relationship_count=0,
                foreign_key_count=0,
                transformation_count=0,
                validation_rule_count=0
            )
        
        # Extract complexity metrics from mapping config
        datasets = mapping_config.get("datasets", [])
        dataset_count = len(datasets)
        
        column_count = 0
        relationship_count = 0
        foreign_key_count = 0
        transformation_count = 0
        validation_rule_count = 0
        
        for dataset in datasets:
            columns = dataset.get("columns", [])
            column_count += len(columns)
            
            # Count relationships
            relationships = dataset.get("relationships", [])
            relationship_count += len(relationships)
            
            # Count foreign keys
            for column in columns:
                if column.get("foreign_key"):
                    foreign_key_count += 1
                
                # Count transformations
                transformations = column.get("transformations", [])
                transformation_count += len(transformations)
                
                # Count validation rules
                validations = column.get("validations", [])
                validation_rule_count += len(validations)
        
        return MappingComplexity(
            dataset_count=dataset_count,
            column_count=column_count,
            relationship_count=relationship_count,
            foreign_key_count=foreign_key_count,
            transformation_count=transformation_count,
            validation_rule_count=validation_rule_count
        )
    
    def estimate_phase_durations(self, 
                               strategy: ExecutionStrategy,
                               complexity: MappingComplexity,
                               file_size_bytes: Optional[int] = None) -> List[PhaseEstimate]:
        """Estimate duration for each phase based on strategy and complexity."""
        base_durations = self.BASE_DURATIONS.get(strategy, self.BASE_DURATIONS[ExecutionStrategy.STANDARD])
        
        phase_estimates = []
        
        for phase_name, base_duration in base_durations.items():
            # Calculate complexity factor
            complexity_factor = self._calculate_complexity_factor(phase_name, complexity)
            
            # Calculate file size factor
            file_size_factor = self._calculate_file_size_factor(phase_name, file_size_bytes)
            
            # Calculate estimated duration
            estimated_duration = base_duration * complexity_factor * file_size_factor
            
            phase_estimates.append(PhaseEstimate(
                phase_name=phase_name,
                estimated_duration_seconds=estimated_duration,
                complexity_factor=complexity_factor,
                base_duration=base_duration
            ))
        
        return phase_estimates
    
    def _calculate_complexity_factor(self, phase_name: str, complexity: MappingComplexity) -> float:
        """Calculate complexity factor for a specific phase."""
        base_factor = 1.0
        
        # Phase-specific complexity adjustments
        if phase_name == "mapping_validation":
            # Validation complexity increases with datasets and validation rules
            base_factor = 1.0 + (complexity.dataset_count * 0.1) + (complexity.validation_rule_count * 0.05)
        
        elif phase_name == "file_validation":
            # File validation complexity increases with columns and relationships
            base_factor = 1.0 + (complexity.column_count * 0.02) + (complexity.relationship_count * 0.1)
        
        elif phase_name == "data_import":
            # Data import complexity is the most significant
            dataset_factor = complexity.dataset_count * 0.15
            column_factor = complexity.column_count * 0.03
            relationship_factor = complexity.relationship_count * 0.2
            fk_factor = complexity.foreign_key_count * 0.1
            transformation_factor = complexity.transformation_count * 0.25
            
            base_factor = 1.0 + dataset_factor + column_factor + relationship_factor + fk_factor + transformation_factor
        
        elif phase_name == "finalization":
            # Finalization complexity increases with output complexity
            base_factor = 1.0 + (complexity.dataset_count * 0.05) + (complexity.relationship_count * 0.03)
        
        return max(base_factor, 1.0)  # Ensure factor is at least 1.0
    
    def _calculate_file_size_factor(self, phase_name: str, file_size_bytes: Optional[int]) -> float:
        """Calculate file size factor for a specific phase."""
        if not file_size_bytes:
            return 1.0
        
        # Convert to MB for easier calculation
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # File size primarily affects download and processing phases
        if phase_name in ["file_download", "data_import", "processing"]:
            if file_size_mb < 1:
                return 1.0
            elif file_size_mb < 10:
                return 1.0 + (file_size_mb * 0.1)
            elif file_size_mb < 100:
                return 1.5 + (file_size_mb * 0.05)
            else:
                return 2.0 + (file_size_mb * 0.02)
        
        return 1.0
    
    def calculate_progress_weights(self, phase_estimates: List[PhaseEstimate]) -> Dict[str, float]:
        """Calculate progress weights for each phase based on estimated durations."""
        total_duration = sum(estimate.estimated_duration_seconds for estimate in phase_estimates)
        
        if total_duration == 0:
            # Equal weights if no estimates available
            equal_weight = 100.0 / len(phase_estimates)
            return {estimate.phase_name: equal_weight for estimate in phase_estimates}
        
        weights = {}
        for estimate in phase_estimates:
            weight = (estimate.estimated_duration_seconds / total_duration) * 100.0
            weights[estimate.phase_name] = weight
        
        return weights
    
    def estimate_overall_progress(self,
                                current_phase: str,
                                phase_progress: float,
                                phase_estimates: List[PhaseEstimate]) -> float:
        """Estimate overall progress based on current phase and phase progress."""
        weights = self.calculate_progress_weights(phase_estimates)
        
        # Calculate cumulative progress up to current phase
        cumulative_progress = 0.0
        current_phase_found = False
        
        for estimate in phase_estimates:
            if estimate.phase_name == current_phase:
                current_phase_found = True
                # Add partial progress for current phase
                current_phase_weight = weights.get(estimate.phase_name, 0.0)
                cumulative_progress += (phase_progress / 100.0) * current_phase_weight
                break
            else:
                # Add full progress for completed phases
                cumulative_progress += weights.get(estimate.phase_name, 0.0)
        
        if not current_phase_found:
            self.logger.warning(f"Current phase '{current_phase}' not found in estimates")
            return phase_progress  # Fallback to phase progress
        
        return min(cumulative_progress, 100.0)
    
    def get_enhanced_progress_info(self,
                                 current_phase: str,
                                 phase_progress: float,
                                 strategy: ExecutionStrategy,
                                 mapping_config: Optional[Dict] = None,
                                 file_size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Get enhanced progress information with complexity-aware estimates."""
        
        # Analyze mapping complexity
        complexity = self.analyze_mapping_complexity(mapping_config)
        
        # Estimate phase durations
        phase_estimates = self.estimate_phase_durations(strategy, complexity, file_size_bytes)
        
        # Calculate progress weights
        weights = self.calculate_progress_weights(phase_estimates)
        
        # Estimate overall progress
        overall_progress = self.estimate_overall_progress(current_phase, phase_progress, phase_estimates)
        
        # Find current phase estimate
        current_phase_estimate = None
        for estimate in phase_estimates:
            if estimate.phase_name == current_phase:
                current_phase_estimate = estimate
                break
        
        return {
            "overall_progress": overall_progress,
            "complexity_score": complexity.complexity_score,
            "phase_weights": weights,
            "current_phase_estimate": {
                "estimated_duration": current_phase_estimate.estimated_duration_seconds if current_phase_estimate else 0,
                "complexity_factor": current_phase_estimate.complexity_factor if current_phase_estimate else 1.0,
                "base_duration": current_phase_estimate.base_duration if current_phase_estimate else 0
            } if current_phase_estimate else None,
            "total_estimated_duration": sum(e.estimated_duration_seconds for e in phase_estimates),
            "phase_estimates": [
                {
                    "phase_name": e.phase_name,
                    "estimated_duration": e.estimated_duration_seconds,
                    "weight": weights.get(e.phase_name, 0.0)
                }
                for e in phase_estimates
            ]
        }


# Global instance for easy access
progress_estimator = MappingProgressEstimator()