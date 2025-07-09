"""
Test suite for ExecutionStrategyRecommender
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import List, Dict, Any

from arkumu.importer.services.execution_strategy.execution_strategy_recommender import (
    ExecutionStrategyRecommender,
    ExecutionStrategy,
    ComplexityLevel,
    FileInfo,
    MappingComplexityMetrics,
    ResourceEstimation,
    StrategyRecommendation
)
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig,
    DatasetConfig,
    ColumnConfig,
    FKRelationship,
    ColumnType
)


class TestExecutionStrategyRecommender:
    """Test suite for ExecutionStrategyRecommender"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.recommender = ExecutionStrategyRecommender()
        
        # Create test execution config
        self.test_execution_config = ExecutionConfig(
            datasets=[
                DatasetConfig(
                    dataset_name="test_dataset",
                    columns=[
                        ColumnConfig(
                            column_name="id",
                            dataset_name="test_dataset",
                            arkumu_type="identifier",
                            is_anchor=True
                        ),
                        ColumnConfig(
                            column_name="name",
                            dataset_name="test_dataset",
                            arkumu_type="text"
                        )
                    ]
                )
            ],
            fk_relationships=[],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        # Create test file info
        self.test_file_info = FileInfo(
            file_size_mb=10.0,
            estimated_rows=10000,
            estimated_columns=5,
            csv_complexity_score=0.3,
            has_large_text_fields=False,
            has_numeric_fields=True
        )
    
    def test_init(self):
        """Test ExecutionStrategyRecommender initialization"""
        recommender = ExecutionStrategyRecommender()
        
        assert recommender.mapping_adapter is not None
        assert recommender.complexity_thresholds is not None
        assert recommender.strategy_configs is not None
        assert len(recommender.strategy_configs) == 5  # All strategies except AUTO
    
    def test_recommend_execution_strategy_simple(self):
        """Test strategy recommendation for simple mapping"""
        recommendation = self.recommender.recommend_execution_strategy(
            self.test_execution_config,
            self.test_file_info
        )
        
        assert isinstance(recommendation, StrategyRecommendation)
        assert recommendation.strategy in ExecutionStrategy
        assert 0.0 <= recommendation.confidence_score <= 1.0
        assert recommendation.complexity_metrics is not None
        assert recommendation.resource_estimation is not None
        assert recommendation.reasoning is not None
    
    def test_recommend_execution_strategy_complex(self):
        """Test strategy recommendation for complex mapping"""
        # Create complex execution config
        complex_config = ExecutionConfig(
            datasets=[
                DatasetConfig(
                    dataset_name="dataset1",
                    columns=[
                        ColumnConfig(
                            column_name="id",
                            dataset_name="dataset1",
                            arkumu_type="identifier",
                            is_anchor=True
                        ),
                        ColumnConfig(
                            column_name="categories",
                            dataset_name="dataset1",
                            arkumu_type="text",
                            is_multi_value=True
                        ),
                        ColumnConfig(
                            column_name="orcid",
                            dataset_name="dataset1",
                            arkumu_type="identifier",
                            is_external_ontology=True
                        )
                    ]
                ),
                DatasetConfig(
                    dataset_name="dataset2",
                    columns=[
                        ColumnConfig(
                            column_name="id",
                            dataset_name="dataset2",
                            arkumu_type="identifier",
                            is_anchor=True
                        ),
                        ColumnConfig(
                            column_name="ref_id",
                            dataset_name="dataset2",
                            arkumu_type="identifier"
                        )
                    ]
                )
            ],
            fk_relationships=[
                FKRelationship(
                    source_column="ref_id",
                    source_dataset="dataset2",
                    target_column="id",
                    target_dataset="dataset1",
                    relationship_type="references"
                )
            ],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        # Create large file info
        large_file_info = FileInfo(
            file_size_mb=500.0,
            estimated_rows=1000000,
            estimated_columns=20,
            csv_complexity_score=0.8
        )
        
        recommendation = self.recommender.recommend_execution_strategy(
            complex_config,
            large_file_info
        )
        
        assert isinstance(recommendation, StrategyRecommendation)
        assert recommendation.complexity_metrics.overall_complexity in [
            ComplexityLevel.MEDIUM, ComplexityLevel.HIGH, ComplexityLevel.EXTREME
        ]
        assert recommendation.strategy in [
            ExecutionStrategy.STREAMING, ExecutionStrategy.MULTI_PHASE, ExecutionStrategy.HYBRID
        ]
    
    def test_analyze_mapping_complexity_simple(self):
        """Test mapping complexity analysis for simple mapping"""
        metrics = self.recommender.analyze_mapping_complexity(self.test_execution_config)
        
        assert isinstance(metrics, MappingComplexityMetrics)
        assert metrics.total_datasets == 1
        assert metrics.total_columns == 2
        assert metrics.total_relationships == 0
        assert metrics.external_ontology_count == 0
        assert metrics.multi_value_column_count == 0
        assert metrics.anchor_column_count == 1
        assert metrics.overall_complexity == ComplexityLevel.LOW
    
    def test_analyze_mapping_complexity_complex(self):
        """Test mapping complexity analysis for complex mapping"""
        # Create complex config (reuse from above test)
        complex_config = ExecutionConfig(
            datasets=[
                DatasetConfig(
                    dataset_name="dataset1",
                    columns=[
                        ColumnConfig(
                            column_name="id",
                            dataset_name="dataset1",
                            arkumu_type="identifier",
                            is_anchor=True
                        ),
                        ColumnConfig(
                            column_name="categories",
                            dataset_name="dataset1",
                            arkumu_type="text",
                            is_multi_value=True
                        ),
                        ColumnConfig(
                            column_name="orcid",
                            dataset_name="dataset1",
                            arkumu_type="identifier",
                            is_external_ontology=True
                        )
                    ]
                )
            ],
            fk_relationships=[
                FKRelationship(
                    source_column="ref_id",
                    source_dataset="dataset2",
                    target_column="id",
                    target_dataset="dataset1",
                    relationship_type="references"
                )
            ],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        metrics = self.recommender.analyze_mapping_complexity(complex_config)
        
        assert metrics.total_datasets == 1
        assert metrics.total_columns == 3
        assert metrics.total_relationships == 1
        assert metrics.external_ontology_count == 1
        assert metrics.multi_value_column_count == 1
        assert metrics.anchor_column_count == 1
        assert metrics.overall_complexity in [ComplexityLevel.MEDIUM, ComplexityLevel.HIGH]
    
    def test_estimate_performance_impact_entity_centric(self):
        """Test performance impact estimation for entity-centric strategy"""
        estimation = self.recommender.estimate_performance_impact(
            ExecutionStrategy.ENTITY_CENTRIC,
            self.test_execution_config,
            self.test_file_info
        )
        
        assert isinstance(estimation, ResourceEstimation)
        assert estimation.estimated_memory_mb > 0
        assert estimation.estimated_cpu_cores >= 1
        assert estimation.estimated_execution_time_minutes > 0
        assert estimation.estimated_disk_space_mb > 0
        assert estimation.peak_memory_mb > estimation.estimated_memory_mb
        assert estimation.concurrent_processing_capability >= 1
        assert 0.0 <= estimation.scalability_factor <= 1.0
    
    def test_estimate_performance_impact_streaming(self):
        """Test performance impact estimation for streaming strategy"""
        estimation = self.recommender.estimate_performance_impact(
            ExecutionStrategy.STREAMING,
            self.test_execution_config,
            self.test_file_info
        )
        
        assert isinstance(estimation, ResourceEstimation)
        # Streaming should use less memory than entity-centric
        entity_estimation = self.recommender.estimate_performance_impact(
            ExecutionStrategy.ENTITY_CENTRIC,
            self.test_execution_config,
            self.test_file_info
        )
        assert estimation.estimated_memory_mb < entity_estimation.estimated_memory_mb
    
    def test_calculate_dependency_depth_no_relationships(self):
        """Test dependency depth calculation with no relationships"""
        depth = self.recommender._calculate_dependency_depth(self.test_execution_config)
        assert depth == 0
    
    def test_calculate_dependency_depth_with_relationships(self):
        """Test dependency depth calculation with relationships"""
        config_with_relationships = ExecutionConfig(
            datasets=[
                DatasetConfig(dataset_name="dataset1", columns=[]),
                DatasetConfig(dataset_name="dataset2", columns=[]),
                DatasetConfig(dataset_name="dataset3", columns=[])
            ],
            fk_relationships=[
                FKRelationship(
                    source_column="id1",
                    source_dataset="dataset1",
                    target_column="id2",
                    target_dataset="dataset2",
                    relationship_type="references"
                ),
                FKRelationship(
                    source_column="id2",
                    source_dataset="dataset2",
                    target_column="id3",
                    target_dataset="dataset3",
                    relationship_type="references"
                )
            ],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        depth = self.recommender._calculate_dependency_depth(config_with_relationships)
        assert depth >= 1
    
    def test_calculate_relationship_complexity_no_relationships(self):
        """Test relationship complexity calculation with no relationships"""
        complexity = self.recommender._calculate_relationship_complexity(self.test_execution_config)
        assert complexity == 0.0
    
    def test_calculate_relationship_complexity_with_relationships(self):
        """Test relationship complexity calculation with relationships"""
        config_with_relationships = ExecutionConfig(
            datasets=[DatasetConfig(dataset_name="dataset1", columns=[])],
            fk_relationships=[
                FKRelationship(
                    source_column="id1",
                    source_dataset="dataset1",
                    target_column="id2",
                    target_dataset="dataset2",
                    relationship_type="references",
                    is_multi_value=True
                )
            ],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        complexity = self.recommender._calculate_relationship_complexity(config_with_relationships)
        assert complexity > 0.0
        assert complexity <= 1.0
    
    def test_calculate_transformation_complexity(self):
        """Test transformation complexity calculation"""
        columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="test",
                arkumu_type="identifier",
                is_anchor=True
            ),
            ColumnConfig(
                column_name="categories",
                dataset_name="test",
                arkumu_type="text",
                is_multi_value=True
            ),
            ColumnConfig(
                column_name="orcid",
                dataset_name="test",
                arkumu_type="identifier",
                is_external_ontology=True
            )
        ]
        
        complexity = self.recommender._calculate_transformation_complexity(columns)
        assert complexity > 0.0
        assert complexity <= 1.0
    
    def test_calculate_integration_complexity(self):
        """Test integration complexity calculation"""
        # Create config with multiple datasets
        multi_dataset_config = ExecutionConfig(
            datasets=[
                DatasetConfig(dataset_name=f"dataset{i}", columns=[
                    ColumnConfig(
                        column_name="id",
                        dataset_name=f"dataset{i}",
                        arkumu_type="identifier"
                    )
                ])
                for i in range(3)
            ],
            fk_relationships=[],
            relationship_contexts=[],
            external_ontologies=[],
            phases=[]
        )
        
        complexity = self.recommender._calculate_integration_complexity(multi_dataset_config)
        assert complexity > 0.0
        assert complexity <= 1.0
    
    def test_determine_complexity_level(self):
        """Test complexity level determination"""
        # Low complexity metrics
        low_metrics = MappingComplexityMetrics(
            total_datasets=1,
            total_columns=5,
            total_relationships=0,
            relationship_complexity_score=0.0,
            data_transformation_complexity=0.0,
            integration_complexity=0.0
        )
        
        level = self.recommender._determine_complexity_level(low_metrics)
        assert level == ComplexityLevel.LOW
        
        # High complexity metrics
        high_metrics = MappingComplexityMetrics(
            total_datasets=10,
            total_columns=50,
            total_relationships=20,
            external_ontology_count=5,
            dependency_depth=6,
            relationship_complexity_score=0.8,
            data_transformation_complexity=0.7,
            integration_complexity=0.6
        )
        
        level = self.recommender._determine_complexity_level(high_metrics)
        assert level in [ComplexityLevel.HIGH, ComplexityLevel.EXTREME]
    
    def test_estimate_base_memory_usage_with_file_info(self):
        """Test base memory usage estimation with file info"""
        memory = self.recommender._estimate_base_memory_usage(
            self.test_execution_config,
            self.test_file_info
        )
        
        assert memory > 0
        # Should be based on file size
        assert memory >= self.test_file_info.file_size_mb * 2
    
    def test_estimate_base_memory_usage_without_file_info(self):
        """Test base memory usage estimation without file info"""
        memory = self.recommender._estimate_base_memory_usage(
            self.test_execution_config,
            None
        )
        
        assert memory > 0
        # Should be based on column count estimation
    
    def test_estimate_execution_time(self):
        """Test execution time estimation"""
        time = self.recommender._estimate_execution_time(
            ExecutionStrategy.ENTITY_CENTRIC,
            self.test_execution_config,
            self.test_file_info,
            self.recommender.strategy_configs[ExecutionStrategy.ENTITY_CENTRIC]
        )
        
        assert time > 0
    
    def test_estimate_disk_space_usage(self):
        """Test disk space usage estimation"""
        disk_space = self.recommender._estimate_disk_space_usage(
            self.test_execution_config,
            self.test_file_info
        )
        
        assert disk_space > 0
        # Should be at least the file size
        assert disk_space >= self.test_file_info.file_size_mb
    
    def test_calculate_concurrent_capability(self):
        """Test concurrent processing capability calculation"""
        capability = self.recommender._calculate_concurrent_capability(
            ExecutionStrategy.ENTITY_CENTRIC,
            self.test_execution_config,
            100.0  # 100MB estimated memory
        )
        
        assert capability >= 1
        assert capability <= self.recommender.complexity_thresholds['cpu_cores_available']
    
    def test_calculate_scalability_factor(self):
        """Test scalability factor calculation"""
        factor = self.recommender._calculate_scalability_factor(
            ExecutionStrategy.STREAMING,
            self.test_execution_config
        )
        
        assert 0.0 <= factor <= 1.0
    
    def test_calculate_confidence_score(self):
        """Test confidence score calculation"""
        complexity_metrics = MappingComplexityMetrics(
            overall_complexity=ComplexityLevel.LOW
        )
        
        resource_estimation = ResourceEstimation(
            estimated_memory_mb=100.0,
            estimated_cpu_cores=1,
            estimated_execution_time_minutes=10.0,
            estimated_disk_space_mb=50.0,
            peak_memory_mb=150.0
        )
        
        confidence = self.recommender._calculate_confidence_score(
            ExecutionStrategy.ENTITY_CENTRIC,
            complexity_metrics,
            resource_estimation,
            self.test_file_info
        )
        
        assert 0.0 <= confidence <= 1.0
    
    def test_analyze_strategy_characteristics(self):
        """Test strategy characteristics analysis"""
        complexity_metrics = MappingComplexityMetrics(
            overall_complexity=ComplexityLevel.MEDIUM,
            total_relationships=5
        )
        
        resource_estimation = ResourceEstimation(
            estimated_memory_mb=100.0,
            estimated_cpu_cores=2,
            estimated_execution_time_minutes=15.0,
            estimated_disk_space_mb=80.0,
            peak_memory_mb=150.0,
            concurrent_processing_capability=2
        )
        
        advantages, disadvantages, requirements, risk_factors, performance_notes = (
            self.recommender._analyze_strategy_characteristics(
                ExecutionStrategy.ENTITY_CENTRIC,
                complexity_metrics,
                resource_estimation,
                self.test_file_info
            )
        )
        
        assert isinstance(advantages, list)
        assert isinstance(disadvantages, list)
        assert isinstance(requirements, list)
        assert isinstance(risk_factors, list)
        assert isinstance(performance_notes, list)
        assert len(advantages) > 0
        assert len(performance_notes) > 0
    
    def test_generate_strategy_reasoning(self):
        """Test strategy reasoning generation"""
        recommendation = StrategyRecommendation(
            strategy=ExecutionStrategy.ENTITY_CENTRIC,
            confidence_score=0.8,
            complexity_metrics=MappingComplexityMetrics(
                overall_complexity=ComplexityLevel.LOW,
                total_datasets=1,
                total_columns=5,
                total_relationships=0
            ),
            resource_estimation=ResourceEstimation(
                estimated_memory_mb=100.0,
                estimated_cpu_cores=1,
                estimated_execution_time_minutes=10.0,
                estimated_disk_space_mb=50.0,
                peak_memory_mb=150.0
            )
        )
        
        reasoning = self.recommender._generate_strategy_reasoning(
            recommendation,
            recommendation.complexity_metrics,
            self.test_file_info
        )
        
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
        assert "complexity" in reasoning.lower()
        assert "entity_centric" in reasoning.lower()
    
    def test_analyze_all_strategies(self):
        """Test analysis of all strategies"""
        complexity_metrics = self.recommender.analyze_mapping_complexity(self.test_execution_config)
        
        analyses = self.recommender._analyze_all_strategies(
            self.test_execution_config,
            complexity_metrics,
            self.test_file_info
        )
        
        assert len(analyses) == 5  # All strategies except AUTO
        assert all(isinstance(analysis, StrategyRecommendation) for analysis in analyses)
        assert all(analysis.confidence_score >= 0.0 for analysis in analyses)
        assert all(analysis.confidence_score <= 1.0 for analysis in analyses)
    
    @pytest.mark.parametrize("strategy", [
        ExecutionStrategy.ENTITY_CENTRIC,
        ExecutionStrategy.MAPPING_DRIVEN,
        ExecutionStrategy.STREAMING,
        ExecutionStrategy.MULTI_PHASE,
        ExecutionStrategy.HYBRID
    ])
    def test_all_strategies_performance_estimation(self, strategy):
        """Test performance estimation for all strategies"""
        estimation = self.recommender.estimate_performance_impact(
            strategy,
            self.test_execution_config,
            self.test_file_info
        )
        
        assert isinstance(estimation, ResourceEstimation)
        assert estimation.estimated_memory_mb > 0
        assert estimation.estimated_cpu_cores >= 1
        assert estimation.estimated_execution_time_minutes > 0
        assert estimation.estimated_disk_space_mb > 0
        assert estimation.peak_memory_mb > 0
        assert estimation.concurrent_processing_capability >= 1
        assert 0.0 <= estimation.scalability_factor <= 1.0