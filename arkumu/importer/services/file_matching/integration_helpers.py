"""
Integration helpers for FileDatasetMatcher service.

Provides utility functions for integrating the file matching service
with existing import pipeline components.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import asdict

from typing import TYPE_CHECKING

from .file_dataset_matcher import FileDatasetMatcher, BatchMatchResult, MatchResult

if TYPE_CHECKING:
    from ..mapping_consumer.mapping_adapter import MappingAdapter
    from ..file_upload.s3_upload_service import S3UploadService
    from ..error_handling.error_manager import ErrorManager

logger = logging.getLogger(__name__)


class FileMatchingIntegration:
    """
    Integration helper for FileDatasetMatcher with existing pipeline components.
    """
    
    def __init__(self, 
                 error_manager: Optional['ErrorManager'] = None,
                 s3_upload_service: Optional['S3UploadService'] = None):
        """
        Initialize the integration helper.
        
        Args:
            error_manager: Optional error manager instance
            s3_upload_service: Optional S3 upload service instance
        """
        self.error_manager = error_manager
        self.s3_upload_service = s3_upload_service
        self.mapping_adapter = None  # Will be initialized when needed
        self.file_matcher = FileDatasetMatcher(error_manager=self.error_manager)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def match_files_for_mapping(self, 
                              mapping_id: int,
                              selected_files: List[str],
                              base_directory: Optional[str] = None) -> Dict[str, Any]:
        """
        Match files to datasets for a specific mapping configuration.
        
        Args:
            mapping_id: ID of the mapping configuration
            selected_files: List of file paths to match
            base_directory: Optional base directory for resolving relative paths
            
        Returns:
            Dictionary with comprehensive matching results and recommendations
        """
        try:
            # Load mapping configuration
            if self.mapping_adapter is None:
                from ..mapping_consumer.mapping_adapter import MappingAdapter
                self.mapping_adapter = MappingAdapter()
            execution_config = self.mapping_adapter.translate_to_execution_config(mapping_id)
            
            # Perform file matching
            batch_result = self.file_matcher.match_files_to_datasets(
                selected_files, execution_config, base_directory
            )
            
            # Generate recommendations
            recommendations = self._generate_matching_recommendations(batch_result, execution_config)
            
            # Create comprehensive result
            result = {
                'mapping_id': mapping_id,
                'mapping_name': execution_config.mapping_name,
                'organization': execution_config.organization,
                'matching_results': {
                    'total_files': batch_result.total_files,
                    'total_datasets': batch_result.total_datasets,
                    'match_rate': batch_result.match_rate,
                    'successful_matches': len(batch_result.successful_matches),
                    'failed_matches': len(batch_result.failed_matches),
                    'unmatched_files': len(batch_result.unmatched_files),
                    'unmatched_datasets': len(batch_result.unmatched_datasets)
                },
                'file_matches': [self._serialize_match_result(match) for match in batch_result.successful_matches],
                'failed_matches': [self._serialize_match_result(match) for match in batch_result.failed_matches],
                'unmatched_files': [self._serialize_file_info(file_info) for file_info in batch_result.unmatched_files],
                'unmatched_datasets': batch_result.unmatched_datasets,
                'recommendations': recommendations,
                'ready_for_import': batch_result.match_rate >= 0.8 and len(batch_result.failed_matches) == 0
            }
            
            self.logger.info(f"Completed file matching for mapping {mapping_id}: "
                           f"{len(batch_result.successful_matches)} successful matches, "
                           f"match rate: {batch_result.match_rate:.2%}")
            
            return result
            
        except Exception as e:
            if self.error_manager:
                self.error_manager.record_error(
                    error_code="FILE_MATCHING_INTEGRATION_ERROR",
                    error_type="IntegrationError",
                    error_message=f"Failed to match files for mapping {mapping_id}: {str(e)}",
                    error_category="integration",
                    context={"mapping_id": mapping_id, "file_count": len(selected_files)}
                )
            raise
    
    def validate_files_for_datasets(self, 
                                  file_dataset_pairs: List[Tuple[str, str]],
                                  mapping_id: int,
                                  base_directory: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate specific file-dataset pairs for a mapping.
        
        Args:
            file_dataset_pairs: List of (file_path, dataset_name) tuples
            mapping_id: ID of the mapping configuration
            base_directory: Optional base directory for resolving relative paths
            
        Returns:
            Dictionary with validation results for each file-dataset pair
        """
        try:
            # Load mapping configuration
            if self.mapping_adapter is None:
                from ..mapping_consumer.mapping_adapter import MappingAdapter
                self.mapping_adapter = MappingAdapter()
            execution_config = self.mapping_adapter.translate_to_execution_config(mapping_id)
            
            validation_results = []
            
            for file_path, dataset_name in file_dataset_pairs:
                # Get dataset configuration
                dataset_config = execution_config.get_dataset_config(dataset_name)
                if not dataset_config:
                    validation_results.append({
                        'file_path': file_path,
                        'dataset_name': dataset_name,
                        'is_valid': False,
                        'issues': [f"Dataset '{dataset_name}' not found in mapping configuration"],
                        'recommendations': []
                    })
                    continue
                
                # Validate file structure
                is_valid, issues = self.file_matcher.validate_file_structure(
                    file_path, dataset_config, base_directory
                )
                
                # Analyze compatibility
                dataset_requirements = self._extract_dataset_requirements(dataset_config)
                compatibility_analysis = self.file_matcher.analyze_file_compatibility(
                    file_path, dataset_requirements, base_directory
                )
                
                validation_results.append({
                    'file_path': file_path,
                    'dataset_name': dataset_name,
                    'is_valid': is_valid,
                    'issues': issues,
                    'compatibility_score': compatibility_analysis['compatibility_score'],
                    'recommendations': compatibility_analysis['recommendations'],
                    'file_info': compatibility_analysis['file_info']
                })
            
            # Calculate overall validation status
            all_valid = all(result['is_valid'] for result in validation_results)
            total_issues = sum(len(result['issues']) for result in validation_results)
            
            return {
                'mapping_id': mapping_id,
                'validation_results': validation_results,
                'overall_valid': all_valid,
                'total_issues': total_issues,
                'ready_for_import': all_valid and total_issues == 0
            }
            
        except Exception as e:
            if self.error_manager:
                self.error_manager.record_error(
                    error_code="FILE_VALIDATION_INTEGRATION_ERROR",
                    error_type="IntegrationError",
                    error_message=f"Failed to validate files for mapping {mapping_id}: {str(e)}",
                    error_category="integration",
                    context={"mapping_id": mapping_id, "pair_count": len(file_dataset_pairs)}
                )
            raise
    
    def suggest_file_uploads(self, 
                           local_files: List[str],
                           mapping_id: int,
                           upload_prefix: str = "imports") -> Dict[str, Any]:
        """
        Suggest file uploads to S3 for import processing.
        
        Args:
            local_files: List of local file paths
            mapping_id: ID of the mapping configuration
            upload_prefix: Prefix for S3 object names
            
        Returns:
            Dictionary with upload suggestions and metadata
        """
        if not self.s3_upload_service:
            raise ValueError("S3 upload service not configured")
        
        try:
            # Load mapping configuration
            if self.mapping_adapter is None:
                from ..mapping_consumer.mapping_adapter import MappingAdapter
                self.mapping_adapter = MappingAdapter()
            execution_config = self.mapping_adapter.translate_to_execution_config(mapping_id)
            
            # Match files to datasets
            batch_result = self.file_matcher.match_files_to_datasets(local_files, execution_config)
            
            upload_suggestions = []
            
            for match in batch_result.successful_matches:
                if match.is_valid:
                    # Suggest upload path based on dataset and organization
                    suggested_path = f"{upload_prefix}/{execution_config.organization}/{match.dataset_name}/{match.file_info.filename}"
                    
                    upload_suggestions.append({
                        'local_path': match.file_info.file_path,
                        'suggested_s3_path': suggested_path,
                        'dataset_name': match.dataset_name,
                        'confidence': match.confidence,
                        'file_size': match.file_info.size,
                        'ready_for_upload': True
                    })
            
            # Handle unmatched files
            for file_info in batch_result.unmatched_files:
                upload_suggestions.append({
                    'local_path': file_info.file_path,
                    'suggested_s3_path': f"{upload_prefix}/{execution_config.organization}/unmatched/{file_info.filename}",
                    'dataset_name': None,
                    'confidence': 0.0,
                    'file_size': file_info.size,
                    'ready_for_upload': False,
                    'issues': ['File could not be matched to any dataset']
                })
            
            return {
                'mapping_id': mapping_id,
                'upload_suggestions': upload_suggestions,
                'ready_files': len([s for s in upload_suggestions if s['ready_for_upload']]),
                'total_files': len(upload_suggestions),
                'estimated_upload_size': sum(s['file_size'] for s in upload_suggestions),
                'recommendations': self._generate_upload_recommendations(upload_suggestions)
            }
            
        except Exception as e:
            if self.error_manager:
                self.error_manager.record_error(
                    error_code="FILE_UPLOAD_SUGGESTION_ERROR",
                    error_type="IntegrationError",
                    error_message=f"Failed to suggest file uploads for mapping {mapping_id}: {str(e)}",
                    error_category="integration",
                    context={"mapping_id": mapping_id, "file_count": len(local_files)}
                )
            raise
    
    def _generate_matching_recommendations(self, 
                                         batch_result: BatchMatchResult,
                                         execution_config) -> List[str]:
        """Generate recommendations based on matching results"""
        recommendations = []
        
        # Low match rate
        if batch_result.match_rate < 0.5:
            recommendations.append(
                "Low match rate detected. Consider reviewing file naming conventions or dataset names."
            )
        
        # Unmatched files
        if batch_result.unmatched_files:
            recommendations.append(
                f"{len(batch_result.unmatched_files)} files could not be matched to any dataset. "
                "Consider renaming files or adding missing datasets to the mapping."
            )
        
        # Unmatched datasets
        if batch_result.unmatched_datasets:
            recommendations.append(
                f"{len(batch_result.unmatched_datasets)} datasets have no matching files: "
                f"{', '.join(batch_result.unmatched_datasets)}. "
                "Consider adding files or removing unused datasets."
            )
        
        # Failed matches
        if batch_result.failed_matches:
            recommendations.append(
                f"{len(batch_result.failed_matches)} files matched but failed validation. "
                "Check file structure and column requirements."
            )
        
        # High confidence matches
        high_confidence_matches = [
            match for match in batch_result.successful_matches 
            if match.confidence >= 0.9
        ]
        
        if high_confidence_matches:
            recommendations.append(
                f"{len(high_confidence_matches)} files have high-confidence matches and are ready for import."
            )
        
        return recommendations
    
    def _generate_upload_recommendations(self, upload_suggestions: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations for file uploads"""
        recommendations = []
        
        ready_files = [s for s in upload_suggestions if s['ready_for_upload']]
        total_size = sum(s['file_size'] for s in upload_suggestions)
        
        if ready_files:
            recommendations.append(f"{len(ready_files)} files are ready for upload.")
        
        if total_size > 100 * 1024 * 1024:  # 100MB
            recommendations.append(
                f"Large upload detected ({total_size / (1024*1024):.1f}MB). "
                "Consider batch uploading or compression."
            )
        
        unmatched_files = [s for s in upload_suggestions if not s['ready_for_upload']]
        if unmatched_files:
            recommendations.append(
                f"{len(unmatched_files)} files could not be matched and will be uploaded to 'unmatched' folder."
            )
        
        return recommendations
    
    def _extract_dataset_requirements(self, dataset_config) -> Dict[str, Any]:
        """Extract requirements from dataset configuration"""
        return {
            'required_columns': [col.column_name for col in dataset_config.columns],
            'expected_types': {
                col.column_name: col.datatype for col in dataset_config.columns
            },
            'primary_keys': dataset_config.primary_key_columns,
            'dependencies': dataset_config.dependencies
        }
    
    def _serialize_match_result(self, match_result: MatchResult) -> Dict[str, Any]:
        """Serialize match result for JSON response"""
        return {
            'file_path': match_result.file_info.file_path,
            'filename': match_result.file_info.filename,
            'dataset_name': match_result.dataset_name,
            'confidence': match_result.confidence,
            'matching_strategy': match_result.matching_strategy.value,
            'is_valid': match_result.is_valid,
            'reasons': match_result.reasons,
            'validation_issues': match_result.validation_issues,
            'file_info': self._serialize_file_info(match_result.file_info),
            'metadata': match_result.metadata
        }
    
    def _serialize_file_info(self, file_info) -> Dict[str, Any]:
        """Serialize file info for JSON response"""
        return {
            'file_path': file_info.file_path,
            'filename': file_info.filename,
            'basename': file_info.basename,
            'extension': file_info.extension,
            'size': file_info.size,
            'exists': file_info.exists,
            'is_readable': file_info.is_readable,
            'directory': file_info.directory,
            'relative_path': file_info.relative_path
        }


def create_file_matching_integration(
    error_manager: Optional['ErrorManager'] = None,
    s3_upload_service: Optional['S3UploadService'] = None
) -> FileMatchingIntegration:
    """
    Factory function to create FileMatchingIntegration instance.
    
    Args:
        error_manager: Optional error manager instance
        s3_upload_service: Optional S3 upload service instance
        
    Returns:
        FileMatchingIntegration instance
    """
    return FileMatchingIntegration(
        error_manager=error_manager,
        s3_upload_service=s3_upload_service
    )


def match_files_quick(mapping_id: int, 
                     selected_files: List[str],
                     base_directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick file matching utility function.
    
    Args:
        mapping_id: ID of the mapping configuration
        selected_files: List of file paths to match
        base_directory: Optional base directory for resolving relative paths
        
    Returns:
        Dictionary with basic matching results
    """
    integration = create_file_matching_integration()
    return integration.match_files_for_mapping(mapping_id, selected_files, base_directory)


def validate_files_quick(file_dataset_pairs: List[Tuple[str, str]],
                        mapping_id: int,
                        base_directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick file validation utility function.
    
    Args:
        file_dataset_pairs: List of (file_path, dataset_name) tuples
        mapping_id: ID of the mapping configuration
        base_directory: Optional base directory for resolving relative paths
        
    Returns:
        Dictionary with validation results
    """
    integration = create_file_matching_integration()
    return integration.validate_files_for_datasets(file_dataset_pairs, mapping_id, base_directory)