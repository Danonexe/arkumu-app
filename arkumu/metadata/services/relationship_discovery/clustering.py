"""
Clustering for Relationship Discovery

Contains methods for grouping columns into semantic clusters based on
relationships and feature similarity.
"""

import polars as pl
import numpy as np
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
import logging

from .domain import ColumnRelationship

logger = logging.getLogger(__name__)


def find_data_driven_clusters(df: pl.DataFrame, relationships: List[ColumnRelationship], 
                             clustering_eps: float = 0.3) -> List[List[str]]:
    """Group columns into clusters using data-driven approaches"""
    columns = df.columns
    
    if len(columns) < 2:
        return []
    
    try:
        # Create feature matrix for clustering
        feature_matrix = create_column_feature_matrix(df, relationships)
        
        if feature_matrix is None or len(feature_matrix) < 2:
            return []
        
        # Use DBSCAN clustering
        clustering = DBSCAN(eps=clustering_eps, min_samples=2)
        cluster_labels = clustering.fit_predict(feature_matrix)
        
        # Group columns by cluster
        clusters = defaultdict(list)
        for i, label in enumerate(cluster_labels):
            if label != -1:  # -1 indicates noise/outliers
                clusters[label].append(columns[i])
        
        # Return only clusters with multiple columns
        return [cluster for cluster in clusters.values() if len(cluster) > 1]
        
    except Exception as e:
        logger.warning(f"Error in data-driven clustering: {e}")
        # Fallback to relationship-based clustering
        return fallback_relationship_clustering(df, relationships)


def fallback_relationship_clustering(df: pl.DataFrame, 
                                   relationships: List[ColumnRelationship]) -> List[List[str]]:
    """Fallback clustering based on relationship graph"""
    clusters = []
    clustered_columns = set()
    columns = df.columns
    
    # Build adjacency list from high-confidence relationships
    adjacency = defaultdict(set)
    for rel in relationships:
        if rel.confidence > 0.5:  # High confidence threshold
            adjacency[rel.source_column].add(rel.target_column)
            if rel.bidirectional:
                adjacency[rel.target_column].add(rel.source_column)
    
    # Find connected components (clusters)
    for col in columns:
        if col not in clustered_columns:
            cluster = dfs_cluster(col, adjacency, set())
            if len(cluster) > 1:  # Only include clusters with multiple columns
                clusters.append(list(cluster))
                clustered_columns.update(cluster)
    
    return clusters


def create_column_feature_matrix(df: pl.DataFrame, 
                               relationships: List[ColumnRelationship]) -> Optional[np.ndarray]:
    """Create feature matrix for column clustering"""
    try:
        columns = df.columns
        n_cols = len(columns)
        
        if n_cols < 2:
            return None
        
        # Features: [string_similarity, statistical_measures, data_type_encoding]
        feature_matrix = []
        
        for col in columns:
            features = []
            
            # 1. String-based features (TF-IDF of column name)
            col_tfidf = get_column_name_tfidf(col, columns)
            features.extend(col_tfidf)
            
            # 2. Statistical features
            stats = get_column_statistics(df[col])
            features.extend(stats)
            
            # 3. Data type features
            dtype_features = get_dtype_features(df[col])
            features.extend(dtype_features)
            
            # 4. Relationship features
            rel_features = get_relationship_features(col, relationships)
            features.extend(rel_features)
            
            feature_matrix.append(features)
        
        return np.array(feature_matrix)
        
    except Exception as e:
        logger.warning(f"Error creating feature matrix: {e}")
        return None


def get_column_name_tfidf(col: str, all_columns: List[str]) -> List[float]:
    """Get TF-IDF features for column name"""
    try:
        # Simple character n-gram features
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3), max_features=10)
        tfidf_matrix = vectorizer.fit_transform(all_columns)
        col_idx = all_columns.index(col)
        return tfidf_matrix[col_idx].toarray().flatten().tolist()
    except:
        return [0.0] * 10  # Fallback


def get_column_statistics(series: pl.Series) -> List[float]:
    """Get statistical features for a column"""
    try:
        features = []
        
        # Basic stats
        features.append(len(series))  # Length
        features.append(series.null_count() / len(series) if len(series) > 0 else 0)  # Null ratio
        features.append(len(series.unique()))  # Unique count
        
        # Try numeric stats
        try:
            numeric = series.cast(pl.Float64)
            features.extend([
                numeric.mean() or 0,
                numeric.std() or 0,
                numeric.min() or 0,
                numeric.max() or 0
            ])
        except:
            features.extend([0, 0, 0, 0])  # Non-numeric
        
        return features
    except:
        return [0.0] * 7  # Fallback


def get_dtype_features(series: pl.Series) -> List[float]:
    """Get data type encoding features"""
    dtype_map = {
        'String': [1, 0, 0, 0],
        'Int64': [0, 1, 0, 0],
        'Float64': [0, 0, 1, 0],
        'Boolean': [0, 0, 0, 1]
    }
    return dtype_map.get(str(series.dtype), [0, 0, 0, 0])


def get_relationship_features(col: str, relationships: List[ColumnRelationship]) -> List[float]:
    """Get relationship-based features for a column"""
    features = [0.0] * 4  # [avg_confidence, rel_count, string_sim_count, stat_rel_count]
    
    col_relationships = [r for r in relationships 
                       if r.source_column == col or r.target_column == col]
    
    if col_relationships:
        features[0] = np.mean([r.confidence for r in col_relationships])
        features[1] = len(col_relationships)
        features[2] = len([r for r in col_relationships if r.relationship_type == 'string_similarity'])
        features[3] = len([r for r in col_relationships if r.relationship_type == 'statistical_correlation'])
    
    return features


def dfs_cluster(node: str, adjacency: Dict[str, Set[str]], visited: Set[str]) -> Set[str]:
    """Depth-first search to find connected components"""
    if node in visited:
        return set()
    
    visited.add(node)
    cluster = {node}
    
    for neighbor in adjacency.get(node, set()):
        cluster.update(dfs_cluster(neighbor, adjacency, visited))
    
    return cluster 