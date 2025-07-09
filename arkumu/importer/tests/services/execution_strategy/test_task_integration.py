"""
Test suite for TaskExecutionStrategyService and task integration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from arkumu.importer.services.execution_strategy.task_integration import (
    TaskExecutionStrategyService,
    integrate_strategy_with_import_task
)
from arkumu.importer.services.execution_strategy.execution_strategy_recommender import (
    ExecutionStrategy,
    ComplexityLevel,
    MappingComplexityMetrics,
    ResourceEstimation,
    StrategyRecommendation,
    FileInfo
)
from arkumu.importer.services.mapping_consumer.config_translator import ExecutionConfig
from arkumu.importer.services.orchestrator.strategy_selector import ProcessingStrategy


class TestTaskExecutionStrategyService:
    """Test suite for TaskExecutionStrategyService"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.service = TaskExecutionStrategyService()
        self.test_mapping_id = 123
        self.test_file_info = {
            'file_size_mb': 50.0,
            'estimated_rows': 50000,
            'estimated_columns': 10,
            'csv_complexity_score': 0.4,
            'has_large_text_fields': False,
            'has_numeric_fields': True
        }
        self.test_csv_sources = {
            'test_dataset': [
                {'id': 1, 'name': 'Test 1'},
                {'id': 2, 'name': 'Test 2'}
            ]
        }
        self.test_execution_config = Mock(spec=ExecutionConfig)
    
    def test_init(self):
        """Test TaskExecutionStrategyService initialization"""
        service = TaskExecutionStrategyService()
        
        assert service.recommender is not None
        assert service.integrator is not None
        assert service.mapping_adapter is not None
        assert service.legacy_strategy_selector is not None
    
    def test_select_optimal_strategy_for_import_legacy_auto(self):
        """Test optimal strategy selection with legacy auto mode"""
        # Mock legacy strategy selector
        mock_strategy = ProcessingStrategy.ENTITY_CENTRIC
        mock_analysis = {
            'strategy_analyses': [
                {'strategy': 'entity_centric', 'feasibility_score': 0.8},
                {'strategy': 'streaming', 'feasibility_score': 0.6}
            ]
        }
        
        with patch.object(self.service.legacy_strategy_selector, 'choose_optimal_strategy', return_value=mock_strategy):
            with patch.object(self.service.legacy_strategy_selector, 'analyze_all_strategies', return_value=mock_analysis):
                with patch.object(self.service.legacy_strategy_selector, 'get_strategy_rationale', return_value='Test rationale'):
                    
                    result = self.service.select_optimal_strategy_for_import(
                        execution_config=self.test_execution_config,
                        csv_sources=self.test_csv_sources,
                        execution_strategy="auto"
                    )
                    
                    assert result['strategy'] == 'entity_centric'
                    assert result['source'] == 'legacy_auto'
                    assert result['confidence_score'] == 0.8
                    assert result['reasoning'] == 'Test rationale'
                    assert 'detailed_analysis' in result
                    assert 'alternative_strategies' in result
    
    def test_select_optimal_strategy_for_import_specific_strategy(self):
        """Test optimal strategy selection with specific strategy"""
        result = self.service.select_optimal_strategy_for_import(
            execution_strategy="streaming"
        )
        
        assert result['strategy'] == 'streaming'
        assert result['source'] == 'specific_user'
        assert result['confidence_score'] == 0.5
        assert 'streaming' in result['reasoning']
    
    def test_select_optimal_strategy_for_import_specific_strategy_with_validation(self):
        """Test specific strategy selection with mapping validation"""
        # Mock integrator to return recommendation
        mock_recommendation = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8,
            'reasoning': 'Optimal for small datasets'
        }
        
        with patch.object(self.service.integrator, 'get_strategy_recommendation_for_mapping', return_value=mock_recommendation):
            result = self.service.select_optimal_strategy_for_import(
                mapping_id=self.test_mapping_id,
                file_info=self.test_file_info,
                execution_strategy="entity_centric"
            )
            
            assert result['strategy'] == 'entity_centric'
            assert result['source'] == 'specific_optimal'
            assert result['confidence_score'] == 0.8
            assert 'matches recommended' in result['reasoning']
    
    def test_select_optimal_strategy_for_import_specific_strategy_override(self):
        """Test specific strategy selection that overrides recommendation"""
        # Mock integrator to return different recommendation
        mock_recommendation = {
            'strategy': 'streaming',
            'confidence_score': 0.8,
            'reasoning': 'Optimal for large datasets'
        }
        
        with patch.object(self.service.integrator, 'get_strategy_recommendation_for_mapping', return_value=mock_recommendation):
            result = self.service.select_optimal_strategy_for_import(
                mapping_id=self.test_mapping_id,
                file_info=self.test_file_info,
                execution_strategy="entity_centric"
            )
            
            assert result['strategy'] == 'entity_centric'
            assert result['source'] == 'specific_override'
            assert result['confidence_score'] == 0.5  # Reduced confidence
            assert 'overrides recommended' in result['reasoning']
            assert result['recommended_alternative'] == 'streaming'
    
    def test_select_optimal_strategy_for_import_advanced_mapping(self):
        """Test advanced strategy recommendation with mapping ID"""
        # Mock integrator recommendation
        mock_recommendation = {
            'strategy': 'streaming',
            'confidence_score': 0.9,
            'reasoning': 'Optimal for large datasets',
            'complexity_metrics': {'overall_complexity': 'high'},
            'resource_estimation': {'estimated_memory_mb': 200.0},
            'alternative_strategies': ['multi_phase', 'hybrid'],
            'advantages': ['Memory efficient'],
            'disadvantages': ['Longer execution time'],
            'risk_factors': ['Network interruption']
        }
        
        with patch.object(self.service.integrator, 'get_strategy_recommendation_for_mapping', return_value=mock_recommendation):
            result = self.service.select_optimal_strategy_for_import(
                mapping_id=self.test_mapping_id,
                file_info=self.test_file_info,
                execution_strategy="auto"
            )
            
            assert result['strategy'] == 'streaming'
            assert result['source'] == 'advanced_mapping'
            assert result['confidence_score'] == 0.9
            assert result['reasoning'] == 'Optimal for large datasets'
            assert result['complexity_metrics']['overall_complexity'] == 'high'
            assert result['resource_estimation']['estimated_memory_mb'] == 200.0
            assert 'multi_phase' in result['alternative_strategies']
            assert 'Memory efficient' in result['advantages']
            assert 'Network interruption' in result['risk_factors']
    
    def test_select_optimal_strategy_for_import_advanced_config(self):
        """Test advanced strategy recommendation with execution config"""
        # Mock recommender
        mock_recommendation = StrategyRecommendation(
            strategy=ExecutionStrategy.HYBRID,
            confidence_score=0.7,
            complexity_metrics=MappingComplexityMetrics(
                overall_complexity=ComplexityLevel.MEDIUM
            ),
            resource_estimation=ResourceEstimation(
                estimated_memory_mb=150.0,
                estimated_cpu_cores=2,
                estimated_execution_time_minutes=20.0,
                estimated_disk_space_mb=100.0,
                peak_memory_mb=200.0
            ),
            advantages=['Balanced approach'],
            disadvantages=['Complex coordination'],
            risk_factors=['Coordination failure'],
            reasoning='Hybrid approach for moderate complexity'
        )
        
        with patch.object(self.service.recommender, 'recommend_execution_strategy', return_value=mock_recommendation):
            result = self.service.select_optimal_strategy_for_import(
                execution_config=self.test_execution_config,
                file_info=self.test_file_info,
                execution_strategy="auto"
            )
            
            assert result['strategy'] == 'hybrid'
            assert result['source'] == 'advanced_config'
            assert result['confidence_score'] == 0.7
            assert result['reasoning'] == 'Hybrid approach for moderate complexity'
            assert 'Balanced approach' in result['advantages']
            assert 'Complex coordination' in result['disadvantages']
            assert 'Coordination failure' in result['risk_factors']
    
    def test_select_optimal_strategy_for_import_default(self):
        """Test default strategy selection"""
        result = self.service.select_optimal_strategy_for_import()
        
        assert result['strategy'] == 'entity_centric'
        assert result['source'] == 'default'
        assert result['confidence_score'] == 0.5
        assert 'default' in result['reasoning'].lower()
    
    def test_select_optimal_strategy_for_import_error_handling(self):
        """Test error handling in strategy selection"""
        # Mock integrator to raise exception
        with patch.object(self.service.integrator, 'get_strategy_recommendation_for_mapping', side_effect=Exception("Test error")):
            result = self.service.select_optimal_strategy_for_import(
                mapping_id=self.test_mapping_id,
                execution_strategy="auto"
            )
            
            assert result['strategy'] == 'entity_centric'
            assert result['source'] == 'fallback'
            assert result['confidence_score'] == 0.1
            assert 'error' in result
            assert 'fallback' in result['reasoning'].lower()
    
    def test_prepare_execution_context_entity_centric(self):
        """Test execution context preparation for entity-centric strategy"""
        strategy_result = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8,
            'resource_estimation': {
                'estimated_memory_mb': 100.0,
                'estimated_cpu_cores': 1,
                'estimated_execution_time_minutes': 10.0,
                'peak_memory_mb': 150.0,
                'concurrent_processing_capability': 1
            }
        }
        
        context = self.service.prepare_execution_context(
            strategy_result,
            mapping_id=self.test_mapping_id,
            file_info=self.test_file_info
        )
        
        assert context['strategy'] == 'entity_centric'
        assert context['confidence_score'] == 0.8
        assert context['optimizations']['batch_size'] == 1000
        assert context['optimizations']['memory_buffer_size'] == '2GB'
        assert context['optimizations']['enable_relationship_caching'] is True
        assert context['optimizations']['use_bulk_operations'] is True
        assert context['resource_hints']['estimated_memory_mb'] == 100.0
        assert context['monitoring_config']['track_memory_usage'] is True
    
    def test_prepare_execution_context_streaming(self):
        """Test execution context preparation for streaming strategy"""
        strategy_result = {
            'strategy': 'streaming',
            'confidence_score': 0.7,
            'resource_estimation': {
                'estimated_memory_mb': 80.0,
                'estimated_cpu_cores': 2,
                'estimated_execution_time_minutes': 15.0,
                'peak_memory_mb': 120.0,
                'concurrent_processing_capability': 2
            }
        }
        
        context = self.service.prepare_execution_context(
            strategy_result,
            mapping_id=self.test_mapping_id,
            file_info=self.test_file_info
        )
        
        assert context['strategy'] == 'streaming'
        assert context['optimizations']['batch_size'] == 5000
        assert context['optimizations']['memory_buffer_size'] == '500MB'
        assert context['optimizations']['enable_streaming'] is True
        assert context['optimizations']['streaming_chunk_size'] == 10000
        assert context['optimizations']['temporary_storage'] is True
    
    def test_prepare_execution_context_large_file_optimizations(self):
        """Test execution context preparation with large file optimizations"""
        strategy_result = {
            'strategy': 'multi_phase',
            'confidence_score': 0.6
        }
        
        large_file_info = {
            'file_size_mb': 1500.0,  # Large file
            'estimated_rows': 2000000  # High volume
        }
        
        context = self.service.prepare_execution_context(
            strategy_result,
            file_info=large_file_info
        )
        
        assert context['optimizations']['large_file_mode'] is True
        assert context['optimizations']['streaming_required'] is True
        assert context['optimizations']['high_volume_mode'] is True
        assert context['optimizations']['batch_size'] <= 2000  # Capped batch size
    
    def test_prepare_execution_context_error_handling(self):
        """Test error handling in execution context preparation"""
        strategy_result = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8
        }
        
        # Mock an error in context preparation
        with patch.object(self.service, 'prepare_execution_context', side_effect=Exception("Context error")):
            # Call the actual method to test error handling
            context = TaskExecutionStrategyService().prepare_execution_context(strategy_result)
            
            assert 'error' in context
            assert context['strategy'] == 'entity_centric'
            assert context['confidence_score'] == 0.1
            assert 'batch_size' in context['optimizations']
    
    def test_create_enhanced_import_metadata(self):
        """Test enhanced import metadata creation"""
        strategy_result = {
            'strategy': 'streaming',
            'confidence_score': 0.8,
            'reasoning': 'Optimal for large datasets',
            'complexity_metrics': {'overall_complexity': 'high'},
            'alternative_strategies': ['multi_phase', 'hybrid'],
            'risk_factors': ['Network interruption', 'Memory overflow']
        }
        
        execution_context = {
            'strategy': 'streaming',
            'optimizations': {'batch_size': 5000, 'enable_streaming': True},
            'resource_hints': {'estimated_memory_mb': 200.0, 'estimated_time_minutes': 20.0},
            'monitoring_config': {'track_memory_usage': True}
        }
        
        metadata = self.service.create_enhanced_import_metadata(
            strategy_result,
            execution_context,
            mapping_id=self.test_mapping_id,
            task_id='test_task_123'
        )
        
        assert metadata['strategy_analysis']['selected_strategy'] == 'streaming'
        assert metadata['strategy_analysis']['confidence_score'] == 0.8
        assert metadata['strategy_analysis']['reasoning'] == 'Optimal for large datasets'
        assert 'multi_phase' in metadata['strategy_analysis']['alternative_strategies']
        
        assert metadata['execution_context']['strategy'] == 'streaming'
        assert metadata['execution_context']['optimizations']['batch_size'] == 5000
        
        assert metadata['performance_predictions']['estimated_memory_mb'] == 200.0
        assert metadata['performance_predictions']['estimated_time_minutes'] == 20.0
        
        assert metadata['task_metadata']['task_id'] == 'test_task_123'
        assert metadata['task_metadata']['mapping_id'] == self.test_mapping_id
        assert metadata['task_metadata']['strategy_service_version'] == '1.0.0'
        
        assert metadata['complexity_analysis']['overall_complexity'] == 'high'
        
        assert metadata['risk_assessment']['risk_factors'] == ['Network interruption', 'Memory overflow']
        assert len(metadata['risk_assessment']['mitigation_strategies']) > 0
    
    def test_create_enhanced_import_metadata_error_handling(self):
        """Test error handling in enhanced import metadata creation"""
        strategy_result = {
            'strategy': 'entity_centric',
            'confidence_score': 0.8
        }
        
        execution_context = {}
        
        # Mock an error in metadata creation
        with patch.object(self.service, 'create_enhanced_import_metadata', side_effect=Exception("Metadata error")):
            # Call the actual method to test error handling
            metadata = TaskExecutionStrategyService().create_enhanced_import_metadata(
                strategy_result, execution_context
            )
            
            assert 'error' in metadata
            assert metadata['strategy_analysis']['selected_strategy'] == 'entity_centric'
            assert metadata['strategy_analysis']['confidence_score'] == 0.1
            assert 'fallback' in metadata['strategy_analysis']['reasoning'].lower()
    
    def test_generate_risk_mitigation_strategies(self):
        """Test risk mitigation strategy generation"""
        risk_factors = [
            'High memory usage may cause system instability',
            'Complex relationships may slow processing significantly',
            'Deep dependencies may require many phases',
            'Network interruption during external ontology lookup'
        ]
        
        mitigation_strategies = self.service._generate_risk_mitigation_strategies(risk_factors)
        
        assert len(mitigation_strategies) > 0
        assert any('memory' in strategy.lower() for strategy in mitigation_strategies)
        assert any('relationship' in strategy.lower() for strategy in mitigation_strategies)
        assert any('dependency' in strategy.lower() for strategy in mitigation_strategies)
        assert any('performance' in strategy.lower() for strategy in mitigation_strategies)
        
        # Check for uniqueness
        assert len(mitigation_strategies) == len(set(mitigation_strategies))
    
    def test_handle_legacy_auto_strategy_error(self):
        """Test error handling in legacy auto strategy"""
        # Mock legacy selector to raise exception
        with patch.object(self.service.legacy_strategy_selector, 'choose_optimal_strategy', side_effect=Exception("Legacy error")):
            result = self.service._handle_legacy_auto_strategy(
                self.test_execution_config,
                self.test_csv_sources
            )
            
            assert result['strategy'] == 'entity_centric'
            assert result['source'] == 'fallback'
            assert result['confidence_score'] == 0.1
            assert 'legacy strategy selection error' in result['reasoning']
    
    def test_handle_specific_strategy_invalid(self):
        """Test handling of invalid specific strategy"""
        result = self.service._handle_specific_strategy(
            'invalid_strategy',
            mapping_id=self.test_mapping_id
        )
        
        assert result['strategy'] == 'invalid_strategy'
        assert result['source'] == 'specific_fallback'
        assert result['confidence_score'] == 0.2
        assert 'validation error' in result['reasoning']
    
    def test_handle_advanced_strategy_recommendation_error(self):
        """Test error handling in advanced strategy recommendation"""
        # Mock integrator to raise exception
        with patch.object(self.service.integrator, 'get_strategy_recommendation_for_mapping', side_effect=Exception("Advanced error")):
            result = self.service._handle_advanced_strategy_recommendation(
                mapping_id=self.test_mapping_id
            )
            
            assert result['strategy'] == 'entity_centric'
            assert result['source'] == 'fallback'
            assert result['confidence_score'] == 0.1
            assert 'advanced recommendation error' in result['reasoning']


class TestIntegrateStrategyWithImportTask:
    """Test suite for integrate_strategy_with_import_task function"""
    
    def test_integrate_strategy_with_import_task_complete_flow(self):
        """Test complete integration flow with import task"""
        test_mapping_id = 123
        test_file_info = {
            'file_size_mb': 100.0,
            'estimated_rows': 100000,
            'estimated_columns': 15
        }
        test_task_id = 'test_task_456'
        
        # Mock TaskExecutionStrategyService
        with patch('arkumu.importer.services.execution_strategy.task_integration.TaskExecutionStrategyService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock service methods
            mock_strategy_result = {
                'strategy': 'hybrid',
                'confidence_score': 0.8,
                'reasoning': 'Optimal for moderate complexity'
            }
            mock_service.select_optimal_strategy_for_import.return_value = mock_strategy_result
            
            mock_execution_context = {
                'strategy': 'hybrid',
                'optimizations': {'batch_size': 3000},
                'resource_hints': {'estimated_memory_mb': 150.0}
            }
            mock_service.prepare_execution_context.return_value = mock_execution_context
            
            mock_enhanced_metadata = {
                'strategy_analysis': {'selected_strategy': 'hybrid'},
                'execution_context': mock_execution_context,
                'task_metadata': {'task_id': test_task_id}
            }
            mock_service.create_enhanced_import_metadata.return_value = mock_enhanced_metadata
            
            # Call integration function
            result = integrate_strategy_with_import_task(
                mapping_id=test_mapping_id,
                file_info=test_file_info,
                execution_strategy="auto",
                task_id=test_task_id
            )
            
            # Verify results
            assert result['integration_status'] == 'success'
            assert result['strategy_result'] == mock_strategy_result
            assert result['execution_context'] == mock_execution_context
            assert result['enhanced_metadata'] == mock_enhanced_metadata
            
            # Verify service method calls
            mock_service.select_optimal_strategy_for_import.assert_called_once_with(
                mapping_id=test_mapping_id,
                execution_config=None,
                file_info=test_file_info,
                csv_sources=None,
                execution_strategy="auto"
            )
            
            mock_service.prepare_execution_context.assert_called_once_with(
                strategy_result=mock_strategy_result,
                mapping_id=test_mapping_id,
                file_info=test_file_info
            )
            
            mock_service.create_enhanced_import_metadata.assert_called_once_with(
                strategy_result=mock_strategy_result,
                execution_context=mock_execution_context,
                mapping_id=test_mapping_id,
                task_id=test_task_id
            )
    
    def test_integrate_strategy_with_import_task_minimal_parameters(self):
        """Test integration with minimal parameters"""
        with patch('arkumu.importer.services.execution_strategy.task_integration.TaskExecutionStrategyService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock minimal responses
            mock_service.select_optimal_strategy_for_import.return_value = {
                'strategy': 'entity_centric',
                'source': 'default'
            }
            mock_service.prepare_execution_context.return_value = {
                'strategy': 'entity_centric',
                'optimizations': {}
            }
            mock_service.create_enhanced_import_metadata.return_value = {
                'strategy_analysis': {'selected_strategy': 'entity_centric'}
            }
            
            result = integrate_strategy_with_import_task()
            
            assert result['integration_status'] == 'success'
            assert 'strategy_result' in result
            assert 'execution_context' in result
            assert 'enhanced_metadata' in result
    
    def test_integrate_strategy_with_import_task_with_execution_config(self):
        """Test integration with execution config"""
        mock_execution_config = Mock(spec=ExecutionConfig)
        mock_csv_sources = {'test_dataset': []}
        
        with patch('arkumu.importer.services.execution_strategy.task_integration.TaskExecutionStrategyService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            # Mock responses
            mock_service.select_optimal_strategy_for_import.return_value = {
                'strategy': 'streaming',
                'source': 'legacy_auto'
            }
            mock_service.prepare_execution_context.return_value = {
                'strategy': 'streaming',
                'optimizations': {'enable_streaming': True}
            }
            mock_service.create_enhanced_import_metadata.return_value = {
                'strategy_analysis': {'selected_strategy': 'streaming'}
            }
            
            result = integrate_strategy_with_import_task(
                execution_config=mock_execution_config,
                csv_sources=mock_csv_sources,
                execution_strategy="auto"
            )
            
            assert result['integration_status'] == 'success'
            
            # Verify execution config was passed
            mock_service.select_optimal_strategy_for_import.assert_called_once_with(
                mapping_id=None,
                execution_config=mock_execution_config,
                file_info=None,
                csv_sources=mock_csv_sources,
                execution_strategy="auto"
            )