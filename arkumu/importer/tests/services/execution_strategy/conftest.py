"""
Pytest configuration and fixtures for execution strategy service tests
"""

import pytest
from unittest.mock import Mock, patch
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


@pytest.fixture
def mock_mapping_adapter():
    """Mock MappingAdapter for testing"""
    with patch('arkumu.importer.services.execution_strategy.execution_strategy_recommender.MappingAdapter') as mock:
        yield mock


@pytest.fixture
def sample_execution_config():
    """Sample ExecutionConfig for testing"""
    return ExecutionConfig(
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
                    ),
                    ColumnConfig(
                        column_name="description",
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


@pytest.fixture
def complex_execution_config():
    """Complex ExecutionConfig with multiple datasets and relationships"""
    return ExecutionConfig(
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
                        is_multi_value=True,
                        multi_value_separator=","
                    ),
                    ColumnConfig(
                        column_name="orcid",
                        dataset_name="dataset1",
                        arkumu_type="identifier",
                        is_external_ontology=True
                    ),
                    ColumnConfig(
                        column_name="data",
                        dataset_name="dataset1",
                        arkumu_type="text"
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
                    ),
                    ColumnConfig(
                        column_name="value",
                        dataset_name="dataset2",
                        arkumu_type="text"
                    )
                ]
            ),
            DatasetConfig(
                dataset_name="dataset3",
                columns=[
                    ColumnConfig(
                        column_name="id",
                        dataset_name="dataset3",
                        arkumu_type="identifier",
                        is_anchor=True
                    ),
                    ColumnConfig(
                        column_name="parent_id",
                        dataset_name="dataset3",
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
            ),
            FKRelationship(
                source_column="parent_id",
                source_dataset="dataset3",
                target_column="id",
                target_dataset="dataset2",
                relationship_type="references"
            ),
            FKRelationship(
                source_column="categories",
                source_dataset="dataset1",
                target_column="id",
                target_dataset="dataset3",
                relationship_type="references",
                is_multi_value=True
            )
        ],
        relationship_contexts=[],
        external_ontologies=[],
        phases=[]
    )


@pytest.fixture
def sample_file_info():
    """Sample FileInfo for testing"""
    return FileInfo(
        file_size_mb=25.0,
        estimated_rows=25000,
        estimated_columns=8,
        csv_complexity_score=0.3,
        has_large_text_fields=False,
        has_numeric_fields=True,
        encoding="utf-8",
        delimiter=",",
        header_rows=1
    )


@pytest.fixture
def large_file_info():
    """Large FileInfo for testing"""
    return FileInfo(
        file_size_mb=800.0,
        estimated_rows=1500000,
        estimated_columns=25,
        csv_complexity_score=0.7,
        has_large_text_fields=True,
        has_numeric_fields=True,
        encoding="utf-8",
        delimiter=";",
        header_rows=2
    )


@pytest.fixture
def sample_complexity_metrics():
    """Sample MappingComplexityMetrics for testing"""
    return MappingComplexityMetrics(
        total_datasets=1,
        total_columns=3,
        total_relationships=0,
        external_ontology_count=0,
        multi_value_column_count=0,
        anchor_column_count=1,
        dependency_depth=0,
        relationship_complexity_score=0.0,
        data_transformation_complexity=0.1,
        integration_complexity=0.1,
        overall_complexity=ComplexityLevel.LOW
    )


@pytest.fixture
def complex_complexity_metrics():
    """Complex MappingComplexityMetrics for testing"""
    return MappingComplexityMetrics(
        total_datasets=3,
        total_columns=10,
        total_relationships=3,
        external_ontology_count=1,
        multi_value_column_count=2,
        anchor_column_count=3,
        dependency_depth=2,
        relationship_complexity_score=0.6,
        data_transformation_complexity=0.7,
        integration_complexity=0.5,
        overall_complexity=ComplexityLevel.HIGH
    )


@pytest.fixture
def sample_resource_estimation():
    """Sample ResourceEstimation for testing"""
    return ResourceEstimation(
        estimated_memory_mb=100.0,
        estimated_cpu_cores=1,
        estimated_execution_time_minutes=10.0,
        estimated_disk_space_mb=50.0,
        peak_memory_mb=150.0,
        concurrent_processing_capability=1,
        scalability_factor=0.7
    )


@pytest.fixture
def high_resource_estimation():
    """High ResourceEstimation for testing"""
    return ResourceEstimation(
        estimated_memory_mb=500.0,
        estimated_cpu_cores=4,
        estimated_execution_time_minutes=60.0,
        estimated_disk_space_mb=300.0,
        peak_memory_mb=750.0,
        concurrent_processing_capability=4,
        scalability_factor=0.9
    )


@pytest.fixture
def sample_strategy_recommendation(sample_complexity_metrics, sample_resource_estimation):
    """Sample StrategyRecommendation for testing"""
    return StrategyRecommendation(
        strategy=ExecutionStrategy.ENTITY_CENTRIC,
        confidence_score=0.8,
        complexity_metrics=sample_complexity_metrics,
        resource_estimation=sample_resource_estimation,
        advantages=[
            "Complete entity creation in single pass",
            "Excellent for complex relationship handling",
            "Best debugging capabilities"
        ],
        disadvantages=[
            "High memory usage for large datasets",
            "May exceed memory limits"
        ],
        requirements=[
            "Minimum 100MB RAM",
            "Stable network connection"
        ],
        risk_factors=[
            "Memory overflow risk with large datasets"
        ],
        performance_notes=[
            "Estimated execution time: 10.0 minutes",
            "Peak memory usage: 150MB"
        ],
        reasoning="Entity-centric strategy is optimal for this low-complexity mapping with small dataset size",
        alternative_strategies=["streaming", "mapping_driven"]
    )


@pytest.fixture
def sample_csv_sources():
    """Sample CSV sources for testing"""
    return {
        "test_dataset": [
            {"id": "1", "name": "Test Item 1", "description": "Description 1"},
            {"id": "2", "name": "Test Item 2", "description": "Description 2"},
            {"id": "3", "name": "Test Item 3", "description": "Description 3"}
        ]
    }


@pytest.fixture
def large_csv_sources():
    """Large CSV sources for testing"""
    return {
        "dataset1": [{"id": str(i), "name": f"Item {i}", "value": f"Value {i}"} for i in range(1000)],
        "dataset2": [{"id": str(i), "ref_id": str(i % 100), "data": f"Data {i}"} for i in range(500)]
    }


@pytest.fixture
def mock_django_cache():
    """Mock Django cache for testing"""
    with patch('django.core.cache.cache') as mock_cache:
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None
        yield mock_cache


@pytest.fixture
def mock_django_db():
    """Mock Django database operations"""
    with patch('arkumu.metadata.models.mappings.Mapping.objects') as mock_objects:
        mock_mapping = Mock()
        mock_mapping.id = 123
        mock_mapping.name = "Test Mapping"
        mock_mapping.organization_id = "test_org"
        mock_mapping.mapping_config = {
            "datasets": [
                {
                    "dataset_name": "test_dataset",
                    "columns": [
                        {
                            "column_name": "id",
                            "arkumu_type": "identifier",
                            "is_anchor": True
                        }
                    ]
                }
            ]
        }
        mock_objects.get.return_value = mock_mapping
        yield mock_objects


@pytest.fixture
def execution_strategy_recommender():
    """ExecutionStrategyRecommender instance for testing"""
    return ExecutionStrategyRecommender()


@pytest.fixture
def mock_strategy_configs():
    """Mock strategy configurations for testing"""
    return {
        ExecutionStrategy.ENTITY_CENTRIC: {
            'memory_multiplier': 3.5,
            'cpu_efficiency': 0.9,
            'max_recommended_file_mb': 200,
            'max_recommended_relationships': 15,
            'optimal_complexity': ComplexityLevel.LOW
        },
        ExecutionStrategy.STREAMING: {
            'memory_multiplier': 1.5,
            'cpu_efficiency': 0.7,
            'max_recommended_file_mb': 2000,
            'max_recommended_relationships': 30,
            'optimal_complexity': ComplexityLevel.HIGH
        }
    }


@pytest.fixture
def mock_complexity_thresholds():
    """Mock complexity thresholds for testing"""
    return {
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
        'memory_limit_mb': 8192,
        'cpu_cores_available': 4
    }


@pytest.fixture(autouse=True)
def cleanup_patches():
    """Cleanup patches after each test"""
    yield
    # Any cleanup code can go here if needed


# Parametrized fixtures for testing different strategies
@pytest.fixture(params=[
    ExecutionStrategy.ENTITY_CENTRIC,
    ExecutionStrategy.MAPPING_DRIVEN,
    ExecutionStrategy.STREAMING,
    ExecutionStrategy.MULTI_PHASE,
    ExecutionStrategy.HYBRID
])
def execution_strategy(request):
    """Parametrized execution strategy fixture"""
    return request.param


@pytest.fixture(params=[
    ComplexityLevel.LOW,
    ComplexityLevel.MEDIUM,
    ComplexityLevel.HIGH,
    ComplexityLevel.EXTREME
])
def complexity_level(request):
    """Parametrized complexity level fixture"""
    return request.param


@pytest.fixture(params=[
    {"file_size_mb": 5.0, "estimated_rows": 5000, "complexity": "low"},
    {"file_size_mb": 50.0, "estimated_rows": 50000, "complexity": "medium"},
    {"file_size_mb": 500.0, "estimated_rows": 500000, "complexity": "high"},
    {"file_size_mb": 2000.0, "estimated_rows": 2000000, "complexity": "extreme"}
])
def file_size_scenario(request):
    """Parametrized file size scenario fixture"""
    return request.param