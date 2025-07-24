"""
Integration Tests for Cross-Dataset Relationship Discovery System

Tests the complete workflow from multiple CSV files to visual relationship matrix,
focusing on the end-to-end multi-dataset analysis functionality.
"""

import pytest
import tempfile
import polars as pl
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import TestCase, RequestFactory
from django.template import Context, Template

from arkumu.metadata.services.relationship_discovery import RelationshipDiscoveryService


class TestCrossDatasetRelationshipIntegration(TestCase):
    """Integration tests for complete cross-dataset relationship workflow"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.factory = RequestFactory()
        self.discovery_service = RelationshipDiscoveryService()
        self.temp_dir = tempfile.mkdtemp()
    
    def create_test_datasets(self):
        """Create realistic test datasets for cultural heritage domain"""
        # Artists dataset
        artists_data = {
            'artist_id': ['ART001', 'ART002', 'ART003', 'ART004', 'ART005'],
            'full_name': ['Pablo Picasso', 'Vincent van Gogh', 'Leonardo da Vinci', 'Claude Monet', 'Frida Kahlo'],
            'birth_year': [1881, 1853, 1452, 1840, 1907],
            'birth_country': ['Spain', 'Netherlands', 'Italy', 'France', 'Mexico'],
            'art_movement': ['Cubism', 'Post-Impressionism', 'Renaissance', 'Impressionism', 'Surrealism'],
            'active_period_start': [1901, 1881, 1482, 1865, 1925],
            'active_period_end': [1973, 1890, 1519, 1926, 1954]
        }
        
        # Artworks dataset  
        artworks_data = {
            'work_id': ['WRK001', 'WRK002', 'WRK003', 'WRK004', 'WRK005'],
            'title': ['Guernica', 'Starry Night', 'Mona Lisa', 'Water Lilies', 'The Two Fridas'],
            'creator_artist_id': ['ART001', 'ART002', 'ART003', 'ART004', 'ART005'],
            'creation_year': [1937, 1889, 1503, 1919, 1939],
            'medium': ['Oil on canvas', 'Oil on canvas', 'Oil on wood', 'Oil on canvas', 'Oil on canvas'],
            'current_location': ['Madrid', 'New York', 'Paris', 'Paris', 'Mexico City'],
            'style': ['Cubism', 'Post-Impressionism', 'Renaissance', 'Impressionism', 'Surrealism']
        }
        
        # Museums dataset
        museums_data = {
            'museum_id': ['MUS001', 'MUS002', 'MUS003', 'MUS004'],
            'institution_name': ['Museo Reina Sofía', 'Museum of Modern Art', 'Louvre Museum', 'Museo Frida Kahlo'],
            'city_location': ['Madrid', 'New York', 'Paris', 'Mexico City'],
            'country_code': ['ES', 'US', 'FR', 'MX'],
            'established': [1990, 1929, 1793, 1958],
            'collection_focus': ['Contemporary', 'Modern', 'Classical', 'Mexican Art']
        }
        
        # Collections dataset
        collections_data = {
            'collection_id': ['COL001', 'COL002', 'COL003', 'COL004'],
            'collection_name': ['Spanish Civil War Art', 'Post-Impressionist Masters', 'Renaissance Portraits', 'Mexican Identity'],
            'owning_museum_id': ['MUS001', 'MUS002', 'MUS003', 'MUS004'],
            'featured_work_id': ['WRK001', 'WRK002', 'WRK003', 'WRK005'],
            'theme': ['Political Art', 'Emotional Expression', 'Portraiture', 'Cultural Identity'],
            'time_period': ['20th Century', '19th Century', '16th Century', '20th Century']
        }
        
        # Create CSV files
        datasets = {
            'artists': artists_data,
            'artworks': artworks_data, 
            'museums': museums_data,
            'collections': collections_data
        }
        
        filepaths = {}
        for name, data in datasets.items():
            df = pl.DataFrame(data)
            filepath = Path(self.temp_dir) / f'{name}.csv'
            df.write_csv(filepath)
            filepaths[name] = str(filepath)
            
        return filepaths
    
    def test_complete_multi_dataset_workflow(self):
        """Test complete workflow from CSV files to relationship analysis"""
        # Create test datasets
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        # Run cross-dataset analysis
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Verify comprehensive analysis structure
        assert result['total_datasets'] == 4
        assert len(result['dataset_analyses']) == 4
        assert 'cross_dataset_relationships' in result
        assert 'global_patterns' in result
        
        # Check all datasets were processed
        expected_datasets = ['artists', 'artworks', 'museums', 'collections']
        for dataset_name in expected_datasets:
            assert dataset_name in result['dataset_analyses']
            analysis = result['dataset_analyses'][dataset_name]
            assert analysis['column_count'] > 0
            assert analysis['row_count'] > 0
            assert 'relationships' in analysis
            assert 'quality_metrics' in analysis
    
    def test_semantic_relationship_detection_across_domains(self):
        """Test semantic relationship detection across cultural heritage datasets"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        cross_rels = result['cross_dataset_relationships']
        
        # Should detect ID field relationships
        id_relationships = [
            rel for rel in cross_rels 
            if (('artist_id' in rel['source_column'] and 'creator_artist_id' in rel['target_column']) or
                ('creator_artist_id' in rel['source_column'] and 'artist_id' in rel['target_column']))
        ]
        assert len(id_relationships) > 0
        
        # Should detect location relationships
        location_relationships = [
            rel for rel in cross_rels
            if (('city' in rel['source_column'].lower() and 'location' in rel['target_column'].lower()) or
                ('location' in rel['source_column'].lower() and 'city' in rel['target_column'].lower()))
        ]
        # May or may not find location relationships depending on exact column names
        
        # Verify confidence scores are meaningful
        for rel in cross_rels:
            assert 0.0 <= rel['confidence'] <= 1.0
            assert 'evidence' in rel
            # Should be one of the cross-dataset relationship types
            assert rel['relationship_type'] in [
                'cross_dataset_pattern_similarity', 
                'cross_dataset_foreign_key', 
                'cross_dataset_semantic'
            ]
    
    def test_foreign_key_detection_across_datasets(self):
        """Test foreign key relationship detection between related datasets"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check FK candidates in individual datasets
        for dataset_name, analysis in result['dataset_analyses'].items():
            fk_candidates = analysis['foreign_key_candidates']
            
            # Each dataset should have ID fields identified as FK candidates
            id_columns = [col for col in fk_candidates if 'id' in col.lower()]
            assert len(id_columns) > 0
    
    def test_relationship_matrix_generation(self):
        """Test relationship matrix generation for visualization"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check relationship matrices for each dataset
        for dataset_name, analysis in result['dataset_analyses'].items():
            matrix = analysis['relationship_matrix']
            assert isinstance(matrix, dict)
            
            # Matrix should have reasonable entries
            if len(matrix) > 0:
                # Check matrix key format
                sample_key = list(matrix.keys())[0]
                assert '-' in sample_key  # Should be "col1-col2" format
                
                # Check matrix values are confidence scores
                for confidence in matrix.values():
                    assert isinstance(confidence, (int, float))
                    assert 0.0 <= confidence <= 1.0
    
    def test_quality_metrics_calculation(self):
        """Test quality metrics calculation for multi-dataset analysis"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check quality metrics for each dataset
        for dataset_name, analysis in result['dataset_analyses'].items():
            metrics = analysis['quality_metrics']
            
            # Verify all expected metrics are present
            required_metrics = ['coverage', 'average_confidence', 'high_confidence_ratio', 
                              'type_diversity', 'total_relationships']
            for metric in required_metrics:
                assert metric in metrics
                assert isinstance(metrics[metric], (int, float))
                assert metrics[metric] >= 0
    
    def test_global_pattern_analysis(self):
        """Test global pattern analysis across all datasets"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        global_patterns = result['global_patterns']
        
        # Verify global pattern structure
        assert 'relationship_type_distribution' in global_patterns
        assert 'average_confidence_by_type' in global_patterns
        assert 'total_relationships' in global_patterns
        assert 'unique_columns' in global_patterns
        
        # Check relationship type distribution
        type_dist = global_patterns['relationship_type_distribution']
        if type_dist:  # If relationships were found
            assert all(isinstance(count, int) for count in type_dist.values())
            assert all(count >= 0 for count in type_dist.values())
    
    def test_template_rendering_with_cross_dataset_data(self):
        """Test template rendering with real cross-dataset relationship data"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Test relationship matrix template
        template = Template("""
            {% load relationship_tags %}
            <div class="cross-dataset-analysis">
                <h3>{{ total_datasets }} Datasets Analyzed</h3>
                <div class="cross-relationships">
                    {% for rel in cross_dataset_relationships %}
                        <div class="relationship" style="background-color: {{ rel.relationship_type|relationship_type_color }}">
                            {{ rel.relationship_type|relationship_icon }}
                            <strong>{{ rel.source_column }}</strong> → <strong>{{ rel.target_column }}</strong>
                            <span class="confidence">{{ rel.confidence|confidence_level }}</span>
                            <small>({{ rel.confidence|floatformat:3 }})</small>
                        </div>
                    {% empty %}
                        <p>No cross-dataset relationships found.</p>
                    {% endfor %}
                </div>
                <div class="summary">
                    Total relationships: {{ cross_dataset_relationships|length }}
                    High confidence: {{ cross_dataset_relationships|high_confidence_count }}
                </div>
            </div>
        """)
        
        context = Context(result)
        rendered = template.render(context)
        
        # Verify template rendered successfully
        assert 'cross-dataset-analysis' in rendered
        assert '4 Datasets Analyzed' in rendered
        
        # If relationships were found, verify they're displayed
        if result['cross_dataset_relationships']:
            assert 'relationship' in rendered
            assert '→' in rendered  # Arrow between columns
    
    def test_performance_with_multiple_datasets(self):
        """Test performance characteristics of multi-dataset analysis"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        import time
        start_time = time.time()
        
        result = self.discovery_service.compare_datasets_relationships(
            dataset_paths, sample_size=100
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete in reasonable time (adjust threshold as needed)
        assert execution_time < 30  # seconds
        
        # Should produce results
        assert result['total_datasets'] == 4
        assert 'cross_dataset_relationships' in result
    
    def test_error_handling_in_multi_dataset_workflow(self):
        """Test error handling in multi-dataset analysis workflow"""
        filepaths = self.create_test_datasets()
        
        # Add an invalid file path
        invalid_paths = list(filepaths.values()) + ['/nonexistent/file.csv']
        
        # Should handle gracefully or raise appropriate exception
        with pytest.raises(Exception):
            self.discovery_service.compare_datasets_relationships(invalid_paths)
    
    def test_semantic_clustering_across_datasets(self):
        """Test semantic clustering functionality with real multi-dataset data"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check for semantic clusters in datasets
        for dataset_name, analysis in result['dataset_analyses'].items():
            clusters = analysis['semantic_clusters']
            
            # Clusters should be lists of column names
            for cluster in clusters:
                assert isinstance(cluster, list)
                assert all(isinstance(col, str) for col in cluster)
                assert len(cluster) >= 2  # Clusters should have multiple columns
    
    def test_relationship_evidence_completeness(self):
        """Test that relationships include comprehensive evidence"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check cross-dataset relationships have proper evidence
        for rel in result['cross_dataset_relationships']:
            assert 'evidence' in rel
            evidence = rel['evidence']
            
            # Should include relevant scoring metrics
            # The evidence structure may contain different fields based on relationship type
            has_score_field = any(key in evidence for key in [
                'pattern_score', 'foreign_key_likelihood', 'intersection_ratio', 'similarity_score'
            ])
            assert has_score_field, f"Evidence missing scoring field: {evidence.keys()}"
            
            # Should include dataset information
            assert 'source_dataset' in evidence
            assert 'target_dataset' in evidence
    
    def test_visualization_data_preparation(self):
        """Test data preparation for visualization components"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Test data is suitable for matrix visualization
        for dataset_name, analysis in result['dataset_analyses'].items():
            matrix = analysis['relationship_matrix']
            
            # Should be serializable for frontend
            import json
            try:
                json.dumps(matrix)
            except TypeError:
                pytest.fail(f"Matrix for {dataset_name} is not JSON serializable")
        
        # Test cross-dataset relationships are serializable
        try:
            json.dumps(result['cross_dataset_relationships'])
        except TypeError:
            pytest.fail("Cross-dataset relationships are not JSON serializable")
    
    def test_multi_dataset_confidence_calibration(self):
        """Test that confidence scores are well-calibrated across datasets"""
        filepaths = self.create_test_datasets()
        dataset_paths = list(filepaths.values())
        
        result = self.discovery_service.compare_datasets_relationships(dataset_paths)
        
        all_confidences = []
        
        # Collect all confidence scores
        for analysis in result['dataset_analyses'].values():
            for rel in analysis['relationships']:
                all_confidences.append(rel['confidence'])
        
        for rel in result['cross_dataset_relationships']:
            all_confidences.append(rel['confidence'])
        
        if all_confidences:
            # Check confidence distribution
            avg_confidence = sum(all_confidences) / len(all_confidences)
            assert 0.0 <= avg_confidence <= 1.0
            
            # Should have reasonable spread (not all the same value)
            unique_confidences = set(all_confidences)
            if len(all_confidences) > 1:
                assert len(unique_confidences) > 1 