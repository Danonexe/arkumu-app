"""
Cross-Dataset Relationship Analysis

Contains methods for discovering potential relationships between columns
across different datasets using value overlap and pattern analysis.
"""

import polars as pl
import re
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
import logging

from .domain import ColumnRelationship, DatasetRelationshipAnalysis
from .utils import calculate_column_similarity

logger = logging.getLogger(__name__)


def find_cross_dataset_relationships(dataset1_name: str, analysis1: DatasetRelationshipAnalysis,
                                   dataset2_name: str, analysis2: DatasetRelationshipAnalysis,
                                   current_dataset_paths: Dict[str, str]) -> List[ColumnRelationship]:
    """Find potential relationships between columns in different datasets using data-driven analysis"""
    cross_relationships = []
    
    # Load actual data for value analysis
    try:
        dataset1_columns = analysis1.column_names
        dataset2_columns = analysis2.column_names
        
        # 1. Value overlap analysis (most important for FK relationships)
        value_based_relationships = find_value_overlap_cross_dataset(
            dataset1_name, dataset1_columns, dataset2_name, dataset2_columns, current_dataset_paths
        )
        cross_relationships.extend(value_based_relationships)
        
        # 2. Column name similarity (as fallback)
        name_based_relationships = find_name_similarity_cross_dataset(
            dataset1_name, dataset1_columns, dataset2_name, dataset2_columns
        )
        cross_relationships.extend(name_based_relationships)
        
        # 3. Remove duplicates (prefer value-based over name-based)
        cross_relationships = deduplicate_cross_relationships(cross_relationships)
        
    except Exception as e:
        logger.warning(f"Error in cross-dataset analysis: {e}")
    
    return cross_relationships


def find_value_overlap_cross_dataset(dataset1_name: str, dataset1_columns: List[str],
                                   dataset2_name: str, dataset2_columns: List[str],
                                   current_dataset_paths: Dict[str, str]) -> List[ColumnRelationship]:
    """Find cross-dataset relationships based on actual value overlap"""
    relationships = []
    
    try:
        # Load actual data for both datasets
        dataset1_path = current_dataset_paths.get(dataset1_name)
        dataset2_path = current_dataset_paths.get(dataset2_name)
        
        if not dataset1_path or not dataset2_path:
            logger.warning(f"Could not find dataset paths for {dataset1_name} or {dataset2_name}")
            return relationships
        
        df1 = pl.read_csv(dataset1_path)
        df2 = pl.read_csv(dataset2_path)
        
        logger.info(f"Analyzing value overlap between {dataset1_name} and {dataset2_name}")
        
        # Compare all column pairs for value overlap and patterns
        for col1 in dataset1_columns:
            if col1 not in df1.columns:
                continue
                
            for col2 in dataset2_columns:
                if col2 not in df2.columns:
                    continue
                
                # 1. Direct value overlap analysis
                values1 = set(df1[col1].drop_nulls().to_list())
                values2 = set(df2[col2].drop_nulls().to_list())
                
                if values1 and values2:
                    # Calculate overlap metrics
                    intersection = values1 & values2
                    union = values1 | values2
                    
                    # Jaccard similarity (intersection over union)
                    jaccard = len(intersection) / len(union) if union else 0
                    
                    # Overlap percentage (intersection over smaller set)
                    overlap_pct = len(intersection) / min(len(values1), len(values2)) if values1 and values2 else 0
                    
                    # Foreign key likelihood (one set is subset of another)
                    fk_likelihood = 0
                    if values1.issubset(values2):
                        fk_likelihood = len(values1) / len(values2) if values2 else 0
                    elif values2.issubset(values1):
                        fk_likelihood = len(values2) / len(values1) if values1 else 0
                    
                    # Consider it a significant relationship if there's meaningful overlap
                    min_overlap_threshold = 0.1  # At least 10% overlap
                    min_fk_threshold = 0.3      # At least 30% for FK relationship
                    
                    if jaccard > min_overlap_threshold or overlap_pct > min_overlap_threshold or fk_likelihood > min_fk_threshold:
                        # Determine relationship type and confidence
                        if fk_likelihood > min_fk_threshold:
                            rel_type = 'cross_dataset_foreign_key'
                            confidence = fk_likelihood
                        else:
                            rel_type = 'cross_dataset_value_overlap'
                            confidence = max(jaccard, overlap_pct)
                        
                        # Debug logging for expected relationships
                        expected_pairs = [
                            ('person_id', 'individual_id'),
                            ('artist_id', 'creator_id')
                        ]
                        if (col1, col2) in expected_pairs or (col2, col1) in expected_pairs:
                            logger.info(f"Value overlap {col1} <-> {col2}: jaccard={jaccard:.3f}, overlap={overlap_pct:.3f}, fk={fk_likelihood:.3f}")
                        
                        relationship = ColumnRelationship(
                            source_column=f"{dataset1_name}.{col1}",
                            target_column=f"{dataset2_name}.{col2}",
                            relationship_type=rel_type,
                            confidence=confidence,
                            evidence={
                                'jaccard_similarity': jaccard,
                                'overlap_percentage': overlap_pct,
                                'foreign_key_likelihood': fk_likelihood,
                                'intersection_size': len(intersection),
                                'values1_size': len(values1),
                                'values2_size': len(values2),
                                'similarity_type': 'value_based',
                                'source_dataset': dataset1_name,
                                'target_dataset': dataset2_name
                            }
                        )
                        relationships.append(relationship)
                
                # 2. Split value analysis (e.g., "John,Doe" vs separate first/last columns)
                split_relationships = analyze_split_values_cross_dataset(
                    df1, col1, df2, col2, dataset1_name, dataset2_name
                )
                relationships.extend(split_relationships)
                
                # 3. Pattern analysis (e.g., 'P001' vs 'I001' - different prefixes, same format)
                pattern_relationship = analyze_value_patterns_cross_dataset(
                    df1, col1, df2, col2, dataset1_name, dataset2_name
                )
                if pattern_relationship:
                    relationships.append(pattern_relationship)
        
    except Exception as e:
        logger.warning(f"Error in value overlap analysis: {e}")
    
    return relationships


def analyze_split_values_cross_dataset(df1: pl.DataFrame, col1: str, df2: pl.DataFrame, col2: str,
                                      dataset1_name: str, dataset2_name: str) -> List[ColumnRelationship]:
    """Analyze relationships where values might be split or combined differently"""
    relationships = []
    
    try:
        # Get sample values to analyze patterns
        values1 = df1[col1].drop_nulls().head(50).to_list()
        values2 = df2[col2].drop_nulls().head(50).to_list()
        
        # Common split patterns
        split_patterns = [',', ';', '|', ' ', '\t', '-', '_', ':']
        
        for pattern in split_patterns:
            split_relationship = analyze_split_pattern_cross_dataset(
                values1, values2, pattern, col1, col2, dataset1_name, dataset2_name
            )
            if split_relationship:
                relationships.append(split_relationship)
                break  # Found a pattern, no need to try others
    
    except Exception as e:
        logger.warning(f"Error analyzing split values between {col1} and {col2}: {e}")
    
    return relationships


def analyze_split_pattern_cross_dataset(values1: List, values2: List, pattern: str, col1: str, col2: str,
                                       dataset1_name: str, dataset2_name: str) -> Optional[ColumnRelationship]:
    """Analyze a specific split pattern for cross-dataset relationships"""
    try:
        # Split values by pattern and create sets of components
        components1 = set()
        components2 = set()
        
        for val in values1:
            if isinstance(val, str) and pattern in val:
                components1.update(part.strip() for part in val.split(pattern) if part.strip())
        
        for val in values2:
            if isinstance(val, str):
                if pattern == ' ':
                    # For space, treat each word as a component
                    components2.update(part.strip() for part in val.split() if part.strip())
                else:
                    components2.add(val.strip())
        
        if not components1 or not components2:
            return None
        
        # Calculate overlap between split components and target values
        intersection = components1 & components2
        if len(intersection) > 2:  # At least 3 matching components
            overlap_ratio = len(intersection) / len(components1)
            
            if overlap_ratio > 0.3:  # 30% of split components match target values
                logger.info(f"Split value relationship found: {col1} ({pattern}) <-> {col2}, overlap={overlap_ratio:.3f}")
                
                return ColumnRelationship(
                    source_column=f"{dataset1_name}.{col1}",
                    target_column=f"{dataset2_name}.{col2}",
                    relationship_type='cross_dataset_split_values',
                    confidence=overlap_ratio,
                    evidence={
                        'similarity_type': 'value_based',
                        'split_pattern': pattern,
                        'overlap_ratio': overlap_ratio,
                        'matching_components': list(intersection)[:5],
                        'total_components': len(components1),
                        'source_dataset': dataset1_name,
                        'target_dataset': dataset2_name
                    }
                )
    except Exception:
        pass
    
    return None


def analyze_value_patterns_cross_dataset(df1: pl.DataFrame, col1: str, df2: pl.DataFrame, col2: str,
                                        dataset1_name: str, dataset2_name: str) -> Optional[ColumnRelationship]:
    """Analyze value patterns that might indicate relationships (IDs, codes, etc.)"""
    try:
        values1 = df1[col1].drop_nulls().head(20).to_list()
        values2 = df2[col2].drop_nulls().head(20).to_list()
        
        # Pattern analysis for IDs and codes
        pattern_scores = []
        
        # 1. Prefix/suffix pattern matching (e.g., 'P001' vs 'I001')
        prefix_score = analyze_prefix_suffix_patterns(values1, values2)
        if prefix_score > 0:
            pattern_scores.append(('prefix_suffix', prefix_score))
        
        # 2. Numeric ID pattern matching
        numeric_score = analyze_numeric_patterns(values1, values2)
        if numeric_score > 0:
            pattern_scores.append(('numeric_pattern', numeric_score))
        
        # 3. Format similarity (length, character types)
        format_score = analyze_format_similarity(values1, values2)
        if format_score > 0:
            pattern_scores.append(('format_similarity', format_score))
        
        # Return the best pattern match
        if pattern_scores:
            best_pattern, best_score = max(pattern_scores, key=lambda x: x[1])
            
            if best_score > 0.4:  # Threshold for pattern significance
                logger.info(f"Pattern relationship found: {col1} <-> {col2}, type={best_pattern}, score={best_score:.3f}")
                
                return ColumnRelationship(
                    source_column=f"{dataset1_name}.{col1}",
                    target_column=f"{dataset2_name}.{col2}",
                    relationship_type='cross_dataset_pattern_similarity',
                    confidence=best_score,
                    evidence={
                        'similarity_type': 'value_based',
                        'pattern_type': best_pattern,
                        'pattern_score': best_score,
                        'sample_values1': values1[:3],
                        'sample_values2': values2[:3],
                        'source_dataset': dataset1_name,
                        'target_dataset': dataset2_name
                    }
                )
    
    except Exception as e:
        logger.warning(f"Error analyzing value patterns between {col1} and {col2}: {e}")
    
    return None


def analyze_prefix_suffix_patterns(values1: List, values2: List) -> float:
    """Analyze prefix/suffix patterns (e.g., 'P001' vs 'I001')"""
    try:
        if not values1 or not values2:
            return 0.0
        
        # Extract prefixes and suffixes
        prefixes1 = set()
        suffixes1 = set()
        prefixes2 = set()
        suffixes2 = set()
        
        for val in values1:
            if isinstance(val, str) and len(val) > 2:
                # Extract first 1-2 chars as prefix
                prefixes1.add(val[:1])
                prefixes1.add(val[:2] if len(val) > 1 else val[:1])
                # Extract last 3 chars as suffix (numeric part)
                suffixes1.add(val[-3:])
        
        for val in values2:
            if isinstance(val, str) and len(val) > 2:
                prefixes2.add(val[:1])
                prefixes2.add(val[:2] if len(val) > 1 else val[:1])
                suffixes2.add(val[-3:])
        
        # Check for different prefixes but similar suffix patterns
        if len(prefixes1 & prefixes2) == 0:  # Different prefixes
            # Check if suffixes have similar patterns (e.g., both are numeric)
            numeric_suffixes1 = sum(1 for s in suffixes1 if s.isdigit())
            numeric_suffixes2 = sum(1 for s in suffixes2 if s.isdigit())
            
            if numeric_suffixes1 > 0 and numeric_suffixes2 > 0:
                # Different prefixes but similar numeric suffix patterns
                return 0.6
        
        return 0.0
    except Exception:
        return 0.0


def analyze_numeric_patterns(values1: List, values2: List) -> float:
    """Analyze numeric patterns in values"""
    try:
        # Extract numeric parts
        numbers1 = []
        numbers2 = []
        
        for val in values1:
            nums = re.findall(r'\d+', str(val))
            numbers1.extend([int(n) for n in nums if n])
        
        for val in values2:
            nums = re.findall(r'\d+', str(val))
            numbers2.extend([int(n) for n in nums if n])
        
        if not numbers1 or not numbers2:
            return 0.0
        
        # Check for overlapping numeric ranges
        range1 = (min(numbers1), max(numbers1))
        range2 = (min(numbers2), max(numbers2))
        
        # Calculate range overlap
        overlap_start = max(range1[0], range2[0])
        overlap_end = min(range1[1], range2[1])
        
        if overlap_start <= overlap_end:
            overlap = overlap_end - overlap_start + 1
            total_range = max(range1[1], range2[1]) - min(range1[0], range2[0]) + 1
            return min(0.8, overlap / total_range)  # Cap at 0.8
        
        return 0.0
    except Exception:
        return 0.0


def analyze_format_similarity(values1: List, values2: List) -> float:
    """Analyze format similarity (length, character patterns)"""
    try:
        if not values1 or not values2:
            return 0.0
        
        # Analyze length patterns
        lengths1 = [len(str(val)) for val in values1]
        lengths2 = [len(str(val)) for val in values2]
        
        avg_len1 = sum(lengths1) / len(lengths1)
        avg_len2 = sum(lengths2) / len(lengths2)
        
        # Similar average lengths suggest similar formats
        length_similarity = 1 - abs(avg_len1 - avg_len2) / max(avg_len1, avg_len2, 1)
        
        # Analyze character type patterns
        patterns1 = set()
        patterns2 = set()
        
        for val in values1[:10]:  # Sample to avoid performance issues
            pattern = get_character_pattern(str(val))
            patterns1.add(pattern)
        
        for val in values2[:10]:
            pattern = get_character_pattern(str(val))
            patterns2.add(pattern)
        
        # Pattern overlap
        pattern_overlap = len(patterns1 & patterns2) / len(patterns1 | patterns2) if (patterns1 | patterns2) else 0
        
        # Combined score
        return (length_similarity + pattern_overlap) / 2
    
    except Exception:
        return 0.0


def get_character_pattern(value: str) -> str:
    """Get character pattern (e.g., 'P001' -> 'Lddd')"""
    pattern = ""
    for char in value:
        if char.isalpha():
            pattern += 'L' if char.isupper() else 'l'
        elif char.isdigit():
            pattern += 'd'
        else:
            pattern += 's'  # symbol
    return pattern


def find_name_similarity_cross_dataset(dataset1_name: str, dataset1_columns: List[str],
                                      dataset2_name: str, dataset2_columns: List[str]) -> List[ColumnRelationship]:
    """Find cross-dataset relationships based on column name similarity"""
    relationships = []
    
    # Compare all column pairs between datasets
    for col1 in dataset1_columns:
        for col2 in dataset2_columns:
            # Check semantic similarity
            similarity = calculate_column_similarity(col1, col2)
            
            # Debug: log similarity scores for expected matches
            expected_pairs = [
                ('person_id', 'individual_id'),
                ('person_name', 'individual_name'), 
                ('birth_date', 'date_of_birth'),
                ('artist_id', 'creator_id')
            ]
            if (col1, col2) in expected_pairs or (col2, col1) in expected_pairs:
                logger.info(f"Name similarity between {col1} and {col2}: {similarity:.3f}")
            
            # Lower threshold for cross-dataset relationships to capture more potential matches
            if similarity > 0.15:  # Very low threshold to catch subtle similarities
                relationship = ColumnRelationship(
                    source_column=f"{dataset1_name}.{col1}",
                    target_column=f"{dataset2_name}.{col2}",
                    relationship_type='cross_dataset_semantic',
                    confidence=similarity,
                    evidence={
                        'similarity_score': similarity,
                        'similarity_type': 'name_based',
                        'source_dataset': dataset1_name,
                        'target_dataset': dataset2_name
                    }
                )
                relationships.append(relationship)
    
    return relationships


def deduplicate_cross_relationships(relationships: List[ColumnRelationship]) -> List[ColumnRelationship]:
    """Remove duplicate relationships, preferring value-based over name-based"""
    seen_pairs = set()
    deduplicated = []
    
    # Sort by preference: value-based first, then by confidence
    sorted_rels = sorted(relationships, key=lambda r: (
        r.evidence.get('similarity_type') != 'value_based',  # False comes first
        -r.confidence
    ))
    
    for rel in sorted_rels:
        pair = (rel.source_column, rel.target_column)
        reverse_pair = (rel.target_column, rel.source_column)
        
        if pair not in seen_pairs and reverse_pair not in seen_pairs:
            deduplicated.append(rel)
            seen_pairs.add(pair)
    
    return deduplicated 