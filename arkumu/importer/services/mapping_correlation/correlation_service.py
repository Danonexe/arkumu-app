"""
MappingFileCorrelationService - Main orchestrator for file-mapping correlation.

Service for exact correlation between selected CSV files and mapping configuration.
Leverages existing S3DirectDataAnalyzer and MappingValidator for 90% of logic reuse.
Provides deterministic binary matching results.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.importer.services.mapping_validation.validator import MappingValidator
from arkumu.common.uri_utils import slugify_uri_part

from .data_models import (
    FileAnalysis, 
    MappingAnalysis, 
    DatasetCorrelation, 
    CorrelationResult
)
from .mapping_extractor import MappingExtractor
from .exact_matcher import ExactMatcher
from .relationship_validator import RelationshipValidator

logger = logging.getLogger(__name__)


class MappingFileCorrelationService:
    """
    Service for exact correlation between selected CSV files and mapping configuration.
    
    Leverages existing S3DirectDataAnalyzer and MappingValidator for 90% of logic reuse.
    Provides deterministic binary matching results.
    """
    
    def __init__(self, organization_code: str):
        """
        Initialize the correlation service.
        
        Args:
            organization_code: Organization code for S3 bucket access
        """
        self.organization_code = organization_code
        self.s3_analyzer = S3DirectDataAnalyzer()
        self.mapping_validator = MappingValidator()  # Extensive reuse of existing validation
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def analyze_file_dataset_correlation(self, file_paths: List[str], 
                                       mapping_config: Dict) -> CorrelationResult:
        """
        Main correlation analysis method.
        
        1. Analyze each CSV file using S3DirectDataAnalyzer
        2. Extract mapping requirements from configuration  
        3. Calculate correlation scores for file-dataset pairs
        4. Identify missing/extra files and columns
        5. Generate recommendations
        
        Args:
            file_paths: List of file paths to analyze
            mapping_config: Dictionary containing mapping configuration
            
        Returns:
            CorrelationResult with complete analysis
        """
        self.logger.info(f"Starting correlation analysis for {len(file_paths)} files")
        
        try:
            # Step 1: Validate mapping structure (REUSE MappingValidator)
            mapping_validation = self.mapping_validator.validate_mapping_completeness(mapping_config)
            if not mapping_validation['is_complete']:
                self.logger.warning(f"Mapping incomplete: {mapping_validation['missing_components']}")
                return CorrelationResult(
                    file_analyses=[],
                    mapping_analysis=None,
                    dataset_correlations=[],
                    exactly_matched_datasets=[],
                    missing_datasets=[],  # Don't treat config validation errors as missing datasets
                    unmatched_files=file_paths,
                    has_all_required_datasets=False,
                    has_no_extra_files=False,
                    recommendations=[f"Fix mapping configuration: {', '.join(mapping_validation['missing_components'])}"]
                )
            
            # Step 2: Analyze CSV files using existing S3DirectDataAnalyzer
            file_analyses = self._analyze_files(file_paths)
            
            if not file_analyses:
                self.logger.warning("No valid files found for analysis")
                return CorrelationResult(
                    file_analyses=[],
                    mapping_analysis=None,
                    dataset_correlations=[],
                    exactly_matched_datasets=[],
                    missing_datasets=[],
                    unmatched_files=file_paths,
                    has_all_required_datasets=False,
                    has_no_extra_files=False,
                    recommendations=["No valid files found - check file paths and permissions"]
                )
            
            # Step 3: Extract mapping requirements
            mapping_analysis = self._extract_mapping_requirements(mapping_config)
            
            # Step 4: Perform relationship-aware correlation
            correlation_data = self._perform_relationship_aware_correlation(
                file_analyses, mapping_analysis, mapping_config
            )
            
            # Step 5: Generate enhanced result with relationship validation
            result = self._build_enhanced_correlation_result(
                file_analyses, mapping_analysis, correlation_data
            )
            
            self.logger.info(f"Correlation analysis complete: {len(result.exactly_matched_datasets)} matched datasets, "
                           f"{len(result.missing_datasets)} missing, {len(result.unmatched_files)} unmatched files")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Correlation analysis failed: {str(e)}", exc_info=True)
            return CorrelationResult(
                file_analyses=[],
                mapping_analysis=None,
                dataset_correlations=[],
                exactly_matched_datasets=[],
                missing_datasets=[],
                unmatched_files=file_paths,
                has_all_required_datasets=False,
                has_no_extra_files=False,
                recommendations=[f"Analysis failed: {str(e)}"]
            )
    
    def get_exact_correlation_status(self, file_paths: List[str], mapping_id: str) -> Dict:
        """
        Get binary correlation status for quick checks.
        
        Args:
            file_paths: List of file paths
            mapping_id: ID of the mapping configuration
            
        Returns:
            Dictionary with binary status flags
        """
        # This would require loading mapping config by ID
        # For now, return a placeholder implementation
        return {
            'has_all_files': False,
            'has_all_datasets': False,
            'ready_for_execution': False,
            'total_issues': 0
        }
    
    def find_missing_datasets(self, mapping_config: Dict, available_files: List[str]) -> List[str]:
        """
        Find missing datasets based on available files.
        
        Args:
            mapping_config: Dictionary containing mapping configuration
            available_files: List of available file paths
            
        Returns:
            List of missing dataset names
        """
        expected_datasets = MappingExtractor.extract_expected_datasets(mapping_config)
        file_dataset_matches = ExactMatcher.match_files_to_datasets(
            [FileAnalysis(file_path=f, file_name="", column_count=0, row_count=0, 
                         columns=[], column_types={}) for f in available_files],
            expected_datasets
        )
        
        matched_datasets = set(file_dataset_matches.values())
        return ExactMatcher.find_missing_datasets(matched_datasets, expected_datasets)
    
    def calculate_exact_coverage(self, correlation_result: CorrelationResult) -> Dict:
        """
        Calculate exact coverage statistics.
        
        Args:
            correlation_result: CorrelationResult to analyze
            
        Returns:
            Dictionary with coverage statistics
        """
        if not correlation_result.mapping_analysis:
            return {'file_coverage': 0.0, 'dataset_coverage': 0.0, 'overall_ready': False}
        
        total_files = len(correlation_result.file_analyses)
        matched_files = len([c for c in correlation_result.dataset_correlations if c.is_exact_match])
        total_datasets = len(correlation_result.mapping_analysis.expected_datasets)
        matched_datasets = len(correlation_result.exactly_matched_datasets)
        
        return ExactMatcher.calculate_exact_coverage(
            total_files, matched_files, total_datasets, matched_datasets
        )
    
    
    def _analyze_files(self, file_paths: List[str]) -> List[FileAnalysis]:
        """Analyze CSV files using existing S3DirectDataAnalyzer."""
        file_analyses = []
        
        for file_path in file_paths:
            try:
                # Create S3DataSourceInfo for the file
                from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DataSourceInfo
                from arkumu.storage.services.bucket_service import BucketService
                bucket_service = BucketService()
                
                source_info = S3DataSourceInfo(
                    bucket_name=bucket_service.get_organization_bucket(self.organization_code),
                    object_key=file_path,
                    name=Path(file_path).stem,
                    format='csv'
                )
                
                # REUSE: File analysis
                analysis = self.s3_analyzer.analyze_s3_dataset_completely(source_info, include_relationships=False)
                if analysis:
                    # Extract column information from the analysis
                    columns = list(analysis.column_types.keys())
                    sample_data = analysis.preview.data_rows
                    
                    # Convert preview data to dictionary format
                    if sample_data and analysis.preview.column_headers:
                        sample_dicts = []
                        for row in sample_data[:10]:  # Take first 10 rows
                            row_dict = {}
                            for i, header in enumerate(analysis.preview.column_headers):
                                if i < len(row):
                                    row_dict[header] = row[i]
                            sample_dicts.append(row_dict)
                    else:
                        sample_dicts = None
                    
                    file_analysis = FileAnalysis(
                        file_path=file_path,
                        file_name=Path(file_path).stem,
                        column_count=len(columns),
                        row_count=analysis.row_count,
                        columns=columns,
                        column_types=analysis.column_types,
                        sample_data=sample_dicts
                    )
                    file_analyses.append(file_analysis)
                    self.logger.debug(f"Analyzed file: {file_path} ({len(columns)} columns)")
                    
                    # Add specific logging for German character files
                    if "informations" in file_analysis.file_name.lower() or "träger" in file_analysis.file_name.lower():
                        self.logger.info(f"🔍 GERMAN FILE ANALYZED: '{file_analysis.file_name}' from path '{file_path}'")
                
            except Exception as e:
                self.logger.error(f"Failed to analyze file {file_path}: {str(e)}")
                continue
        
        return file_analyses
    
    def _extract_mapping_requirements(self, mapping_config: Dict) -> MappingAnalysis:
        """Extract mapping requirements from configuration."""
        mapping_id = mapping_config.get('id', 'unknown')
        mapping_name = mapping_config.get('name', 'Unknown Mapping')
        
        expected_datasets = MappingExtractor.extract_expected_datasets(mapping_config)
        dataset_columns = MappingExtractor.extract_columns_per_dataset(mapping_config)
        column_types = MappingExtractor.extract_column_types_per_dataset(mapping_config)
        
        # Extract all relationship types
        all_relationships = MappingExtractor.extract_all_relationships(mapping_config)
        
        return MappingAnalysis(
            mapping_id=str(mapping_id),
            mapping_name=mapping_name,
            expected_datasets=expected_datasets,
            dataset_columns=dataset_columns,
            required_columns=dataset_columns,  # Same as dataset_columns for required columns
            column_types=column_types,
            relationships=all_relationships.get('relationships', []),
            fk_relationships=all_relationships.get('fk_relationships', []),
            relationship_contexts=all_relationships.get('relationship_contexts', [])
        )
    
    def _perform_exact_correlation_with_validator(self, file_analyses: List[FileAnalysis],
                                                 mapping_analysis: MappingAnalysis, 
                                                 mapping_config: Dict) -> List[DatasetCorrelation]:
        """Perform exact correlation using MappingValidator methods for consistency."""
        correlations = []
        
        for file_analysis in file_analyses:
            # NEW: Simple exact filename match to dataset
            matched_dataset = ExactMatcher.match_filename_to_dataset(
                file_analysis.file_path, mapping_analysis.expected_datasets
            )
            
            if matched_dataset:
                # REUSE: Extract workspace columns for this dataset from mapping config
                workspace_columns = MappingExtractor.extract_workspace_columns_for_dataset(
                    mapping_config, matched_dataset
                )
                
                # REUSE: MappingValidator column correlation
                column_validation = self.mapping_validator.validate_column_mappings(
                    workspace_columns, file_analysis.columns
                )
                
                # REUSE: MappingValidator type validation
                type_issues = []
                if file_analysis.sample_data:
                    type_issues = self.mapping_validator.validate_data_types(
                        workspace_columns, file_analysis.sample_data
                    )
                
                correlation = DatasetCorrelation(
                    file_path=file_analysis.file_path,
                    dataset_name=matched_dataset,
                    is_exact_match=True,
                    matched_columns=list(column_validation['mapped_columns'].keys()),
                    missing_columns=column_validation['missing_required_columns'],
                    extra_columns=column_validation['unmapped_columns'],
                    type_mismatches=type_issues,
                    status='exact_match'
                )
                
                # Update file analysis with matched dataset
                file_analysis.matched_dataset_name = matched_dataset
                
            else:
                # File doesn't match any dataset name exactly
                correlation = DatasetCorrelation(
                    file_path=file_analysis.file_path,
                    dataset_name='',
                    is_exact_match=False,
                    matched_columns=[],
                    missing_columns=[],
                    extra_columns=file_analysis.columns,
                    type_mismatches=[],
                    status='no_match'
                )
            
            correlations.append(correlation)
        
        return correlations
    
    def _perform_relationship_aware_correlation(self, 
                                              file_analyses: List[FileAnalysis],
                                              mapping_analysis: MappingAnalysis, 
                                              mapping_config: Dict) -> Dict:
        """Enhanced correlation with full relationship validation"""
        
        # 1. Basic column correlation (existing)
        correlations = self._perform_exact_correlation_with_validator(
            file_analyses, mapping_analysis, mapping_config
        )
        
        # 2. Initialize relationship validator
        rel_validator = RelationshipValidator()
        
        # 3. FK validation
        fk_validation = rel_validator.validate_fk_relationships(
            mapping_analysis.fk_relationships, file_analyses
        )
        
        # 4. Relationship context validation
        context_validation = rel_validator.validate_relationship_contexts(
            mapping_analysis.relationship_contexts, file_analyses
        )
        
        # 5. Join validation
        join_validation = rel_validator.validate_join_requirements(
            mapping_analysis.relationships, file_analyses
        )
        
        # 6. Dependency order validation
        dependency_validation = rel_validator.validate_dependency_order(
            file_analyses, mapping_analysis.fk_relationships
        )
        
        return {
            'correlations': correlations,
            'fk_validation': fk_validation,
            'context_validation': context_validation,
            'join_validation': join_validation,
            'dependency_validation': dependency_validation
        }
    
    def _build_exact_correlation_result(self, file_analyses: List[FileAnalysis],
                                      mapping_analysis: MappingAnalysis,
                                      correlations: List[DatasetCorrelation]) -> CorrelationResult:
        """Generate binary correlation result."""
        exactly_matched_datasets = [
            c.dataset_name for c in correlations 
            if c.is_exact_match and c.dataset_name
        ]
        
        unmatched_files = [
            c.file_path for c in correlations 
            if not c.is_exact_match
        ]
        
        missing_datasets = ExactMatcher.find_missing_datasets(
            set(exactly_matched_datasets), mapping_analysis.expected_datasets
        )
        
        has_all_required_datasets = len(missing_datasets) == 0
        has_no_extra_files = len(unmatched_files) == 0
        
        # Generate recommendations
        recommendations = self._generate_exact_recommendations(
            missing_datasets, unmatched_files, correlations
        )
        
        return CorrelationResult(
            file_analyses=file_analyses,
            mapping_analysis=mapping_analysis,
            dataset_correlations=correlations,
            exactly_matched_datasets=exactly_matched_datasets,
            missing_datasets=missing_datasets,
            unmatched_files=unmatched_files,
            has_all_required_datasets=has_all_required_datasets,
            has_no_extra_files=has_no_extra_files,
            recommendations=recommendations
        )
    
    def _generate_exact_recommendations(self, missing_datasets: List[str],
                                      unmatched_files: List[str],
                                      correlations: List[DatasetCorrelation]) -> List[str]:
        """
        Generate specific recommendations based on exact matching results.
        """
        recommendations = []
        
        # Missing datasets - exact files needed
        for missing_dataset in missing_datasets:
            recommendations.append(
                f"Missing file: Create '{missing_dataset}.csv' for {missing_dataset} dataset"
            )
        
        # Unmatched files
        for unmatched_file in unmatched_files:
            file_name = Path(unmatched_file).name
            recommendations.append(
                f"Extra file: '{file_name}' does not match any dataset name"
            )
        
        # Missing columns in matched files
        for correlation in correlations:
            if correlation.is_exact_match and correlation.missing_columns:
                file_name = Path(correlation.file_path).name
                recommendations.append(
                    f"Missing columns in {file_name}: {', '.join(correlation.missing_columns)}"
                )
        
        # Type mismatches in matched files
        for correlation in correlations:
            if correlation.is_exact_match and correlation.type_mismatches:
                file_name = Path(correlation.file_path).name
                for mismatch in correlation.type_mismatches:
                    column_name = mismatch.get('column_name', 'unknown')
                    expected_type = mismatch.get('expected_type', 'unknown')
                    recommendations.append(
                        f"Type mismatch in {file_name}: column '{column_name}' expected {expected_type}"
                    )
        
        return recommendations
    
    def _build_enhanced_correlation_result(self, file_analyses: List[FileAnalysis],
                                         mapping_analysis: MappingAnalysis,
                                         correlation_data: Dict) -> CorrelationResult:
        """Generate enhanced correlation result with relationship validation"""
        correlations = correlation_data['correlations']
        
        # Build basic result first
        result = self._build_exact_correlation_result(file_analyses, mapping_analysis, correlations)
        
        # Add relationship-aware recommendations
        relationship_recommendations = self._generate_relationship_aware_recommendations(
            correlation_data
        )
        
        # Combine all recommendations
        result.recommendations.extend(relationship_recommendations)
        
        # Store validation results for potential future use
        # Note: These are not part of the CorrelationResult dataclass, 
        # but could be added as a new field if needed
        self._last_validation_results = {
            'fk_validation': correlation_data['fk_validation'],
            'context_validation': correlation_data['context_validation'],
            'join_validation': correlation_data['join_validation'],
            'dependency_validation': correlation_data['dependency_validation']
        }
        
        return result
    
    def _generate_relationship_aware_recommendations(self, 
                                                   validation_results: Dict) -> List[str]:
        """Generate recommendations including relationship issues"""
        recommendations = []
        
        # FK issues
        for issue in validation_results['fk_validation']['issues']:
            if issue['type'] == 'missing_fk_column':
                recommendations.append(
                    f"FK Error in {issue['dataset']}: Column '{issue['column']}' "
                    f"needed to reference '{issue['target']}' is missing"
                )
            elif issue['type'] == 'missing_target_dataset':
                recommendations.append(
                    f"FK Target Missing: Dataset '{issue['dataset']}' referenced by "
                    f"'{issue['referenced_by']}' not found"
                )
            elif issue['type'] == 'missing_source_dataset':
                recommendations.append(
                    f"FK Source Missing: Dataset '{issue['dataset']}' with FK relationship not found"
                )
            elif issue['type'] == 'missing_target_column':
                recommendations.append(
                    f"FK Target Column Missing: '{issue['dataset']}.{issue['column']}' "
                    f"referenced by '{issue['referenced_by']}' not found"
                )
        
        # Junction table issues  
        for issue in validation_results['context_validation']['issues']:
            if issue['type'] == 'missing_junction_table':
                recommendations.append(
                    f"Junction Table Missing: '{issue['dataset']}' needed for relationship context"
                )
            elif issue['type'] == 'missing_junction_fks':
                recommendations.append(
                    f"Junction Table Error: '{issue['dataset']}' missing FK columns: "
                    f"{', '.join(issue['missing_fks'])}"
                )
            elif issue['type'] == 'missing_context_attributes':
                recommendations.append(
                    f"Junction Table Warning: '{issue['dataset']}' missing attributes: "
                    f"{', '.join(issue['missing_attrs'])}"
                )
        
        # Processing order issues
        dep_val = validation_results['dependency_validation']
        if dep_val.get('has_cycles'):
            recommendations.append(
                f"Circular Dependency: {' -> '.join(dep_val['cycle'])}"
            )
        
        # Join issues
        for issue in validation_results['join_validation']['issues']:
            recommendations.append(
                f"Join Error: Column '{issue['dataset']}.{issue['column']}' "
                f"needed for {issue['relationship']} relationship not found"
            )
        
        return recommendations