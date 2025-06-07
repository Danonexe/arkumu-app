"""
Intra-Dataset Relationship Analysis

Contains methods for discovering potential relationships between columns
within a single dataset using various data-driven approaches.
"""

import polars as pl
import re
import math
import numpy as np
from typing import Dict, List, Any, Optional
from collections import defaultdict
from itertools import combinations
from scipy.stats import chi2_contingency, pearsonr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

from .domain import ColumnRelationship
from .utils import (
    levenshtein_distance, calculate_mutual_information, calculate_entropy,
    calculate_distribution_stats, calculate_stats_similarity,
    compare_categorical_distributions, suggest_predicate
)

logger = logging.getLogger(__name__)


def find_string_similarity_relationships(df: pl.DataFrame, min_similarity_threshold: float = 0.2) -> List[ColumnRelationship]:
    """Find relationships based on data-driven string similarity of column names"""
    relationships = []
    columns = df.columns
    
    if len(columns) < 2:
        return relationships
    
    # Create TF-IDF vectors for column names (character-level n-grams)
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 4), lowercase=True)
    try:
        tfidf_matrix = vectorizer.fit_transform(columns)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Find column pairs with high similarity
        for i, col1 in enumerate(columns):
            for j, col2 in enumerate(columns):
                if i < j:  # Avoid duplicates
                    similarity = similarity_matrix[i, j]
                    
                    if similarity > min_similarity_threshold:
                        # Calculate additional string metrics
                        edit_distance = levenshtein_distance(col1, col2)
                        max_len = max(len(col1), len(col2))
                        normalized_edit = 1 - (edit_distance / max_len) if max_len > 0 else 0
                        
                        # Combined confidence score
                        confidence = (similarity + normalized_edit) / 2
                        
                        relationship = ColumnRelationship(
                            source_column=col1,
                            target_column=col2,
                            relationship_type='string_similarity',
                            confidence=confidence,
                            evidence={
                                'tfidf_similarity': similarity,
                                'edit_distance_normalized': normalized_edit,
                                'edit_distance': edit_distance
                            },
                            suggested_predicate=suggest_predicate('string_similarity', confidence),
                            bidirectional=True
                        )
                        relationships.append(relationship)
    except Exception as e:
        logger.warning(f"Error in string similarity analysis: {e}")
    
    return relationships


def find_statistical_relationships(df: pl.DataFrame) -> List[ColumnRelationship]:
    """Find relationships based on statistical correlation between columns"""
    relationships = []
    columns = df.columns
    
    for col1, col2 in combinations(columns, 2):
        try:
            # Try to convert to numeric for correlation analysis
            series1 = df[col1].drop_nulls()
            series2 = df[col2].drop_nulls()
            
            # Attempt numeric correlation
            try:
                numeric1 = series1.cast(pl.Float64).to_numpy()
                numeric2 = series2.cast(pl.Float64).to_numpy()
                
                if len(numeric1) > 1 and len(numeric2) > 1:
                    # Align the series (take common indices)
                    min_len = min(len(numeric1), len(numeric2))
                    numeric1 = numeric1[:min_len]
                    numeric2 = numeric2[:min_len]
                    
                    correlation, p_value = pearsonr(numeric1, numeric2)
                    
                    if abs(correlation) > 0.3 and p_value < 0.05:  # Significant correlation
                        confidence = abs(correlation)
                        
                        relationship = ColumnRelationship(
                            source_column=col1,
                            target_column=col2,
                            relationship_type='statistical_correlation',
                            confidence=confidence,
                            evidence={
                                'correlation': correlation,
                                'p_value': p_value,
                                'correlation_type': 'pearson'
                            },
                            suggested_predicate=suggest_predicate('statistical_correlation', confidence),
                            bidirectional=True
                        )
                        relationships.append(relationship)
            except:
                # If numeric correlation fails, try categorical analysis
                analyze_categorical_relationship(df, col1, col2, relationships)
                
        except Exception as e:
            logger.warning(f"Error in statistical analysis between {col1} and {col2}: {e}")
    
    return relationships


def analyze_categorical_relationship(df: pl.DataFrame, col1: str, col2: str, 
                                   relationships: List[ColumnRelationship]):
    """Analyze relationship between categorical columns using chi-square test"""
    try:
        # Create contingency table - handle missing pyarrow gracefully
        try:
            data_df = df.select([col1, col2]).drop_nulls()
            pandas_df = data_df.to_pandas()
            crosstab = pandas_df.crosstab(pandas_df[col1], pandas_df[col2])
        except ImportError:
            # Fallback: use Polars directly for contingency table
            data_df = df.select([col1, col2]).drop_nulls()
            if len(data_df) == 0:
                return
            
            # Create manual contingency table
            grouped = data_df.group_by([col1, col2]).len()
            if len(grouped) <= 1:
                return
            
            # Convert to simple matrix for chi-square test
            values = grouped["len"].to_list()
            if len(values) < 4:  # Need at least 2x2 table
                return
            
            # Skip chi-square test without pandas/pyarrow
            return
        
        if crosstab.size > 1:
            chi2, p_value, dof, expected = chi2_contingency(crosstab)
            
            # Calculate Cramér's V for effect size
            n = crosstab.sum().sum()
            cramers_v = math.sqrt(chi2 / (n * (min(crosstab.shape) - 1)))
            
            if p_value < 0.05 and cramers_v > 0.3:  # Significant association
                relationship = ColumnRelationship(
                    source_column=col1,
                    target_column=col2,
                    relationship_type='categorical_association',
                    confidence=cramers_v,
                    evidence={
                        'chi_square': chi2,
                        'p_value': p_value,
                        'cramers_v': cramers_v,
                        'degrees_of_freedom': dof
                    },
                    bidirectional=True
                )
                relationships.append(relationship)
    except Exception as e:
        logger.warning(f"Error in categorical analysis between {col1} and {col2}: {e}")


def find_information_theory_relationships(df: pl.DataFrame, min_mutual_information: float = 0.05) -> List[ColumnRelationship]:
    """Find relationships using information theory measures"""
    relationships = []
    columns = df.columns
    
    for col1, col2 in combinations(columns, 2):
        try:
            mutual_info = calculate_mutual_information(df, col1, col2)
            
            if mutual_info > min_mutual_information:
                # Normalize by individual entropies
                entropy1 = calculate_entropy(df[col1])
                entropy2 = calculate_entropy(df[col2])
                
                # Normalized mutual information
                max_entropy = max(entropy1, entropy2)
                normalized_mi = mutual_info / max_entropy if max_entropy > 0 else 0
                
                relationship = ColumnRelationship(
                    source_column=col1,
                    target_column=col2,
                    relationship_type='information_theory',
                    confidence=normalized_mi,
                    evidence={
                        'mutual_information': mutual_info,
                        'normalized_mi': normalized_mi,
                        'entropy_col1': entropy1,
                        'entropy_col2': entropy2
                    },
                    bidirectional=True
                )
                relationships.append(relationship)
                
        except Exception as e:
            logger.warning(f"Error in information theory analysis between {col1} and {col2}: {e}")
    
    return relationships


def find_distribution_similarity_relationships(df: pl.DataFrame) -> List[ColumnRelationship]:
    """Find relationships based on statistical distribution similarity"""
    relationships = []
    columns = df.columns
    
    for col1, col2 in combinations(columns, 2):
        try:
            similarity = compare_distributions(df, col1, col2)
            
            if similarity > 0.5:  # Threshold for distribution similarity
                relationship = ColumnRelationship(
                    source_column=col1,
                    target_column=col2,
                    relationship_type='distribution_similarity',
                    confidence=similarity,
                    evidence={
                        'distribution_similarity': similarity
                    },
                    bidirectional=True
                )
                relationships.append(relationship)
                
        except Exception as e:
            logger.warning(f"Error in distribution analysis between {col1} and {col2}: {e}")
    
    return relationships


def compare_distributions(df: pl.DataFrame, col1: str, col2: str) -> float:
    """Compare statistical distributions of two columns"""
    try:
        series1 = df[col1].drop_nulls()
        series2 = df[col2].drop_nulls()
        
        # For numeric columns, compare statistical moments
        try:
            numeric1 = series1.cast(pl.Float64)
            numeric2 = series2.cast(pl.Float64)
            
            stats1 = calculate_distribution_stats(numeric1)
            stats2 = calculate_distribution_stats(numeric2)
            
            # Calculate similarity based on normalized statistical measures
            similarity = calculate_stats_similarity(stats1, stats2)
            return similarity
            
        except:
            # For categorical columns, compare value distributions
            return compare_categorical_distributions(series1, series2)
            
    except Exception:
        return 0.0


def find_value_overlap_relationships(df: pl.DataFrame, 
                                   min_overlap_threshold: float = 0.1) -> List[ColumnRelationship]:
    """Find relationships based on overlapping values between columns"""
    relationships = []
    columns = df.columns
    
    # Calculate value overlaps between all column pairs
    for col1, col2 in combinations(columns, 2):
        try:
            # Get non-null values
            values1 = set(df[col1].drop_nulls().cast(pl.Utf8).to_list())
            values2 = set(df[col2].drop_nulls().cast(pl.Utf8).to_list())
            
            if not values1 or not values2:
                continue
            
            # Calculate overlap
            intersection = values1 & values2
            union = values1 | values2
            
            jaccard_similarity = len(intersection) / len(union) if union else 0
            overlap_ratio = len(intersection) / min(len(values1), len(values2))
            
            if overlap_ratio >= min_overlap_threshold:
                confidence = (jaccard_similarity + overlap_ratio) / 2
                
                relationship = ColumnRelationship(
                    source_column=col1,
                    target_column=col2,
                    relationship_type='value_overlap',
                    confidence=confidence,
                    evidence={
                        'jaccard_similarity': jaccard_similarity,
                        'overlap_ratio': overlap_ratio,
                        'common_values_count': len(intersection),
                        'sample_common_values': list(intersection)[:5]
                    },
                    bidirectional=True
                )
                relationships.append(relationship)
                
        except Exception as e:
            logger.warning(f"Error calculating overlap between {col1} and {col2}: {e}")
            continue
    
    return relationships


def find_pattern_relationships(df: pl.DataFrame, table_analysis=None) -> List[ColumnRelationship]:
    """Find relationships based on data patterns"""
    relationships = []
    
    if not table_analysis:
        return relationships
    
    # Group columns by pattern types
    pattern_groups = defaultdict(list)
    for col_analysis in table_analysis.columns:
        for pattern in col_analysis.patterns:
            pattern_groups[pattern].append(col_analysis.name)
    
    # Find columns with similar patterns
    for pattern, columns in pattern_groups.items():
        if len(columns) > 1:
            for col1, col2 in combinations(columns, 2):
                # Calculate pattern strength
                confidence = 0.6  # Base confidence for pattern matching
                
                # Boost confidence for specific pattern types
                if pattern.startswith('prefix:') or pattern.startswith('format:'):
                    confidence = 0.8
                
                relationship = ColumnRelationship(
                    source_column=col1,
                    target_column=col2,
                    relationship_type='pattern_match',
                    confidence=confidence,
                    evidence={
                        'shared_pattern': pattern,
                        'pattern_type': pattern.split(':')[0] if ':' in pattern else pattern
                    },
                    bidirectional=True
                )
                relationships.append(relationship)
    
    return relationships


def find_foreign_key_relationships(df: pl.DataFrame, table_analysis=None) -> List[ColumnRelationship]:
    """Find potential foreign key relationships"""
    relationships = []
    
    # Use table analysis if available
    if table_analysis:
        fk_candidates = table_analysis.foreign_key_candidates
    else:
        # Simple heuristic: columns with 'id' in name
        fk_candidates = [col for col in df.columns if 'id' in col.lower()]
    
    # Look for potential references between FK candidates and other columns
    for fk_col in fk_candidates:
        for other_col in df.columns:
            if fk_col == other_col:
                continue
            
            # Check if values in fk_col could reference entities in other_col
            try:
                fk_values = set(df[fk_col].drop_nulls().cast(pl.Utf8).to_list())
                other_values = set(df[other_col].drop_nulls().cast(pl.Utf8).to_list())
                
                # Simple check: if FK values are substrings of other values
                reference_matches = sum(1 for fk_val in fk_values 
                                      if any(fk_val in other_val for other_val in other_values))
                
                if reference_matches > 0:
                    confidence = reference_matches / len(fk_values) if fk_values else 0
                    
                    if confidence > 0.1:  # At least 10% match
                        relationship = ColumnRelationship(
                            source_column=fk_col,
                            target_column=other_col,
                            relationship_type='foreign_key',
                            confidence=confidence,
                            evidence={
                                'reference_matches': reference_matches,
                                'total_fk_values': len(fk_values),
                                'match_ratio': confidence
                            },
                            suggested_predicate='dcterms:references'
                        )
                        relationships.append(relationship)
                        
            except Exception as e:
                logger.warning(f"Error checking FK relationship {fk_col} -> {other_col}: {e}")
                continue
    
    return relationships