"""
Test suite for TableAnalysisService
"""

import pytest
import polars as pl
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from arkumu.metadata.services.metadata_models_mapping.table_analysis import (
    TableAnalysisService, 
    ColumnAnalysis, 
    TableAnalysis
)


class TestTableAnalysisService:
    """Test cases for TableAnalysisService"""
    
    @pytest.fixture
    def service(self):
        """Create a TableAnalysisService instance"""
        return TableAnalysisService()
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame for testing"""
        return pl.DataFrame({
            'person_id': ['P001', 'P002', 'P003', 'P004', 'P005'],
            'person_name': ['John Doe', 'Jane Smith', 'Bob Johnson', 'Alice Brown', 'Charlie Davis'],
            'birth_date': ['1990-01-15', '1985-06-22', '1992-11-30', '1988-03-10', '1995-09-05'],
            'email': ['john@example.com', 'jane@example.com', 'bob@example.com', 'alice@example.com', 'charlie@example.com'],
            'department_id': ['DEPT_001', 'DEPT_002', 'DEPT_001', 'DEPT_003', 'DEPT_002'],
            'status': ['active', 'active', 'inactive', 'active', 'active']
        })
    
    @pytest.fixture
    def temp_csv(self, sample_df):
        """Create a temporary CSV file with sample data"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            sample_df.write_csv(f.name)
            yield f.name
        os.unlink(f.name)
    
    def test_init(self, service):
        """Test service initialization"""
        assert service.id_patterns is not None
        assert len(service.id_patterns) > 0
        assert service.common_semantic_patterns is not None
        assert 'person' in service.common_semantic_patterns
        assert 'place' in service.common_semantic_patterns
    
    def test_analyze_csv_basic(self, service, temp_csv):
        """Test basic CSV analysis"""
        result = service.analyze_csv(temp_csv)
        
        assert isinstance(result, TableAnalysis)
        assert result.filename == temp_csv
        assert result.row_count == 5
        assert result.column_count == 6
        assert len(result.columns) == 6
    
    def test_analyze_column(self, service, sample_df):
        """Test single column analysis"""
        col_analysis = service._analyze_column(sample_df, 'person_id')
        
        assert isinstance(col_analysis, ColumnAnalysis)
        assert col_analysis.name == 'person_id'
        assert col_analysis.total_count == 5
        assert col_analysis.null_count == 0
        assert col_analysis.unique_count == 5
        assert len(col_analysis.sample_values) == 5
        assert 'P001' in col_analysis.sample_values
    
    def test_discover_column_patterns(self, service):
        """Test pattern discovery in column values"""
        values = ['P001', 'P002', 'P003', 'P004', 'P005']
        patterns = service._discover_column_patterns(values)
        
        assert isinstance(patterns, list)
        assert any('prefix:P' in p for p in patterns)
    
    def test_find_common_prefixes(self, service):
        """Test common prefix detection"""
        values = ['DEPT_001', 'DEPT_002', 'DEPT_003', 'DEPT_HR', 'DEPT_IT']
        prefixes = service._find_common_prefixes(values, min_frequency=0.5)
        
        assert 'DEPT' in prefixes or 'DEPT_' in prefixes
    
    def test_find_common_suffixes(self, service):
        """Test common suffix detection"""
        values = ['user_id', 'product_id', 'order_id', 'customer_id']
        suffixes = service._find_common_suffixes(values, min_frequency=0.5)
        
        assert '_id' in suffixes or 'id' in suffixes
    
    def test_detect_format_patterns(self, service):
        """Test format pattern detection"""
        # Test date format
        date_values = ['2023-01-15', '2023-06-22', '2023-11-30', '2023-03-10']
        patterns = service._detect_format_patterns(date_values)
        assert 'format:date_format' in patterns
        
        # Test email format
        email_values = ['john@example.com', 'jane@example.com', 'bob@example.com']
        patterns = service._detect_format_patterns(email_values)
        assert 'format:email_format' in patterns
        
        # Test numeric ID
        numeric_values = ['123', '456', '789', '101112']
        patterns = service._detect_format_patterns(numeric_values)
        assert 'format:numeric_id' in patterns
    
    def test_detect_foreign_keys(self, service):
        """Test foreign key detection"""
        # Test with ID pattern in name
        fks = service._detect_foreign_keys('department_id', ['DEPT_001', 'DEPT_002'])
        assert len(fks) > 0
        assert any('name_pattern' in fk for fk in fks)
        
        # Test with value patterns
        fks = service._detect_foreign_keys('dept_ref', ['DEPT_001', 'DEPT_002', 'DEPT_003'])
        assert any('value_prefix:DEPT' in fk for fk in fks)
    
    def test_get_semantic_hints(self, service):
        """Test semantic hint extraction"""
        # Test person-related column
        hints = service._get_semantic_hints('person_name', ['John Doe', 'Jane Smith'])
        assert 'person' in hints
        
        # Test date-related column
        hints = service._get_semantic_hints('created_date', ['2023-01-15', '2023-06-22'])
        assert 'date' in hints or 'temporal' in hints
        
        # Test URL values
        hints = service._get_semantic_hints('website', ['http://example.com', 'https://test.org'])
        assert 'resource' in hints
    
    def test_classify_table_type(self, service):
        """Test table type classification"""
        # Entity table
        columns = [
            ColumnAnalysis('id', 'Int64', [], 100, 0, 100, ['format:numeric_id'], [], []),
            ColumnAnalysis('name', 'Utf8', [], 95, 5, 100, [], [], ['title']),
            ColumnAnalysis('description', 'Utf8', [], 80, 20, 100, [], [], ['description']),
            ColumnAnalysis('created_date', 'Utf8', [], 100, 0, 100, ['format:date_format'], [], ['date'])
        ]
        table_type = service._classify_table_type(columns)
        assert table_type == 'entity'
        
        # Junction table
        junction_columns = [
            ColumnAnalysis('user_id', 'Utf8', [], 50, 0, 100, [], ['name_pattern:^.*_id$'], []),
            ColumnAnalysis('role_id', 'Utf8', [], 20, 0, 100, [], ['name_pattern:^.*_id$'], []),
            ColumnAnalysis('assigned_date', 'Utf8', [], 100, 0, 100, ['format:date_format'], [], ['date'])
        ]
        table_type = service._classify_table_type(junction_columns)
        assert table_type == 'junction'
    
    def test_find_naming_conventions(self, service):
        """Test naming convention detection"""
        # Snake case
        snake_names = ['user_id', 'first_name', 'last_updated_date']
        conventions = service._find_naming_conventions(snake_names)
        assert 'snake_case' in conventions
        
        # Camel case
        camel_names = ['userId', 'firstName', 'lastUpdatedDate']
        conventions = service._find_naming_conventions(camel_names)
        assert 'camelCase' in conventions
    
    def test_extract_institutional_prefixes(self, service):
        """Test institutional prefix extraction"""
        columns = [
            ColumnAnalysis('id', 'Utf8', ['MET_001', 'MET_002'], 100, 0, 100, 
                         ['prefix:MET'], [], []),
            ColumnAnalysis('ref', 'Utf8', ['DEPT_A', 'DEPT_B'], 50, 0, 100, 
                         ['prefix:DEPT'], [], [])
        ]
        prefixes = service._extract_institutional_prefixes(columns)
        assert 'MET' in prefixes
        assert 'DEPT' in prefixes
    
    def test_calculate_quality_score(self, service, sample_df):
        """Test data quality score calculation"""
        columns = []
        for col_name in sample_df.columns:
            col_analysis = service._analyze_column(sample_df, col_name)
            columns.append(col_analysis)
        
        score = service._calculate_quality_score(columns, sample_df)
        assert 0 <= score <= 10
        assert score > 5  # Should be relatively high for clean sample data
    
    def test_generate_mapping_suggestions(self, service):
        """Test mapping suggestion generation"""
        columns = [
            ColumnAnalysis('person_name', 'Utf8', ['John Doe', 'Jane Smith'], 100, 0, 100, 
                         [], [], ['person']),
            ColumnAnalysis('birth_date', 'Utf8', ['1990-01-15', '1985-06-22'], 100, 0, 100, 
                         ['format:date_format'], [], ['date', 'temporal'])
        ]
        patterns = {'prefixes': [], 'suffixes': [], 'formats': ['date_format'], 'naming_conventions': []}
        
        suggestions = service._generate_mapping_suggestions(columns, patterns)
        assert len(suggestions) > 0
        assert any(s['column'] == 'person_name' for s in suggestions)
        assert any(s['suggested_type'] == 'arkumu:person' for s in suggestions)
    
    def test_calculate_mapping_confidence(self, service):
        """Test mapping confidence calculation"""
        # High quality column
        col = ColumnAnalysis('person_name', 'Utf8', ['John', 'Jane'], 100, 0, 100, 
                           ['prefix:P'], [], ['person'])
        confidence = service._calculate_mapping_confidence(col, 'person')
        assert 0.5 <= confidence <= 1.0
        assert confidence > 0.7  # Should be high for good quality data
        
        # Low quality column (many nulls)
        col_low = ColumnAnalysis('notes', 'Utf8', ['Note1'], 10, 90, 100, 
                               [], [], ['description'])
        confidence_low = service._calculate_mapping_confidence(col_low, 'description')
        assert confidence_low < confidence
    
    def test_analyze_csv_with_nulls(self, service):
        """Test CSV analysis with null values"""
        df_with_nulls = pl.DataFrame({
            'id': [1, 2, 3, None, 5],
            'name': ['A', None, 'C', 'D', None],
            'value': [10.5, 20.3, None, None, 50.1]
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df_with_nulls.write_csv(f.name)
            temp_file = f.name
        
        try:
            result = service.analyze_csv(temp_file)
            assert result.row_count == 5
            
            # Check null counts
            id_col = next(c for c in result.columns if c.name == 'id')
            assert id_col.null_count == 1
            
            name_col = next(c for c in result.columns if c.name == 'name')
            assert name_col.null_count == 2
        finally:
            os.unlink(temp_file)
    
    def test_analyze_csv_large_file(self, service):
        """Test CSV analysis with sampling for large files"""
        # Create a large DataFrame
        large_df = pl.DataFrame({
            'id': range(2000),
            'value': [f'VAL_{i:04d}' for i in range(2000)]
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            large_df.write_csv(f.name)
            temp_file = f.name
        
        try:
            result = service.analyze_csv(temp_file, sample_size=1000)
            # Should still show original row count
            assert result.row_count == 1000  # Sampled
        finally:
            os.unlink(temp_file)
    
    def test_analyze_csv_error_handling(self, service):
        """Test error handling in CSV analysis"""
        with pytest.raises(Exception):
            service.analyze_csv('non_existent_file.csv')
    
    def test_edge_cases(self, service):
        """Test various edge cases"""
        # Empty values list
        patterns = service._discover_column_patterns([])
        assert patterns == []
        
        # None values
        patterns = service._discover_column_patterns([None, None])
        assert patterns == []
        
        # Single character prefixes
        prefixes = service._find_common_prefixes(['a1', 'a2', 'a3'])
        assert 'a' in prefixes
        
        # No common patterns
        patterns = service._detect_format_patterns(['random', 'values', 'here'])
        assert len(patterns) == 0 or all('format:' in p for p in patterns)


class TestIntegration:
    """Integration tests for TableAnalysisService"""
    
    @pytest.fixture
    def service(self):
        return TableAnalysisService()
    
    def test_full_analysis_workflow(self, service):
        """Test complete analysis workflow"""
        # Create a more complex dataset
        complex_df = pl.DataFrame({
            'museum_object_id': [f'MET_{i:06d}' for i in range(1, 51)],
            'artist_id': [f'ARTIST_{i:03d}' for i in range(1, 51)],
            'title': [f'Artwork {i}' for i in range(1, 51)],
            'creation_date': ['1850-01-01'] * 25 + ['1900-06-15'] * 25,
            'medium': ['Oil on canvas'] * 30 + ['Bronze'] * 20,
            'department': ['European Paintings'] * 25 + ['European Sculpture'] * 25,
            'acquisition_date': [f'200{i%10}-01-01' for i in range(1, 51)],
            'credit_line': ['Gift of ' + f'Donor {i%10}' for i in range(1, 51)],
            'object_url': [f'https://metmuseum.org/art/collection/{i}' for i in range(1, 51)]
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            complex_df.write_csv(f.name)
            temp_file = f.name
        
        try:
            result = service.analyze_csv(temp_file)
            
            # Verify comprehensive analysis
            assert result.row_count == 50
            assert result.column_count == 9
            
            # Check discovered patterns
            assert 'MET' in result.institutional_prefixes
            assert 'ARTIST' in result.institutional_prefixes
            
            # Check foreign key detection
            assert 'artist_id' in result.foreign_key_candidates
            
            # Check table type
            assert result.table_type in ['entity', 'attribute']
            
            # Check quality score
            assert result.quality_score > 7  # Should be high for clean data
            
            # Check suggestions
            assert len(result.suggested_mappings) > 0
            
            # Verify specific column analysis
            object_id_col = next(c for c in result.columns if c.name == 'museum_object_id')
            assert 'prefix:MET' in object_id_col.patterns
            
            url_col = next(c for c in result.columns if c.name == 'object_url')
            assert 'format:url_format' in url_col.patterns
            
        finally:
            os.unlink(temp_file)