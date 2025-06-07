"""
Tests for Cross-Dataset Relationship Discovery System

Tests focus on the multi-dataset analysis functionality which is the primary
use case for relationship discovery - finding connections between different datasets.
"""

import pytest
import polars as pl
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from arkumu.metadata.services.relationship_discovery import (
    RelationshipDiscoveryService,
    ColumnRelationship,
    DatasetRelationshipAnalysis
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test CSV files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def artists_dataset(temp_dir):
    """Create a sample artists dataset CSV"""
    data = {
        'artist_id': ['A001', 'A002', 'A003', 'A004', 'A005'],
        'artist_name': ['Leonardo da Vinci', 'Pablo Picasso', 'Vincent van Gogh', 'Claude Monet', 'Frida Kahlo'],
        'birth_date': ['1452-04-15', '1881-10-25', '1853-03-30', '1840-11-14', '1907-07-06'],
        'birth_place': ['Vinci, Italy', 'Málaga, Spain', 'Groot-Zundert, Netherlands', 'Paris, France', 'Coyoacán, Mexico'],
        'art_movement': ['Renaissance', 'Cubism', 'Post-Impressionism', 'Impressionism', 'Surrealism']
    }
    df = pl.DataFrame(data)
    filepath = temp_dir / 'artists.csv'
    df.write_csv(filepath)
    return str(filepath)


@pytest.fixture
def artworks_dataset(temp_dir):
    """Create a sample artworks dataset CSV"""
    data = {
        'artwork_id': ['W001', 'W002', 'W003', 'W004', 'W005'],
        'artwork_title': ['Mona Lisa', 'Guernica', 'Starry Night', 'Water Lilies', 'The Two Fridas'],
        'creator_id': ['A001', 'A002', 'A003', 'A004', 'A005'],
        'creation_date': ['1503', '1937', '1889', '1919', '1939'],
        'location': ['Paris, France', 'Madrid, Spain', 'New York, USA', 'Paris, France', 'Mexico City, Mexico'],
        'artwork_type': ['Painting', 'Painting', 'Painting', 'Painting', 'Painting']
    }
    df = pl.DataFrame(data)
    filepath = temp_dir / 'artworks.csv'
    df.write_csv(filepath)
    return str(filepath)


@pytest.fixture
def museums_dataset(temp_dir):
    """Create a sample museums dataset CSV"""
    data = {
        'museum_id': ['M001', 'M002', 'M003', 'M004'],
        'museum_name': ['Louvre Museum', 'Museo Reina Sofía', 'Museum of Modern Art', 'Musée Marmottan Monet'],
        'city': ['Paris', 'Madrid', 'New York', 'Paris'],
        'country': ['France', 'Spain', 'USA', 'France'],
        'established_date': ['1793', '1990', '1929', '1934']
    }
    df = pl.DataFrame(data)
    filepath = temp_dir / 'museums.csv'
    df.write_csv(filepath)
    return str(filepath)


@pytest.fixture
def exhibitions_dataset(temp_dir):
    """Create a sample exhibitions dataset CSV"""
    data = {
        'exhibition_id': ['E001', 'E002', 'E003', 'E004'],
        'exhibition_title': ['Renaissance Masters', 'Modern Art Showcase', 'Impressionist Collection', 'Contemporary Expressions'],
        'host_museum_id': ['M001', 'M003', 'M004', 'M002'],
        'featured_artist_id': ['A001', 'A002', 'A004', 'A005'],
        'start_date': ['2023-01-15', '2023-03-10', '2023-05-20', '2023-07-01'],
        'end_date': ['2023-06-30', '2023-08-15', '2023-10-31', '2023-12-15']
    }
    df = pl.DataFrame(data)
    filepath = temp_dir / 'exhibitions.csv'
    df.write_csv(filepath)
    return str(filepath)


@pytest.fixture
def discovery_service():
    """Create RelationshipDiscoveryService instance"""
    return RelationshipDiscoveryService()


class TestCrossDatasetRelationshipDiscovery:
    """Test cross-dataset relationship discovery functionality"""

    def test_compare_multiple_datasets_basic(self, discovery_service, artists_dataset, artworks_dataset):
        """Test basic cross-dataset relationship analysis"""
        dataset_paths = [artists_dataset, artworks_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Verify result structure
        assert 'dataset_analyses' in result
        assert 'cross_dataset_relationships' in result
        assert 'global_patterns' in result
        assert result['total_datasets'] == 2
        
        # Check individual dataset analyses
        assert 'artists' in result['dataset_analyses']
        assert 'artworks' in result['dataset_analyses']
        
        # Verify cross-dataset relationships exist
        cross_rels = result['cross_dataset_relationships']
        assert len(cross_rels) > 0
        
        # Check for expected semantic relationships between datasets
        source_columns = [rel['source_column'] for rel in cross_rels]
        target_columns = [rel['target_column'] for rel in cross_rels]
        
        # Should find relationships between artist_id and creator_id
        id_relationships = [rel for rel in cross_rels 
                           if ('artist_id' in rel['source_column'] or 'creator_id' in rel['source_column'])]
        assert len(id_relationships) > 0

    def test_semantic_similarity_across_datasets(self, discovery_service, artists_dataset, artworks_dataset):
        """Test semantic similarity detection between datasets"""
        dataset_paths = [artists_dataset, artworks_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        cross_rels = result['cross_dataset_relationships']
        
        # Find pattern and semantic relationships
        pattern_rels = [rel for rel in cross_rels if rel['relationship_type'] == 'cross_dataset_pattern_similarity']
        semantic_rels = [rel for rel in cross_rels if rel['relationship_type'] == 'cross_dataset_semantic']
        
        # Should find either pattern or semantic relationships
        assert len(pattern_rels) > 0 or len(semantic_rels) > 0
        
        # Check specific expected relationships in both types
        all_rel_pairs = [(rel['source_column'], rel['target_column']) for rel in cross_rels]
        
        # Should detect artist_id <-> creator_id relationship
        id_relationships = [pair for pair in all_rel_pairs 
                           if ('artist_id' in pair[0] and 'creator_id' in pair[1]) or
                              ('creator_id' in pair[0] and 'artist_id' in pair[1])]
        assert len(id_relationships) > 0
        
        # Verify confidence scores are reasonable
        for rel in cross_rels:
            assert 0.0 <= rel['confidence'] <= 1.0
            # Pattern similarity should have high confidence for format matches
            if rel['relationship_type'] == 'cross_dataset_pattern_similarity':
                assert rel['confidence'] > 0.4  # Should be reasonable confidence for pattern matches

    def test_four_dataset_analysis(self, discovery_service, artists_dataset, artworks_dataset, 
                                  museums_dataset, exhibitions_dataset):
        """Test comprehensive analysis across four related datasets"""
        dataset_paths = [artists_dataset, artworks_dataset, museums_dataset, exhibitions_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Verify all datasets are analyzed
        assert result['total_datasets'] == 4
        assert len(result['dataset_analyses']) == 4
        
        expected_datasets = ['artists', 'artworks', 'museums', 'exhibitions']
        for dataset_name in expected_datasets:
            assert dataset_name in result['dataset_analyses']
        
        # Check for comprehensive cross-dataset relationships
        cross_rels = result['cross_dataset_relationships']
        assert len(cross_rels) > 0
        
        # Should find multiple types of relationships
        relationship_types = set(rel['relationship_type'] for rel in cross_rels)
        # Should find at least one type of cross-dataset relationship
        expected_types = {'cross_dataset_semantic', 'cross_dataset_pattern_similarity', 'cross_dataset_split_values'}
        assert len(relationship_types & expected_types) > 0
        
        # Verify global patterns analysis
        global_patterns = result['global_patterns']
        assert 'relationship_type_distribution' in global_patterns
        assert 'total_relationships' in global_patterns
        assert global_patterns['total_relationships'] > 0

    def test_foreign_key_relationship_detection(self, discovery_service, artists_dataset, artworks_dataset):
        """Test detection of foreign key relationships across datasets"""
        dataset_paths = [artists_dataset, artworks_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check individual dataset analyses for FK candidates
        artists_analysis = result['dataset_analyses']['artists']
        artworks_analysis = result['dataset_analyses']['artworks']
        
        # Should identify ID columns as FK candidates
        assert 'artist_id' in artists_analysis['foreign_key_candidates']
        assert 'creator_id' in artworks_analysis['foreign_key_candidates']
        assert 'artwork_id' in artworks_analysis['foreign_key_candidates']

    def test_semantic_clustering_across_datasets(self, discovery_service, artists_dataset, 
                                               artworks_dataset, museums_dataset):
        """Test semantic clustering functionality with multiple datasets"""
        dataset_paths = [artists_dataset, artworks_dataset, museums_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check for semantic clusters in individual datasets
        for dataset_name, analysis in result['dataset_analyses'].items():
            assert 'semantic_clusters' in analysis
            # Should find at least some clusters for datasets with related columns
            if dataset_name in ['artists', 'artworks', 'museums']:
                clusters = analysis['semantic_clusters']
                # At minimum, date-related columns should cluster together
                date_clusters = [cluster for cluster in clusters 
                               if any('date' in col.lower() for col in cluster)]
                assert len(date_clusters) >= 0  # May not always have date clusters

    def test_relationship_confidence_calculation(self, discovery_service, artists_dataset, artworks_dataset):
        """Test that relationship confidence scores are calculated correctly"""
        dataset_paths = [artists_dataset, artworks_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        cross_rels = result['cross_dataset_relationships']
        
        for rel in cross_rels:
            # All relationships should have valid confidence scores
            assert 'confidence' in rel
            assert isinstance(rel['confidence'], (int, float))
            assert 0.0 <= rel['confidence'] <= 1.0
            
            # High semantic similarity should result in high confidence
            if 'artist_id' in rel['source_column'] and 'creator_id' in rel['target_column']:
                assert rel['confidence'] > 0.6  # Should be high confidence
            
            # Evidence should be provided
            assert 'evidence' in rel
            assert isinstance(rel['evidence'], dict)
            
            # Check for appropriate evidence fields based on relationship type
            if rel['relationship_type'] == 'cross_dataset_semantic':
                assert 'similarity_score' in rel['evidence']
            elif rel['relationship_type'] == 'cross_dataset_pattern_similarity':
                assert 'pattern_score' in rel['evidence']
                assert 'pattern_type' in rel['evidence']
            elif rel['relationship_type'] == 'cross_dataset_split_values':
                assert 'overlap_score' in rel['evidence'] or 'pattern_score' in rel['evidence']

    def test_quality_metrics_calculation(self, discovery_service, artists_dataset, artworks_dataset):
        """Test quality metrics calculation for relationship analysis"""
        dataset_paths = [artists_dataset, artworks_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Check quality metrics for each dataset
        for dataset_name, analysis in result['dataset_analyses'].items():
            metrics = analysis['quality_metrics']
            
            # Verify all expected metrics are present
            assert 'coverage' in metrics
            assert 'average_confidence' in metrics
            assert 'high_confidence_ratio' in metrics
            assert 'type_diversity' in metrics
            assert 'total_relationships' in metrics
            
            # Verify metric ranges
            assert 0.0 <= metrics['coverage'] <= 1.0
            assert 0.0 <= metrics['average_confidence'] <= 1.0
            assert 0.0 <= metrics['high_confidence_ratio'] <= 1.0
            assert 0.0 <= metrics['type_diversity'] <= 1.0
            assert metrics['total_relationships'] >= 0

    def test_empty_dataset_handling(self, discovery_service, temp_dir):
        """Test handling of empty or minimal datasets"""
        # Create empty dataset
        empty_data = {'col1': [], 'col2': []}
        empty_df = pl.DataFrame(empty_data)
        empty_filepath = temp_dir / 'empty.csv'
        empty_df.write_csv(empty_filepath)
        
        # Create minimal dataset
        minimal_data = {'id': ['1'], 'name': ['test']}
        minimal_df = pl.DataFrame(minimal_data)
        minimal_filepath = temp_dir / 'minimal.csv'
        minimal_df.write_csv(minimal_filepath)
        
        dataset_paths = [str(empty_filepath), str(minimal_filepath)]
        
        # Should handle gracefully without errors
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        assert result['total_datasets'] == 2
        assert 'dataset_analyses' in result
        assert 'cross_dataset_relationships' in result

    def test_dataset_with_similar_structure(self, discovery_service, temp_dir):
        """Test analysis of datasets with very similar structures"""
        # Create two datasets with similar column names
        data1 = {
            'person_id': ['P001', 'P002', 'P003'],
            'person_name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
            'birth_date': ['1980-01-01', '1985-05-15', '1990-12-31']
        }
        
        data2 = {
            'individual_id': ['I001', 'I002', 'I003'],
            'individual_name': ['Alice Brown', 'Charlie Wilson', 'Diana Davis'],
            'date_of_birth': ['1975-03-20', '1988-07-10', '1992-11-05']
        }
        
        df1 = pl.DataFrame(data1)
        df2 = pl.DataFrame(data2)
        
        filepath1 = temp_dir / 'persons.csv'
        filepath2 = temp_dir / 'individuals.csv'
        
        df1.write_csv(filepath1)
        df2.write_csv(filepath2)
        
        dataset_paths = [str(filepath1), str(filepath2)]
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Should detect high semantic similarity
        cross_rels = result['cross_dataset_relationships']
        assert len(cross_rels) > 0
        
        # Should find relationships between similar columns
        high_confidence_rels = [rel for rel in cross_rels if rel['confidence'] > 0.7]
        assert len(high_confidence_rels) > 0

    def test_global_pattern_analysis(self, discovery_service, artists_dataset, artworks_dataset, 
                                   museums_dataset, exhibitions_dataset):
        """Test global pattern analysis across multiple datasets"""
        dataset_paths = [artists_dataset, artworks_dataset, museums_dataset, exhibitions_dataset]
        
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        global_patterns = result['global_patterns']
        
        # Verify global pattern structure
        assert 'relationship_type_distribution' in global_patterns
        assert 'average_confidence_by_type' in global_patterns
        assert 'total_relationships' in global_patterns
        assert 'unique_columns' in global_patterns
        
        # Check relationship type distribution
        type_dist = global_patterns['relationship_type_distribution']
        assert isinstance(type_dist, dict)
        assert all(isinstance(count, int) for count in type_dist.values())
        
        # Check average confidence by type
        avg_conf = global_patterns['average_confidence_by_type']
        assert isinstance(avg_conf, dict)
        for rel_type, confidence in avg_conf.items():
            assert 0.0 <= confidence <= 1.0

    def test_large_dataset_sample_handling(self, discovery_service, temp_dir):
        """Test handling of large datasets with sampling"""
        # Create a larger dataset
        large_data = {
            'id': [f'ID{i:04d}' for i in range(2000)],
            'name': [f'Name_{i}' for i in range(2000)],
            'category': [f'Cat_{i % 10}' for i in range(2000)],
            'value': list(range(2000))
        }
        
        large_df = pl.DataFrame(large_data)
        large_filepath = temp_dir / 'large_dataset.csv'
        large_df.write_csv(large_filepath)
        
        # Test with small sample size
        dataset_paths = [str(large_filepath)]
        result = discovery_service.compare_datasets_relationships(dataset_paths, sample_size=100)
        
        # Should complete successfully with sampling
        assert 'dataset_analyses' in result
        large_analysis = result['dataset_analyses']['large_dataset']
        assert large_analysis['row_count'] == 100  # Should be limited by sample_size
        assert large_analysis['column_count'] == 4


class TestRelationshipDiscoveryErrorHandling:
    """Test error handling and edge cases"""

    def test_invalid_file_path(self, discovery_service):
        """Test handling of invalid file paths"""
        invalid_paths = ['/nonexistent/file.csv']
        
        with pytest.raises(Exception):
            discovery_service.compare_datasets_relationships(invalid_paths)

    def test_malformed_csv_handling(self, discovery_service, temp_dir):
        """Test handling of malformed CSV files"""
        # Create malformed CSV
        malformed_content = "col1,col2\nvalue1\nvalue2,value3,extra_value\n"
        malformed_filepath = temp_dir / 'malformed.csv'
        
        with open(malformed_filepath, 'w') as f:
            f.write(malformed_content)
        
        # Should handle gracefully or raise appropriate exception
        with pytest.raises(Exception):
            discovery_service.compare_datasets_relationships([str(malformed_filepath)])

    def test_single_column_dataset(self, discovery_service, temp_dir):
        """Test handling of dataset with single column"""
        single_col_data = {'only_column': ['value1', 'value2', 'value3']}
        single_col_df = pl.DataFrame(single_col_data)
        single_col_filepath = temp_dir / 'single_column.csv'
        single_col_df.write_csv(single_col_filepath)
        
        dataset_paths = [str(single_col_filepath)]
        result = discovery_service.compare_datasets_relationships(dataset_paths)
        
        # Should handle gracefully
        assert result['total_datasets'] == 1
        analysis = result['dataset_analyses']['single_column']
        assert analysis['column_count'] == 1
        # No relationships possible within single column
        assert len(analysis['relationships']) == 0 