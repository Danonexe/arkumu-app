"""
Tests for dependency resolver service.

Tests the DependencyResolver class which handles FK dependencies and determines
processing order for datasets.
"""

import pytest
from unittest.mock import Mock, patch
from arkumu.importer.services.mapping_consumer.dependency_resolver import (
    DependencyResolver, DependencyGraph, ProcessingPhase
)
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig, DatasetConfig, ColumnConfig, FKRelationship, 
    ProcessingStrategy, ColumnType
)


class TestDependencyGraph:
    """Test suite for DependencyGraph class"""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple dependency graph"""
        return DependencyGraph(
            nodes={'A', 'B', 'C'},
            edges=[('A', 'B'), ('B', 'C')]  # A depends on B, B depends on C
        )

    @pytest.fixture
    def complex_graph(self):
        """Create a complex dependency graph"""
        return DependencyGraph(
            nodes={'A', 'B', 'C', 'D', 'E'},
            edges=[
                ('A', 'B'), ('A', 'C'),  # A depends on B and C
                ('B', 'D'),              # B depends on D
                ('C', 'D'),              # C depends on D
                ('E', 'A')               # E depends on A
            ]
        )

    @pytest.fixture
    def circular_graph(self):
        """Create a graph with circular dependencies"""
        return DependencyGraph(
            nodes={'A', 'B', 'C'},
            edges=[('A', 'B'), ('B', 'C'), ('C', 'A')]  # Circular: A -> B -> C -> A
        )

    def test_get_dependencies(self, simple_graph):
        """Test getting direct dependencies for a dataset"""
        assert simple_graph.get_dependencies('A') == ['B']
        assert simple_graph.get_dependencies('B') == ['C']
        assert simple_graph.get_dependencies('C') == []

    def test_get_dependents(self, simple_graph):
        """Test getting datasets that depend on a dataset"""
        assert simple_graph.get_dependents('B') == ['A']
        assert simple_graph.get_dependents('C') == ['B']
        assert simple_graph.get_dependents('A') == []

    def test_has_cycles_false(self, simple_graph):
        """Test cycle detection on acyclic graph"""
        assert simple_graph.has_cycles() is False

    def test_has_cycles_true(self, circular_graph):
        """Test cycle detection on cyclic graph"""
        assert circular_graph.has_cycles() is True

    def test_topological_sort_simple(self, simple_graph):
        """Test topological sort on simple graph"""
        result = simple_graph.topological_sort()
        
        # C should come before B, B should come before A
        assert result.index('C') < result.index('B')
        assert result.index('B') < result.index('A')
        assert len(result) == 3

    def test_topological_sort_complex(self, complex_graph):
        """Test topological sort on complex graph"""
        result = complex_graph.topological_sort()
        
        # D should come before B and C
        # B and C should come before A
        # A should come before E
        assert result.index('D') < result.index('B')
        assert result.index('D') < result.index('C')
        assert result.index('B') < result.index('A')
        assert result.index('C') < result.index('A')
        assert result.index('A') < result.index('E')
        assert len(result) == 5

    def test_topological_sort_circular(self, circular_graph):
        """Test topological sort on circular graph"""
        result = circular_graph.topological_sort()
        
        # Should return incomplete result due to cycle
        assert len(result) < 3


class TestProcessingPhase:
    """Test suite for ProcessingPhase class"""

    def test_processing_phase_creation(self):
        """Test ProcessingPhase creation"""
        phase = ProcessingPhase(
            phase_number=1,
            phase_name='Foundation Phase',
            datasets=['dataset1', 'dataset2'],
            description='Process foundation datasets',
            can_parallel=True,
            estimated_complexity='medium'
        )
        
        assert phase.phase_number == 1
        assert phase.phase_name == 'Foundation Phase'
        assert phase.datasets == ['dataset1', 'dataset2']
        assert phase.description == 'Process foundation datasets'
        assert phase.can_parallel is True
        assert phase.estimated_complexity == 'medium'

    def test_add_dataset(self):
        """Test adding dataset to phase"""
        phase = ProcessingPhase(
            phase_number=1,
            phase_name='Test Phase',
            datasets=['dataset1'],
            description='Test phase'
        )
        
        phase.add_dataset('dataset2')
        assert 'dataset2' in phase.datasets
        assert len(phase.datasets) == 2
        
        # Adding same dataset again should not duplicate
        phase.add_dataset('dataset1')
        assert len(phase.datasets) == 2


class TestDependencyResolver:
    """Test suite for DependencyResolver class"""

    @pytest.fixture
    def dependency_resolver(self):
        """Create a DependencyResolver instance"""
        return DependencyResolver()

    @pytest.fixture
    def simple_execution_config(self):
        """Create a simple execution configuration"""
        config = ExecutionConfig(
            mapping_id=1,
            mapping_name='Test Mapping',
            organization='TEST_ORG'
        )
        
        # Create datasets
        people_columns = [
            ColumnConfig('name', 'people', 'Person.name', is_anchor=True),
            ColumnConfig('location_id', 'people', 'Person.location', column_type=ColumnType.FOREIGN_KEY)
        ]
        locations_columns = [
            ColumnConfig('id', 'locations', 'Location.id', is_anchor=True),
            ColumnConfig('city', 'locations', 'Location.city')
        ]
        
        config.datasets = [
            DatasetConfig('people', people_columns, primary_key_columns=['name'], dependencies=['locations']),
            DatasetConfig('locations', locations_columns, primary_key_columns=['id'], dependencies=[])
        ]
        
        # Add FK relationship
        config.fk_relationships = [
            FKRelationship(
                source_column='location_id',
                source_dataset='people',
                target_column='id',
                target_dataset='locations',
                relationship_type='lives_in'
            )
        ]
        
        return config

    @pytest.fixture
    def complex_execution_config(self):
        """Create a complex execution configuration with multiple dependencies"""
        config = ExecutionConfig(
            mapping_id=2,
            mapping_name='Complex Mapping',
            organization='TEST_ORG'
        )
        
        # Create datasets: organizations -> departments -> people -> projects
        config.datasets = [
            DatasetConfig('organizations', [], primary_key_columns=['id'], dependencies=[]),
            DatasetConfig('departments', [], primary_key_columns=['id'], dependencies=['organizations']),
            DatasetConfig('people', [], primary_key_columns=['id'], dependencies=['departments']),
            DatasetConfig('projects', [], primary_key_columns=['id'], dependencies=['people', 'organizations'])
        ]
        
        # Add FK relationships
        config.fk_relationships = [
            FKRelationship('dept_id', 'departments', 'id', 'organizations', 'belongs_to'),
            FKRelationship('dept_id', 'people', 'id', 'departments', 'works_in'),
            FKRelationship('person_id', 'projects', 'id', 'people', 'managed_by'),
            FKRelationship('org_id', 'projects', 'id', 'organizations', 'funded_by')
        ]
        
        return config

    @pytest.fixture
    def circular_execution_config(self):
        """Create execution configuration with circular dependencies"""
        config = ExecutionConfig(
            mapping_id=3,
            mapping_name='Circular Mapping',
            organization='TEST_ORG'
        )
        
        config.datasets = [
            DatasetConfig('A', [], dependencies=['B']),
            DatasetConfig('B', [], dependencies=['C']),
            DatasetConfig('C', [], dependencies=['A'])
        ]
        
        config.fk_relationships = [
            FKRelationship('b_id', 'A', 'id', 'B', 'relates_to'),
            FKRelationship('c_id', 'B', 'id', 'C', 'relates_to'),
            FKRelationship('a_id', 'C', 'id', 'A', 'relates_to')
        ]
        
        return config

    def test_resolve_dependencies_simple(self, dependency_resolver, simple_execution_config):
        """Test dependency resolution for simple case"""
        phases = dependency_resolver.resolve_dependencies(simple_execution_config)
        
        assert len(phases) == 2
        
        # First phase should contain locations (no dependencies)
        phase1 = phases[0]
        assert phase1.phase_number == 1
        assert 'locations' in phase1.datasets
        assert len(phase1.datasets) == 1
        
        # Second phase should contain people (depends on locations)
        phase2 = phases[1]
        assert phase2.phase_number == 2
        assert 'people' in phase2.datasets
        assert len(phase2.datasets) == 1

    def test_resolve_dependencies_complex(self, dependency_resolver, complex_execution_config):
        """Test dependency resolution for complex case"""
        phases = dependency_resolver.resolve_dependencies(complex_execution_config)
        
        assert len(phases) >= 3  # At least 3 phases needed
        
        # Phase 1: organizations (no dependencies)
        phase1 = phases[0]
        assert 'organizations' in phase1.datasets
        
        # Phase 2: departments (depends on organizations)
        phase2 = phases[1]
        assert 'departments' in phase2.datasets
        
        # Phase 3: people (depends on departments)
        phase3 = phases[2]
        assert 'people' in phase3.datasets
        
        # Final phase: projects (depends on people and organizations)
        final_phase = phases[-1]
        assert 'projects' in final_phase.datasets

    def test_resolve_dependencies_circular(self, dependency_resolver, circular_execution_config):
        """Test dependency resolution with circular dependencies"""
        phases = dependency_resolver.resolve_dependencies(circular_execution_config)
        
        # Should handle circular dependencies by creating single phase
        assert len(phases) == 1
        phase = phases[0]
        assert len(phase.datasets) == 3
        assert 'A' in phase.datasets
        assert 'B' in phase.datasets
        assert 'C' in phase.datasets
        assert phase.can_parallel is False
        assert phase.estimated_complexity == 'high'

    def test_build_dependency_graph(self, dependency_resolver, simple_execution_config):
        """Test building dependency graph from execution config"""
        graph = dependency_resolver._build_dependency_graph(simple_execution_config)
        
        assert 'people' in graph.nodes
        assert 'locations' in graph.nodes
        assert ('people', 'locations') in graph.edges
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

    def test_build_dependency_graph_complex(self, dependency_resolver, complex_execution_config):
        """Test building complex dependency graph"""
        graph = dependency_resolver._build_dependency_graph(complex_execution_config)
        
        assert len(graph.nodes) == 4
        expected_edges = [
            ('departments', 'organizations'),
            ('people', 'departments'),
            ('projects', 'people'),
            ('projects', 'organizations')
        ]
        
        for edge in expected_edges:
            assert edge in graph.edges

    def test_create_processing_phases_parallel_opportunities(self, dependency_resolver):
        """Test creation of processing phases with parallel processing opportunities"""
        # Create config where multiple datasets can be processed in parallel
        config = ExecutionConfig(mapping_id=1, mapping_name='Test', organization='TEST')
        config.datasets = [
            DatasetConfig('A', [], dependencies=[]),  # No dependencies
            DatasetConfig('B', [], dependencies=[]),  # No dependencies
            DatasetConfig('C', [], dependencies=['A']),  # Depends on A
            DatasetConfig('D', [], dependencies=['B'])   # Depends on B
        ]
        
        # Need to add FK relationships to create the dependencies
        config.fk_relationships = [
            FKRelationship('a_id', 'C', 'id', 'A', 'depends_on'),
            FKRelationship('b_id', 'D', 'id', 'B', 'depends_on')
        ]
        
        phases = dependency_resolver.resolve_dependencies(config)
        
        assert len(phases) == 2
        
        # Phase 1: A and B can be processed in parallel (no dependencies)
        phase1 = phases[0]
        assert len(phase1.datasets) == 2
        assert 'A' in phase1.datasets
        assert 'B' in phase1.datasets
        assert phase1.can_parallel is True
        
        # Phase 2: C and D can be processed in parallel (depend on phase 1)
        phase2 = phases[1]
        assert len(phase2.datasets) == 2
        assert 'C' in phase2.datasets
        assert 'D' in phase2.datasets
        assert phase2.can_parallel is True

    def test_enhance_phases(self, dependency_resolver, simple_execution_config):
        """Test phase enhancement with complexity estimates and names"""
        # Add more complex columns to test complexity calculation
        people_dataset = simple_execution_config.get_dataset_config('people')
        people_dataset.columns.extend([
            ColumnConfig('tags', 'people', 'Person.tags', is_multi_value=True),
            ColumnConfig('orcid', 'people', 'Person.orcid', is_external_ontology=True)
        ])
        
        phases = dependency_resolver.resolve_dependencies(simple_execution_config)
        
        # Check that phases have been enhanced
        for phase in phases:
            assert phase.estimated_complexity in ['low', 'medium', 'high']
            assert phase.phase_name is not None
            assert phase.phase_name != f'Phase {phase.phase_number}'  # Should have better names

    def test_analyze_dependencies(self, dependency_resolver, complex_execution_config):
        """Test dependency analysis"""
        analysis = dependency_resolver.analyze_dependencies(complex_execution_config)
        
        assert 'total_datasets' in analysis
        assert 'total_dependencies' in analysis
        assert 'has_cycles' in analysis
        assert 'independent_datasets' in analysis
        assert 'dependent_datasets' in analysis
        assert 'dependency_chains' in analysis
        assert 'complexity_assessment' in analysis
        
        assert analysis['total_datasets'] == 4
        assert analysis['total_dependencies'] == 4
        assert analysis['has_cycles'] is False
        assert 'organizations' in analysis['independent_datasets']
        assert len(analysis['dependent_datasets']) == 3
        assert analysis['complexity_assessment'] in ['low', 'medium', 'high']

    def test_analyze_dependencies_circular(self, dependency_resolver, circular_execution_config):
        """Test dependency analysis with circular dependencies"""
        analysis = dependency_resolver.analyze_dependencies(circular_execution_config)
        
        assert analysis['has_cycles'] is True
        assert analysis['complexity_assessment'] == 'high'

    def test_find_dependency_chain(self, dependency_resolver, complex_execution_config):
        """Test finding dependency chains"""
        graph = dependency_resolver._build_dependency_graph(complex_execution_config)
        
        # Test longest chain: projects -> people -> departments -> organizations
        chain = dependency_resolver._find_dependency_chain('projects', graph)
        
        assert len(chain) >= 3  # Should include multiple levels
        assert 'projects' in chain
        assert 'organizations' in chain

    def test_get_processing_order_summary(self, dependency_resolver, simple_execution_config):
        """Test processing order summary generation"""
        phases = dependency_resolver.resolve_dependencies(simple_execution_config)
        summary = dependency_resolver.get_processing_order_summary(phases)
        
        assert 'total_phases' in summary
        assert 'total_datasets' in summary
        assert 'parallel_phases' in summary
        assert 'sequential_phases' in summary
        assert 'phase_details' in summary
        assert 'processing_strategy_recommendation' in summary
        
        assert summary['total_phases'] == len(phases)
        assert summary['total_datasets'] == 2
        
        # Check phase details
        phase_details = summary['phase_details']
        assert len(phase_details) == len(phases)
        for detail in phase_details:
            assert 'phase_number' in detail
            assert 'phase_name' in detail
            assert 'datasets' in detail
            assert 'complexity' in detail

    def test_recommend_processing_strategy(self, dependency_resolver):
        """Test processing strategy recommendations"""
        # Test entity_centric recommendation (single phase, few datasets)
        single_phase = [ProcessingPhase(1, 'Single', ['A', 'B'], 'Test', estimated_complexity='low')]
        recommendation = dependency_resolver._recommend_processing_strategy(single_phase)
        assert recommendation == 'entity_centric'
        
        # Test streaming_entity_centric recommendation (two phases, no high complexity)
        two_phases = [
            ProcessingPhase(1, 'Phase1', ['A'], 'Test', estimated_complexity='low'),
            ProcessingPhase(2, 'Phase2', ['B'], 'Test', estimated_complexity='medium')
        ]
        recommendation = dependency_resolver._recommend_processing_strategy(two_phases)
        assert recommendation == 'streaming_entity_centric'
        
        # Test multi_phase recommendation (multiple phases or high complexity)
        complex_phases = [
            ProcessingPhase(1, 'Phase1', ['A'], 'Test', estimated_complexity='high'),
            ProcessingPhase(2, 'Phase2', ['B'], 'Test', estimated_complexity='medium'),
            ProcessingPhase(3, 'Phase3', ['C'], 'Test', estimated_complexity='low')
        ]
        recommendation = dependency_resolver._recommend_processing_strategy(complex_phases)
        assert recommendation == 'multi_phase'

    def test_generate_phase_description(self, dependency_resolver):
        """Test phase description generation"""
        graph = DependencyGraph(
            nodes={'A', 'B', 'C'},
            edges=[('A', 'B'), ('B', 'C')]
        )
        
        # Single dataset with dependencies
        desc = dependency_resolver._generate_phase_description(['A'], graph)
        assert 'Process A' in desc
        assert 'depends on: B' in desc
        
        # Single dataset without dependencies
        desc = dependency_resolver._generate_phase_description(['C'], graph)
        assert 'Process C' in desc
        assert 'no dependencies' in desc
        
        # Multiple datasets
        desc = dependency_resolver._generate_phase_description(['A', 'B'], graph)
        assert 'Process 2 datasets in parallel' in desc
        assert 'A, B' in desc

    def test_get_phase_dependencies(self, dependency_resolver):
        """Test getting phase dependencies"""
        graph = DependencyGraph(
            nodes={'A', 'B', 'C', 'D'},
            edges=[('A', 'B'), ('A', 'C'), ('B', 'D')]
        )
        
        phase = ProcessingPhase(1, 'Test', ['A'], 'Test phase')
        dependencies = dependency_resolver._get_phase_dependencies(phase, graph)
        
        # A depends on B and C
        assert 'B' in dependencies
        assert 'C' in dependencies
        assert len(dependencies) == 2

    def test_handle_circular_dependencies(self, dependency_resolver, circular_execution_config):
        """Test handling of circular dependencies"""
        graph = DependencyGraph(
            nodes={'A', 'B', 'C'},
            edges=[('A', 'B'), ('B', 'C'), ('C', 'A')]
        )
        
        phases = dependency_resolver._handle_circular_dependencies(circular_execution_config, graph)
        
        assert len(phases) == 1
        phase = phases[0]
        assert len(phase.datasets) == 3
        assert phase.can_parallel is False
        assert phase.estimated_complexity == 'high'
        assert 'Circular Dependencies' in phase.phase_name

    def test_edge_cases(self, dependency_resolver):
        """Test edge cases in dependency resolution"""
        # Empty configuration
        empty_config = ExecutionConfig(mapping_id=1, mapping_name='Empty', organization='TEST')
        phases = dependency_resolver.resolve_dependencies(empty_config)
        assert len(phases) == 0
        
        # Single dataset with no dependencies
        single_config = ExecutionConfig(mapping_id=1, mapping_name='Single', organization='TEST')
        single_config.datasets = [DatasetConfig('A', [], dependencies=[])]
        phases = dependency_resolver.resolve_dependencies(single_config)
        assert len(phases) == 1
        assert phases[0].datasets == ['A']
        
        # FK relationships to non-existent datasets (should be ignored)
        config_with_invalid_fk = ExecutionConfig(mapping_id=1, mapping_name='Invalid', organization='TEST')
        config_with_invalid_fk.datasets = [DatasetConfig('A', [], dependencies=[])]
        config_with_invalid_fk.fk_relationships = [
            FKRelationship('col', 'A', 'id', 'nonexistent', 'relates_to')
        ]
        graph = dependency_resolver._build_dependency_graph(config_with_invalid_fk)
        assert len(graph.edges) == 0  # Should ignore FK to non-existent dataset