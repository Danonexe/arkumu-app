"""
Relationship Discovery Service

Main service class that orchestrates the relationship discovery process
by delegating to specialized modules for different types of analysis.
"""

import polars as pl
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path
import logging

from .domain import DatasetRelationshipAnalysis
from .utils import (
    create_relationship_matrix, identify_foreign_key_candidates,
    calculate_quality_metrics, analyze_global_patterns,
    relationship_to_dict, analysis_to_dict
)
from .intra_dataset import (
    find_string_similarity_relationships, find_statistical_relationships,
    find_information_theory_relationships, find_distribution_similarity_relationships,
    find_value_overlap_relationships, find_pattern_relationships,
    find_foreign_key_relationships
)
from .cross_dataset import find_cross_dataset_relationships
from .clustering import find_data_driven_clusters

logger = logging.getLogger(__name__)


class RelationshipDiscoveryService:
    """
    Service for discovering potential relationships between columns within
    and across datasets to provide users with semantic guidance.
    """
    
    def __init__(self, table_analysis_service=None):
        """
        Initialize with optional table analysis service for enhanced analysis
        
        Args:
            table_analysis_service: Optional TableAnalysisService instance
        """
        self.table_analysis = table_analysis_service
        
        # Data-driven parameters (learned from data rather than hardcoded)
        self.min_similarity_threshold = 0.2  # Lowered for better detection
        self.min_mutual_information = 0.05   # Lowered for small datasets
        self.clustering_eps = 0.3            # Reduced for tighter clusters

    def analyze_dataset_relationships(self, dataset_path: str, sample_size: int = 1000) -> DatasetRelationshipAnalysis:
        """
        Analyze potential relationships within a single dataset
        
        Args:
            dataset_path: Path to CSV file
            sample_size: Number of rows to analyze
            
        Returns:
            DatasetRelationshipAnalysis with discovered relationships
        """
        try:
            # Read dataset
            df = pl.read_csv(dataset_path, n_rows=sample_size)
            dataset_name = dataset_path.split('/')[-1].replace('.csv', '')
            
            logger.info(f"Analyzing relationships in dataset '{dataset_name}' ({len(df)} rows, {len(df.columns)} columns)")
            
            # Get table analysis if service is available
            table_analysis = None
            if self.table_analysis:
                try:
                    table_analysis = self.table_analysis.analyze_csv(dataset_path, sample_size)
                except Exception as e:
                    logger.warning(f"Table analysis failed: {e}")
            
            # Discover relationships using data-driven approaches
            relationships = []
            
            # 1. String similarity relationships (data-driven)
            string_relationships = find_string_similarity_relationships(df, self.min_similarity_threshold)
            relationships.extend(string_relationships)
            
            # 2. Statistical correlation relationships
            correlation_relationships = find_statistical_relationships(df)
            relationships.extend(correlation_relationships)
            
            # 3. Information theory relationships
            information_relationships = find_information_theory_relationships(df, self.min_mutual_information)
            relationships.extend(information_relationships)
            
            # 4. Distribution similarity relationships
            distribution_relationships = find_distribution_similarity_relationships(df)
            relationships.extend(distribution_relationships)

            # 5. Value overlap relationships
            value_overlap_relationships = find_value_overlap_relationships(df)
            relationships.extend(value_overlap_relationships)

            # 6. Pattern relationships (requires table analysis)
            pattern_relationships = find_pattern_relationships(df, table_analysis)
            relationships.extend(pattern_relationships)

            # 7. Foreign key relationships
            fk_relationships = find_foreign_key_relationships(df, table_analysis)
            relationships.extend(fk_relationships)
            
            # Create relationship matrix
            relationship_matrix = create_relationship_matrix(df.columns, relationships)
            
            # Find data-driven clusters
            semantic_clusters = find_data_driven_clusters(df, relationships, self.clustering_eps)
            
            # Identify foreign key candidates
            foreign_key_candidates = identify_foreign_key_candidates(df, relationships)
            
            # Calculate quality metrics
            quality_metrics = calculate_quality_metrics(df, relationships)
            
            return DatasetRelationshipAnalysis(
                dataset_name=dataset_name,
                column_count=len(df.columns),
                row_count=len(df),
                column_names=list(df.columns),
                relationships=relationships,
                relationship_matrix=relationship_matrix,
                semantic_clusters=semantic_clusters,
                foreign_key_candidates=foreign_key_candidates,
                quality_metrics=quality_metrics
            )
            
        except Exception as e:
            logger.error(f"Error analyzing dataset relationships: {e}")
            raise

    def compare_datasets_relationships(self, dataset_paths: List[str], 
                                     sample_size: int = 500) -> Dict[str, Any]:
        """
        Compare relationships across multiple datasets to find cross-dataset connections
        
        Args:
            dataset_paths: List of CSV file paths
            sample_size: Number of rows to analyze per dataset
            
        Returns:
            Dictionary with cross-dataset relationship analysis
        """
        try:
            dataset_analyses = {}
            all_columns = set()
            cross_dataset_relationships = []
            
            # Store dataset paths for cross-dataset value analysis
            current_dataset_paths = {
                Path(dataset_path).stem: dataset_path for dataset_path in dataset_paths
            }
            
            # Analyze each dataset individually
            for dataset_path in dataset_paths:
                analysis = self.analyze_dataset_relationships(dataset_path, sample_size)
                dataset_analyses[analysis.dataset_name] = analysis
                # Add columns from this dataset to the global set
                df = pl.read_csv(dataset_path, n_rows=sample_size)
                all_columns.update(df.columns)
            
            # Find cross-dataset relationships
            for dataset1, analysis1 in dataset_analyses.items():
                for dataset2, analysis2 in dataset_analyses.items():
                    if dataset1 != dataset2:
                        cross_relationships = find_cross_dataset_relationships(
                            dataset1, analysis1, dataset2, analysis2, current_dataset_paths
                        )
                        cross_dataset_relationships.extend(cross_relationships)
            
            # Analyze global patterns
            global_patterns = analyze_global_patterns(dataset_analyses)
            
            return {
                'dataset_analyses': {name: analysis_to_dict(analysis) 
                                   for name, analysis in dataset_analyses.items()},
                'cross_dataset_relationships': [relationship_to_dict(rel) 
                                              for rel in cross_dataset_relationships],
                'global_patterns': global_patterns,
                'total_datasets': len(dataset_paths),
                'total_columns': len(all_columns),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error comparing datasets: {e}")
            raise 