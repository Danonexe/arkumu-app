"""
Table Analysis Service

Analyzes CSV files to detect structure, patterns, and potential semantic mappings.
Provides foundation for intelligent mapping suggestions through data-driven pattern discovery.
"""

import polars as pl
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import logging

logger = logging.getLogger(__name__)


@dataclass
class ColumnAnalysis:
    """Analysis results for a single column"""
    name: str
    data_type: str
    sample_values: List[str]
    unique_count: int
    null_count: int
    total_count: int
    patterns: List[str]
    potential_foreign_keys: List[str]
    semantic_hints: List[str]


@dataclass
class TableAnalysis:
    """Complete analysis results for a table"""
    filename: str
    row_count: int
    column_count: int
    columns: List[ColumnAnalysis]
    table_type: str  # 'entity', 'junction', 'attribute', 'taxonomy'
    discovered_patterns: Dict[str, List[str]]
    institutional_prefixes: List[str]
    foreign_key_candidates: List[str]
    quality_score: float
    suggested_mappings: List[Dict[str, Any]]


class TableAnalysisService:
    """
    Data-driven table analysis service that discovers patterns from actual data
    without hardcoded institution-specific assumptions.
    """
    
    def __init__(self):
        self.id_patterns = [
            r'^.*_id$',
            r'^.*_uuid$',
            r'^id_.*$',
            r'^uuid_.*$',
            r'^.*_key$',
            r'^key_.*$'
        ]
        
        self.common_semantic_patterns = {
            'person': [r'.*person.*', r'.*author.*', r'.*creator.*', r'.*artist.*'],
            'place': [r'.*place.*', r'.*location.*', r'.*city.*', r'.*country.*'],
            'date': [r'.*date.*', r'.*year.*', r'.*time.*', r'.*created.*'],
            'title': [r'.*title.*', r'.*name.*', r'.*label.*'],
            'description': [r'.*desc.*', r'.*text.*', r'.*content.*'],
            'type': [r'.*type.*', r'.*category.*', r'.*class.*']
        }

    def analyze_csv(self, file_path: str, sample_size: int = 1000) -> TableAnalysis:
        """
        Analyze a CSV file to discover patterns and suggest mappings
        """
        try:
            # Read CSV with polars - handle malformed CSV files and auto-detect delimiter
            # Try semicolon first (common in European CSV files), then comma
            try:
                df = pl.read_csv(file_path, 
                               separator=';',
                               infer_schema_length=0,
                               truncate_ragged_lines=True)
                # Check if we got multiple columns (successful parsing)
                if len(df.columns) > 1:
                    logger.info(f"Successfully parsed CSV with semicolon delimiter: {len(df.columns)} columns")
                else:
                    raise ValueError("Single column detected, try comma delimiter")
            except:
                # Fallback to comma delimiter
                logger.info("Semicolon delimiter failed, trying comma delimiter")
                df = pl.read_csv(file_path, 
                               separator=',',
                               infer_schema_length=0,
                               truncate_ragged_lines=True)
            
            # Sample if file is large
            if len(df) > sample_size:
                df = df.sample(sample_size)
            
            # Analyze each column
            columns = []
            for col_name in df.columns:
                column_analysis = self._analyze_column(df, col_name)
                columns.append(column_analysis)
            
            # Determine table type
            table_type = self._classify_table_type(columns)
            
            # Discover institutional patterns
            discovered_patterns = self._discover_patterns(columns)
            institutional_prefixes = self._extract_institutional_prefixes(columns)
            
            # Find foreign key candidates
            foreign_key_candidates = self._find_foreign_key_candidates(columns)
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(columns, df)
            
            # Generate mapping suggestions
            suggested_mappings = self._generate_mapping_suggestions(columns, discovered_patterns)
            
            return TableAnalysis(
                filename=file_path,
                row_count=len(df),
                column_count=len(df.columns),
                columns=columns,
                table_type=table_type,
                discovered_patterns=discovered_patterns,
                institutional_prefixes=institutional_prefixes,
                foreign_key_candidates=foreign_key_candidates,
                quality_score=quality_score,
                suggested_mappings=suggested_mappings
            )
            
        except Exception as e:
            logger.error(f"Error analyzing CSV {file_path}: {e}")
            raise

    def _analyze_column(self, df: pl.DataFrame, col_name: str) -> ColumnAnalysis:
        """Analyze a single column"""
        col_data = df[col_name]
        
        # Basic statistics
        total_count = len(col_data)
        null_count = col_data.null_count()
        unique_count = col_data.n_unique()
        
        # Data type detection
        data_type = str(col_data.dtype)
        
        # Sample values (non-null)
        non_null_values = col_data.drop_nulls()
        sample_values = []
        if len(non_null_values) > 0:
            sample_count = min(5, len(non_null_values))
            sample_values = [str(val) for val in non_null_values.head(sample_count).to_list()]
        
        # Pattern discovery
        patterns = self._discover_column_patterns(sample_values + non_null_values.tail(10).to_list())
        
        # Foreign key detection
        potential_foreign_keys = self._detect_foreign_keys(col_name, sample_values)
        
        # Semantic hints
        semantic_hints = self._get_semantic_hints(col_name, sample_values)
        
        return ColumnAnalysis(
            name=col_name,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            null_count=null_count,
            total_count=total_count,
            patterns=patterns,
            potential_foreign_keys=potential_foreign_keys,
            semantic_hints=semantic_hints
        )

    def _discover_column_patterns(self, values: List[str]) -> List[str]:
        """Discover patterns in column values"""
        patterns = []
        
        if not values:
            return patterns
        
        # Convert to strings and filter non-empty
        str_values = [str(v) for v in values if v is not None and str(v).strip()]
        
        if not str_values:
            return patterns
        
        # Common prefix/suffix patterns
        prefixes = self._find_common_prefixes(str_values)
        suffixes = self._find_common_suffixes(str_values)
        
        patterns.extend([f"prefix:{p}" for p in prefixes])
        patterns.extend([f"suffix:{s}" for s in suffixes])
        
        # Format patterns
        format_patterns = self._detect_format_patterns(str_values)
        patterns.extend(format_patterns)
        
        return patterns[:10]  # Limit to top 10 patterns

    def _find_common_prefixes(self, values: List[str], min_frequency: float = 0.3) -> List[str]:
        """Find common prefixes in values"""
        prefixes = Counter()
        
        for value in values:
            # First check for delimiter-based prefixes (e.g., "ARTIST_001" -> "ARTIST")
            if '_' in value:
                delimiter_prefix = value.split('_')[0]
                if len(delimiter_prefix) >= 1:  # Accept single char for delimited values
                    prefixes[delimiter_prefix] += 1
            
            # Also check for common character prefixes  
            # For alphanumeric values like "P001", allow single character prefixes
            # For longer alphabetic values, require at least 2 characters
            min_length = 1 if any(c.isdigit() for c in value) else 2
            
            for length in range(min_length, min(len(value), 10)):
                prefix = value[:length]
                # Allow single chars for alphanumeric patterns, 2+ chars for pure alpha
                if ((length == 1 and prefix.isalpha() and any(c.isdigit() for c in value)) or
                    (length >= 2 and prefix.isalpha() and 2 <= len(prefix) <= 8)):
                    prefixes[prefix] += 1
        
        # Filter by frequency and prioritize longer prefixes
        threshold = len(values) * min_frequency
        valid_prefixes = [prefix for prefix, count in prefixes.items() if count >= threshold]
        
        # Remove shorter prefixes that are substrings of longer ones
        filtered_prefixes = []
        for prefix in sorted(valid_prefixes, key=len, reverse=True):  # Sort by length, longest first
            if not any(prefix in longer for longer in filtered_prefixes):
                filtered_prefixes.append(prefix)
        
        return filtered_prefixes[:5]  # Return top 5

    def _find_common_suffixes(self, values: List[str], min_frequency: float = 0.3) -> List[str]:
        """Find common suffixes in values"""
        suffixes = Counter()
        
        for value in values:
            # Try different suffix lengths
            for length in range(1, min(len(value), 10)):
                suffix = value[-length:]
                suffixes[suffix] += 1
        
        # Filter by frequency
        threshold = len(values) * min_frequency
        return [suffix for suffix, count in suffixes.most_common(5) if count >= threshold]

    def _detect_format_patterns(self, values: List[str]) -> List[str]:
        """Detect common format patterns"""
        patterns = []
        
        # Check for common formats
        format_checks = {
            'uuid_format': lambda v: len(v) == 36 and v.count('-') == 4,
            'date_format': lambda v: re.match(r'\d{4}-\d{2}-\d{2}', v),
            'url_format': lambda v: v.startswith(('http://', 'https://')),
            'email_format': lambda v: '@' in v and '.' in v,
            'numeric_id': lambda v: v.isdigit(),
            'mixed_id': lambda v: re.match(r'^[A-Za-z]+\d+$', v)
        }
        
        for pattern_name, check_func in format_checks.items():
            matching_count = sum(1 for v in values if check_func(v))
            if matching_count / len(values) >= 0.3:  # 30% threshold
                patterns.append(f"format:{pattern_name}")
        
        return patterns

    def _detect_foreign_keys(self, col_name: str, sample_values: List[str]) -> List[str]:
        """Detect if column might be a foreign key"""
        potential_fks = []
        
        # Check column name patterns
        for pattern in self.id_patterns:
            if re.match(pattern, col_name.lower()):
                potential_fks.append(f"name_pattern:{pattern}")
        
        # Check value patterns
        if sample_values:
            # Look for patterns that suggest references to other entities
            for value in sample_values[:5]:
                if isinstance(value, str):
                    # Extract potential entity prefixes
                    if '_' in value:
                        prefix = value.split('_')[0]
                        potential_fks.append(f"value_prefix:{prefix}")
        
        return list(set(potential_fks))

    def _get_semantic_hints(self, col_name: str, sample_values: List[str]) -> List[str]:
        """Get semantic hints based on column name and values"""
        hints = []
        
        col_lower = col_name.lower()
        
        # Check against semantic patterns
        for semantic_type, patterns in self.common_semantic_patterns.items():
            for pattern in patterns:
                if re.search(pattern, col_lower):
                    hints.append(semantic_type)
                    break
        
        # Check sample values for additional hints
        if sample_values:
            sample_text = ' '.join(str(v) for v in sample_values[:3]).lower()
            
            # Date detection
            if re.search(r'\d{4}', sample_text):
                hints.append('temporal')
            
            # URL detection
            if any(str(v).startswith(('http', 'www')) for v in sample_values):
                hints.append('resource')
        
        return list(set(hints))

    def _classify_table_type(self, columns: List[ColumnAnalysis]) -> str:
        """Classify the type of table based on column analysis"""
        
        # Count different types of columns
        id_columns = sum(1 for col in columns if any('id' in p for p in col.patterns + col.potential_foreign_keys))
        fk_columns = sum(1 for col in columns if col.potential_foreign_keys)
        
        total_columns = len(columns)
        
        # Junction table: multiple foreign keys, few other columns
        if fk_columns >= 2 and total_columns <= 5:
            return 'junction'
        
        # Entity table: has ID, multiple descriptive columns
        elif id_columns >= 1 and total_columns >= 3:
            return 'entity'
        
        # Attribute table: mostly descriptive columns
        elif fk_columns <= 1 and total_columns >= 2:
            return 'attribute'
        
        # Taxonomy table: hierarchical or categorical data
        elif any('type' in col.name.lower() or 'category' in col.name.lower() for col in columns):
            return 'taxonomy'
        
        return 'entity'  # Default

    def _discover_patterns(self, columns: List[ColumnAnalysis]) -> Dict[str, List[str]]:
        """Discover patterns across all columns"""
        patterns = {
            'prefixes': [],
            'suffixes': [],
            'formats': [],
            'naming_conventions': []
        }
        
        # Collect all patterns from columns
        for col in columns:
            for pattern in col.patterns:
                if pattern.startswith('prefix:'):
                    patterns['prefixes'].append(pattern[7:])
                elif pattern.startswith('suffix:'):
                    patterns['suffixes'].append(pattern[7:])
                elif pattern.startswith('format:'):
                    patterns['formats'].append(pattern[7:])
        
        # Find naming conventions
        col_names = [col.name for col in columns]
        patterns['naming_conventions'] = self._find_naming_conventions(col_names)
        
        return patterns

    def _find_naming_conventions(self, col_names: List[str]) -> List[str]:
        """Find naming conventions used in column names"""
        conventions = []
        
        # Check for snake_case
        if any('_' in name for name in col_names):
            conventions.append('snake_case')
        
        # Check for camelCase
        if any(re.search(r'[a-z][A-Z]', name) for name in col_names):
            conventions.append('camelCase')
        
        # Check for common prefixes in column names
        prefixes = self._find_common_prefixes(col_names, min_frequency=0.5)
        conventions.extend([f"column_prefix:{p}" for p in prefixes])
        
        return conventions

    def _extract_institutional_prefixes(self, columns: List[ColumnAnalysis]) -> List[str]:
        """Extract institutional or organizational prefixes from data"""
        prefixes = set()
        
        for col in columns:
            for pattern in col.patterns:
                if pattern.startswith('prefix:'):
                    prefix = pattern[7:]
                    # Filter for likely institutional prefixes
                    # Allow 1-8 chars for alphabetic prefixes (1 char only for special cases like 'P' in IDs)
                    if 1 <= len(prefix) <= 8 and prefix.isalpha():
                        prefixes.add(prefix.upper())
        
        return sorted(list(prefixes))

    def _find_foreign_key_candidates(self, columns: List[ColumnAnalysis]) -> List[str]:
        """Find columns that are likely foreign keys"""
        candidates = []
        
        for col in columns:
            if col.potential_foreign_keys:
                candidates.append(col.name)
        
        return candidates

    def _calculate_quality_score(self, columns: List[ColumnAnalysis], df: pl.DataFrame) -> float:
        """Calculate overall data quality score"""
        scores = []
        
        for col in columns:
            # Completeness score
            completeness = 1 - (col.null_count / col.total_count) if col.total_count > 0 else 0
            
            # Uniqueness score for potential ID columns
            uniqueness = col.unique_count / col.total_count if col.total_count > 0 else 0
            
            # Pattern consistency score
            pattern_score = len(col.patterns) / 10  # Normalize to 0-1
            
            # Combine scores
            col_score = (completeness * 0.5 + uniqueness * 0.3 + pattern_score * 0.2)
            scores.append(col_score)
        
        return sum(scores) / len(scores) * 10 if scores else 0  # Scale to 0-10

    def _generate_mapping_suggestions(self, columns: List[ColumnAnalysis], patterns: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Generate intelligent mapping suggestions based on analysis"""
        suggestions = []
        
        for col in columns:
            # Generate suggestions based on semantic hints
            for hint in col.semantic_hints:
                confidence = self._calculate_mapping_confidence(col, hint)
                
                if confidence > 0.5:  # Only suggest if confidence > 50%
                    suggestions.append({
                        'column': col.name,
                        'pattern_type': 'semantic',
                        'pattern': hint,
                        'suggested_type': f"arkumu:{hint}",
                        'confidence': confidence * 100,
                        'match_count': col.unique_count,
                        'examples': col.sample_values[:3]
                    })
            
            # Generate suggestions based on discovered patterns
            for pattern in col.patterns:
                if pattern.startswith('prefix:'):
                    prefix = pattern[7:]
                    confidence = 0.7  # Good confidence for prefix patterns
                    
                    suggestions.append({
                        'column': col.name,
                        'pattern_type': 'prefix',
                        'pattern': prefix,
                        'suggested_type': f"institution:{prefix.lower()}_entity",
                        'confidence': confidence * 100,
                        'match_count': col.unique_count,
                        'examples': col.sample_values[:3]
                    })
        
        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        return suggestions[:10]  # Return top 10 suggestions

    def _calculate_mapping_confidence(self, col: ColumnAnalysis, semantic_hint: str) -> float:
        """Calculate confidence score for a mapping suggestion"""
        confidence = 0.5  # Base confidence
        
        # Boost confidence based on data quality
        completeness = 1 - (col.null_count / col.total_count) if col.total_count > 0 else 0
        confidence += completeness * 0.3
        
        # Boost confidence based on pattern consistency
        if col.patterns:
            confidence += 0.2
        
        # Adjust based on semantic hint specificity
        specific_hints = ['person', 'place', 'date']
        if semantic_hint in specific_hints:
            confidence += 0.1
        
        return min(confidence, 1.0)  # Cap at 1.0 