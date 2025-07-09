"""
Test suite for ExecutionStrategyIntegrator and integration helpers
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.http import JsonResponse
from django.test import RequestFactory

from arkumu.importer.services.execution_strategy.integration_helpers import (
    ExecutionStrategyIntegrator,
    create_strategy_recommendation_view_response,
    create_strategy_comparison_view_response
)
from arkumu.importer.services.execution_strategy.execution_strategy_recommender import (
    ExecutionStrategy,
    ComplexityLevel,
    MappingComplexityMetrics,
    ResourceEstimation,
    StrategyRecommendation,
    FileInfo
)


class TestExecutionStrategyIntegrator:
    """Test suite for ExecutionStrategyIntegrator"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.integrator = ExecutionStrategyIntegrator()
        self.test_mapping_id = 123
        self.test_file_info = {
            'file_size_mb': 50.0,
            'estimated_rows': 50000,
            'estimated_columns': 10,
            'csv_complexity_score': 0.4,
            'has_large_text_fields': False,
            'has_numeric_fields': True,
            'encoding': 'utf-8',
            'delimiter': ',',
            'header_rows': 1
        }
    
    def test_init(self):
        """Test ExecutionStrategyIntegrator initialization"""
        integrator = ExecutionStrategyIntegrator()
        
        assert integrator.recommender is not None
        assert integrator.mapping_adapter is not None
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.get_strategy_recommendation_for_mapping')
    def test_get_strategy_recommendation_for_mapping_success(self, mock_get_recommendation):
        """Test successful strategy recommendation retrieval"""
        # Mock the recommendation
        mock_recommendation = {
            'mapping_id': self.test_mapping_id,
            'strategy': 'entity_centric',
            'confidence_score': 0.8,
            'complexity_metrics': {
                'overall_complexity': 'low',
                'total_datasets': 1,
                'total_columns': 5
            },
            'resource_estimation': {
                'estimated_memory_mb': 100.0,
                'estimated_execution_time_minutes': 10.0
            },
            'reasoning': 'Test reasoning',
            'advantages': ['Fast processing'],
            'disadvantages': ['High memory usage']
        }
        
        mock_get_recommendation.return_value = mock_recommendation
        
        result = self.integrator.get_strategy_recommendation_for_mapping(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert result == mock_recommendation
        mock_get_recommendation.assert_called_once_with(
            self.test_mapping_id,
            self.test_file_info
        )
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.mapping_adapter')
    def test_get_strategy_recommendation_for_mapping_error(self, mock_mapping_adapter):
        """Test error handling in strategy recommendation retrieval"""
        # Mock an error in loading mapping config
        mock_mapping_adapter.load_mapping_config.side_effect = Exception("Database error")
        
        result = self.integrator.get_strategy_recommendation_for_mapping(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert 'error' in result
        assert result['mapping_id'] == self.test_mapping_id
        assert result['status'] == 'error'
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.mapping_adapter')
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.recommender')
    def test_analyze_mapping_complexity_for_view_success(self, mock_recommender, mock_mapping_adapter):
        """Test successful mapping complexity analysis for view"""
        # Mock mapping adapter
        mock_mapping_adapter.load_mapping_config.return_value = {'test': 'config'}
        mock_mapping_adapter.config_translator.translate_mapping_config.return_value = Mock()
        
        # Mock complexity metrics
        mock_complexity_metrics = MappingComplexityMetrics(
            total_datasets=1,
            total_columns=5,
            total_relationships=0,
            external_ontology_count=0,
            multi_value_column_count=0,
            anchor_column_count=1,
            dependency_depth=0,
            relationship_complexity_score=0.0,
            data_transformation_complexity=0.0,
            integration_complexity=0.0,
            overall_complexity=ComplexityLevel.LOW
        )
        
        mock_recommender.analyze_mapping_complexity.return_value = mock_complexity_metrics
        
        # Mock serialization method
        expected_result = {
            'mapping_id': self.test_mapping_id,
            'total_datasets': 1,
            'total_columns': 5,
            'overall_complexity': 'low'
        }
        
        with patch.object(self.integrator, '_serialize_complexity_metrics', return_value=expected_result):
            result = self.integrator.analyze_mapping_complexity_for_view(self.test_mapping_id)
            
            assert result == expected_result
            mock_mapping_adapter.load_mapping_config.assert_called_once_with(self.test_mapping_id)
            mock_recommender.analyze_mapping_complexity.assert_called_once()
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.mapping_adapter')
    def test_analyze_mapping_complexity_for_view_error(self, mock_mapping_adapter):
        """Test error handling in mapping complexity analysis for view"""
        # Mock an error
        mock_mapping_adapter.load_mapping_config.side_effect = Exception("Database error")
        
        result = self.integrator.analyze_mapping_complexity_for_view(self.test_mapping_id)
        
        assert 'error' in result
        assert result['mapping_id'] == self.test_mapping_id
        assert result['status'] == 'error'
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.mapping_adapter')
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.recommender')
    def test_get_all_strategy_analyses_success(self, mock_recommender, mock_mapping_adapter):
        """Test successful retrieval of all strategy analyses"""
        # Mock mapping adapter
        mock_mapping_adapter.load_mapping_config.return_value = {'test': 'config'}
        mock_mapping_adapter.config_translator.translate_mapping_config.return_value = Mock()
        
        # Mock complexity metrics
        mock_complexity_metrics = MappingComplexityMetrics(
            total_datasets=1,
            total_columns=5,
            total_relationships=0,
            external_ontology_count=0,
            multi_value_column_count=0,
            anchor_column_count=1,
            dependency_depth=0,
            relationship_complexity_score=0.0,
            data_transformation_complexity=0.0,
            integration_complexity=0.0,
            overall_complexity=ComplexityLevel.LOW
        )
        
        mock_recommender.analyze_mapping_complexity.return_value = mock_complexity_metrics
        
        # Mock resource estimation
        mock_resource_estimation = ResourceEstimation(
            estimated_memory_mb=100.0,
            estimated_cpu_cores=1,
            estimated_execution_time_minutes=10.0,
            estimated_disk_space_mb=50.0,
            peak_memory_mb=150.0,
            concurrent_processing_capability=1,
            scalability_factor=0.8
        )
        
        mock_recommender.estimate_performance_impact.return_value = mock_resource_estimation
        mock_recommender._calculate_confidence_score.return_value = 0.8
        mock_recommender._analyze_strategy_characteristics.return_value = (
            ['advantage1'], ['disadvantage1'], ['requirement1'], ['risk1'], ['note1']
        )
        
        # Mock serialization
        with patch.object(self.integrator, '_serialize_recommendation') as mock_serialize:
            mock_serialize.return_value = {
                'strategy': 'entity_centric',
                'confidence_score': 0.8,
                'mapping_id': self.test_mapping_id
            }
            
            result = self.integrator.get_all_strategy_analyses(
                self.test_mapping_id,
                self.test_file_info
            )
            
            assert result['status'] == 'success'
            assert result['mapping_id'] == self.test_mapping_id
            assert 'strategy_analyses' in result
            assert 'complexity_metrics' in result
            assert 'recommended_strategy' in result
            
            # Should have 5 strategy analyses (all except AUTO)
            assert len(result['strategy_analyses']) == 5
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.render_to_string')
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.get_strategy_recommendation_for_mapping')
    def test_render_strategy_recommendation_template_success(self, mock_get_recommendation, mock_render):
        """Test successful template rendering"""
        # Mock recommendation data
        mock_recommendation = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8,
            'reasoning': 'Test reasoning'
        }
        
        mock_get_recommendation.return_value = mock_recommendation
        mock_render.return_value = '<div>Rendered template</div>'
        
        result = self.integrator.render_strategy_recommendation_template(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert result == '<div>Rendered template</div>'
        mock_get_recommendation.assert_called_once_with(self.test_mapping_id, self.test_file_info)
        mock_render.assert_called_once()
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.get_strategy_recommendation_for_mapping')
    def test_render_strategy_recommendation_template_error(self, mock_get_recommendation):
        """Test error handling in template rendering"""
        # Mock an error
        mock_get_recommendation.side_effect = Exception("Rendering error")
        
        result = self.integrator.render_strategy_recommendation_template(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert 'error' in result.lower()
        assert 'rendering error' in result
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator.get_all_strategy_analyses')
    def test_get_strategy_comparison_data_success(self, mock_get_analyses):
        """Test successful strategy comparison data retrieval"""
        # Mock strategy analyses
        mock_analyses = {
            'status': 'success',
            'strategy_analyses': [
                {
                    'strategy': 'entity_centric',
                    'confidence_score': 0.8,
                    'resource_estimation': {
                        'estimated_memory_mb': 100.0,
                        'estimated_execution_time_minutes': 10.0,
                        'estimated_cpu_cores': 1,
                        'estimated_disk_space_mb': 50.0
                    }
                },
                {
                    'strategy': 'streaming',
                    'confidence_score': 0.6,
                    'resource_estimation': {
                        'estimated_memory_mb': 80.0,
                        'estimated_execution_time_minutes': 15.0,
                        'estimated_cpu_cores': 2,
                        'estimated_disk_space_mb': 40.0
                    }
                }
            ]
        }
        
        mock_get_analyses.return_value = mock_analyses
        
        result = self.integrator.get_strategy_comparison_data(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert 'strategies' in result
        assert 'metrics' in result
        assert 'chart_data' in result
        assert len(result['strategies']) == 2
        assert len(result['metrics']['memory_usage']) == 2
        assert len(result['chart_data']['labels']) == 2
        assert len(result['chart_data']['datasets']) == 3  # Memory, time, confidence
    
    def test_serialize_recommendation(self):
        """Test recommendation serialization"""
        # Create test recommendation
        complexity_metrics = MappingComplexityMetrics(
            total_datasets=1,
            total_columns=5,
            total_relationships=0,
            external_ontology_count=0,
            multi_value_column_count=0,
            anchor_column_count=1,
            dependency_depth=0,
            relationship_complexity_score=0.0,
            data_transformation_complexity=0.0,
            integration_complexity=0.0,
            overall_complexity=ComplexityLevel.LOW
        )
        
        resource_estimation = ResourceEstimation(
            estimated_memory_mb=100.0,
            estimated_cpu_cores=1,
            estimated_execution_time_minutes=10.0,
            estimated_disk_space_mb=50.0,
            peak_memory_mb=150.0,
            concurrent_processing_capability=1,
            scalability_factor=0.8
        )
        
        recommendation = StrategyRecommendation(
            strategy=ExecutionStrategy.ENTITY_CENTRIC,
            confidence_score=0.8,
            complexity_metrics=complexity_metrics,
            resource_estimation=resource_estimation,
            advantages=['Fast processing'],
            disadvantages=['High memory usage'],
            requirements=['Sufficient RAM'],
            risk_factors=['Memory overflow'],
            performance_notes=['Optimal for small datasets'],
            reasoning='Test reasoning',
            alternative_strategies=['streaming', 'multi_phase']
        )
        
        result = self.integrator._serialize_recommendation(recommendation, self.test_mapping_id)
        
        assert result['mapping_id'] == self.test_mapping_id
        assert result['strategy'] == 'entity_centric'
        assert result['confidence_score'] == 0.8
        assert 'complexity_metrics' in result
        assert 'resource_estimation' in result
        assert result['advantages'] == ['Fast processing']
        assert result['disadvantages'] == ['High memory usage']
        assert result['reasoning'] == 'Test reasoning'
        assert result['alternative_strategies'] == ['streaming', 'multi_phase']
    
    def test_serialize_complexity_metrics(self):
        """Test complexity metrics serialization"""
        metrics = MappingComplexityMetrics(
            total_datasets=2,
            total_columns=10,
            total_relationships=3,
            external_ontology_count=1,
            multi_value_column_count=2,
            anchor_column_count=2,
            dependency_depth=1,
            relationship_complexity_score=0.3,
            data_transformation_complexity=0.2,
            integration_complexity=0.1,
            overall_complexity=ComplexityLevel.MEDIUM
        )
        
        result = self.integrator._serialize_complexity_metrics(metrics, self.test_mapping_id)
        
        assert result['mapping_id'] == self.test_mapping_id
        assert result['total_datasets'] == 2
        assert result['total_columns'] == 10
        assert result['total_relationships'] == 3
        assert result['external_ontology_count'] == 1
        assert result['multi_value_column_count'] == 2
        assert result['anchor_column_count'] == 2
        assert result['dependency_depth'] == 1
        assert result['overall_complexity'] == 'medium'
        assert 'complexity_summary' in result
    
    def test_generate_complexity_summary_low(self):
        """Test complexity summary generation for low complexity"""
        metrics = MappingComplexityMetrics(
            total_datasets=1,
            total_columns=5,
            total_relationships=0,
            external_ontology_count=0,
            multi_value_column_count=0,
            anchor_column_count=1,
            dependency_depth=0,
            relationship_complexity_score=0.0,
            data_transformation_complexity=0.0,
            integration_complexity=0.0,
            overall_complexity=ComplexityLevel.LOW
        )
        
        summary = self.integrator._generate_complexity_summary(metrics)
        
        assert summary['level'] == 'low'
        assert 'simple' in summary['description'].lower()
        assert 'entity-centric' in summary['recommendations'][0].lower()
        assert isinstance(summary['key_factors'], list)
    
    def test_generate_complexity_summary_high(self):
        """Test complexity summary generation for high complexity"""
        metrics = MappingComplexityMetrics(
            total_datasets=5,
            total_columns=50,
            total_relationships=15,
            external_ontology_count=3,
            multi_value_column_count=5,
            anchor_column_count=5,
            dependency_depth=4,
            relationship_complexity_score=0.8,
            data_transformation_complexity=0.7,
            integration_complexity=0.6,
            overall_complexity=ComplexityLevel.HIGH
        )
        
        summary = self.integrator._generate_complexity_summary(metrics)
        
        assert summary['level'] == 'high'
        assert 'complex' in summary['description'].lower()
        assert len(summary['key_factors']) > 0
        assert 'streaming' in summary['recommendations'][0].lower() or 'hybrid' in summary['recommendations'][0].lower()


class TestIntegrationHelperFunctions:
    """Test suite for integration helper functions"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.test_mapping_id = 123
        self.test_file_info = {
            'file_size_mb': 50.0,
            'estimated_rows': 50000,
            'estimated_columns': 10
        }
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator')
    def test_create_strategy_recommendation_view_response_success(self, mock_integrator_class):
        """Test successful strategy recommendation view response creation"""
        # Mock integrator
        mock_integrator = Mock()
        mock_integrator_class.return_value = mock_integrator
        
        # Mock successful recommendation
        mock_recommendation = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8,
            'reasoning': 'Test reasoning'
        }
        
        mock_integrator.get_strategy_recommendation_for_mapping.return_value = mock_recommendation
        
        response = create_strategy_recommendation_view_response(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert isinstance(response, JsonResponse)
        assert response.status_code == 200
        
        # Parse response content
        import json
        content = json.loads(response.content.decode('utf-8'))
        assert content['success'] is True
        assert content['data'] == mock_recommendation
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator')
    def test_create_strategy_recommendation_view_response_error(self, mock_integrator_class):
        """Test error handling in strategy recommendation view response creation"""
        # Mock integrator
        mock_integrator = Mock()
        mock_integrator_class.return_value = mock_integrator
        
        # Mock error response
        mock_error_response = {
            'error': 'Database error',
            'mapping_id': self.test_mapping_id
        }
        
        mock_integrator.get_strategy_recommendation_for_mapping.return_value = mock_error_response
        
        response = create_strategy_recommendation_view_response(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert isinstance(response, JsonResponse)
        assert response.status_code == 400
        
        # Parse response content
        import json
        content = json.loads(response.content.decode('utf-8'))
        assert content['success'] is False
        assert 'error' in content
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator')
    def test_create_strategy_recommendation_view_response_exception(self, mock_integrator_class):
        """Test exception handling in strategy recommendation view response creation"""
        # Mock integrator to raise exception
        mock_integrator = Mock()
        mock_integrator_class.return_value = mock_integrator
        mock_integrator.get_strategy_recommendation_for_mapping.side_effect = Exception("Unexpected error")
        
        response = create_strategy_recommendation_view_response(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert isinstance(response, JsonResponse)
        assert response.status_code == 500
        
        # Parse response content
        import json
        content = json.loads(response.content.decode('utf-8'))
        assert content['success'] is False
        assert 'error' in content
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator')
    def test_create_strategy_comparison_view_response_success(self, mock_integrator_class):
        """Test successful strategy comparison view response creation"""
        # Mock integrator
        mock_integrator = Mock()
        mock_integrator_class.return_value = mock_integrator
        
        # Mock successful comparison data
        mock_comparison_data = {
            'strategies': [
                {'name': 'entity_centric', 'confidence': 0.8},
                {'name': 'streaming', 'confidence': 0.6}
            ],
            'metrics': {
                'memory_usage': [100.0, 80.0],
                'execution_time': [10.0, 15.0]
            }
        }
        
        mock_integrator.get_strategy_comparison_data.return_value = mock_comparison_data
        
        response = create_strategy_comparison_view_response(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert isinstance(response, JsonResponse)
        assert response.status_code == 200
        
        # Parse response content
        import json
        content = json.loads(response.content.decode('utf-8'))
        assert content['success'] is True
        assert content['data'] == mock_comparison_data
    
    @patch('arkumu.importer.services.execution_strategy.integration_helpers.ExecutionStrategyIntegrator')
    def test_create_strategy_comparison_view_response_error(self, mock_integrator_class):
        """Test error handling in strategy comparison view response creation"""
        # Mock integrator
        mock_integrator = Mock()
        mock_integrator_class.return_value = mock_integrator
        
        # Mock error response
        mock_error_response = {
            'error': 'Analysis failed',
            'mapping_id': self.test_mapping_id
        }
        
        mock_integrator.get_strategy_comparison_data.return_value = mock_error_response
        
        response = create_strategy_comparison_view_response(
            self.test_mapping_id,
            self.test_file_info
        )
        
        assert isinstance(response, JsonResponse)
        assert response.status_code == 400
        
        # Parse response content
        import json
        content = json.loads(response.content.decode('utf-8'))
        assert content['success'] is False
        assert 'error' in content