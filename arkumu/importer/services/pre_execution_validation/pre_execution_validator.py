"""
Pre-execution validation service for the import pipeline.

This module provides comprehensive validation of mapping configurations and files
before execution to ensure successful import operations.
"""

import os
import csv
import json
import logging
import time
import io
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass

import polars as pl

from .validation_result import (
    PreExecutionValidationResult,
    FileValidationResult,
    ColumnMappingValidationResult,
    RelationshipValidationResult,
    ResourceEstimate,
    ValidationIssue,
    ValidationSeverity,
    ValidationCategory,
    ValidationMode,
    ValidationErrorCodes
)

# Import existing services
from arkumu.importer.services.file_matching.file_dataset_matcher import FileDatasetMatcher
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.validation.validation_utils import ValidationReport
from arkumu.storage.services.bucket_service import BucketService
from arkumu.metadata.services.mapping.mapping_coordinator import MappingCoordinator
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin

logger = logging.getLogger(__name__)


class PreExecutionValidator:
    """
    Comprehensive pre-execution validation service.
    
    Provides validation of mapping configurations against files before execution,
    including file structure validation, column mapping validation, relationship
    validation, and resource estimation.
    """
    
    def __init__(self, 
                 mapping_adapter: Optional[MappingAdapter] = None,
                 file_matcher: Optional[FileDatasetMatcher] = None,
                 validation_mode: ValidationMode = ValidationMode.STRICT,
                 bucket_service: Optional[BucketService] = None):
        """
        Initialize the pre-execution validator.
        
        Args:
            mapping_adapter: Optional mapping adapter for loading configurations
            file_matcher: Optional file matcher for file validation
            validation_mode: Validation mode (strict, warning_only, lenient)
            bucket_service: Optional bucket service for S3 file access
        """
        self.mapping_adapter = mapping_adapter or MappingAdapter()
        self.file_matcher = file_matcher or FileDatasetMatcher()
        self.validation_mode = validation_mode
        self.bucket_service = bucket_service or BucketService()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Initialize the mapping coordinator mixin for validation
        self.mapping_coordinator = CSVMappingCoordinatorMixin()
        
        # Configuration
        self.max_file_size = 500 * 1024 * 1024  # 500MB
        self.max_row_count = 1_000_000  # 1M rows
        self.supported_encodings = ['utf-8', 'latin1', 'cp1252']
        self.supported_delimiters = [',', ';', '\t', '|']
        
        # Performance thresholds
        self.performance_thresholds = {
            'execution_time_warning': 300,  # 5 minutes
            'execution_time_critical': 1800,  # 30 minutes
            'memory_warning': 1024,  # 1GB
            'memory_critical': 4096,  # 4GB
            'disk_warning': 5120,  # 5GB
            'disk_critical': 20480  # 20GB
        }
    
    def validate_mapping_execution(self, 
                                 mapping_config: Dict[str, Any], 
                                 file_paths: List[str],
                                 organization_code: Optional[str] = None,
                                 request = None,
                                 organization_id: Optional[int] = None) -> PreExecutionValidationResult:
        """
        Validate mapping execution against provided files.
        
        Args:
            mapping_config: Mapping configuration dictionary
            file_paths: List of file paths to validate (can be S3 paths)
            organization_code: Optional organization code for S3 bucket access
            
        Returns:
            PreExecutionValidationResult with comprehensive validation results
        """
        start_time = time.time()
        
        self.logger.info(f"Starting pre-execution validation for {len(file_paths)} files")
        
        # Create result container
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=self.validation_mode,
            overall_confidence=0.0
        )
        
        try:
            # 1. Validate mapping configuration
            self._validate_mapping_configuration(mapping_config, result)
            
            # 2. Validate file structures
            file_validation_results = []
            for file_path in file_paths:
                file_result = self.validate_file_structure(file_path, mapping_config, organization_code)
                file_validation_results.append(file_result)
                result.all_issues.extend(file_result.issues)
            
            result.file_validation_results = file_validation_results
            
            # 3. Validate column mappings at dataset level using mixin
            column_mapping_result = self.validate_dataset_column_mappings_with_mixin(
                file_validation_results,
                mapping_config,
                organization_code,
                request,
                organization_id
            )
            
            self.logger.info(f"Column mapping result: missing_required={column_mapping_result.missing_required_columns}, "
                           f"unmapped={column_mapping_result.unmapped_columns}, "
                           f"mapped={len(column_mapping_result.mapped_columns)}")
            result.column_mapping_result = column_mapping_result
            result.all_issues.extend(column_mapping_result.issues)
            
            # 4. Validate relationships
            relationship_result = self.validate_relationship_requirements(mapping_config)
            result.relationship_validation_result = relationship_result
            result.all_issues.extend(relationship_result.issues)
            
            # 5. Estimate resource requirements
            file_sizes = []
            for fp in file_paths:
                size = self._get_file_size(fp, organization_code)
                if size > 0:
                    file_sizes.append(size)
            resource_estimate = self.estimate_resource_requirements(mapping_config, file_sizes)
            result.resource_estimate = resource_estimate
            
            # 6. Generate execution recommendations
            self._generate_execution_recommendations(result)
            
            # 7. Determine overall validity
            result.is_valid = self._determine_overall_validity(result)
            
        except Exception as e:
            self.logger.error(f"Pre-execution validation failed: {str(e)}")
            result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.CRITICAL,
                category=ValidationCategory.CONFIGURATION,
                message=f"Validation failed: {str(e)}",
                details={"exception": str(e)}
            ))
            result.is_valid = False
        
        finally:
            result.validation_duration = time.time() - start_time
            self.logger.info(f"Pre-execution validation completed in {result.validation_duration:.2f}s")
        
        return result
    
    def validate_file_structure(self, 
                               file_path: str, 
                               dataset_config: Dict[str, Any],
                               organization_code: Optional[str] = None) -> FileValidationResult:
        """
        Validate file structure against dataset configuration.
        
        Args:
            file_path: Path to the file to validate (can be S3 path)
            dataset_config: Dataset configuration dictionary
            organization_code: Optional organization code for S3 bucket access
            
        Returns:
            FileValidationResult with validation details
        """
        result = FileValidationResult(
            file_path=file_path,
            is_valid=True,
            file_size=0,
            column_count=0,
            row_count=0
        )
        
        try:
            # Determine if this is an S3 path or local file
            is_s3_path = self._is_s3_path(file_path)
            
            # Basic file checks
            if is_s3_path:
                # Validate S3 file
                if not organization_code:
                    # Try to extract organization from mapping config
                    organization_code = dataset_config.get('institution', dataset_config.get('organization'))
                    
                if not organization_code:
                    result.is_valid = False
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.MISSING_CONFIGURATION,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message="Organization code required for S3 file validation",
                        file_path=file_path
                    ))
                    return result
                
                # Check if file exists in S3
                bucket_name = self.bucket_service.get_organization_bucket(organization_code)
                file_exists, file_size = self._check_s3_file_exists(bucket_name, file_path)
                
                if not file_exists:
                    result.is_valid = False
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_NOT_FOUND,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"File not found in S3: {file_path}",
                        file_path=file_path
                    ))
                    return result
                
                result.file_size = file_size
            else:
                # Local file validation
                if not os.path.exists(file_path):
                    result.is_valid = False
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_NOT_FOUND,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"File not found: {file_path}",
                        file_path=file_path
                    ))
                    return result
                
                if not os.access(file_path, os.R_OK):
                    result.is_valid = False
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_NOT_READABLE,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"File not readable: {file_path}",
                        file_path=file_path
                    ))
                    return result
                
                # File size validation
                file_size = os.path.getsize(file_path)
                result.file_size = file_size
            
            if file_size == 0:
                result.is_valid = False
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.FILE_EMPTY,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"File is empty: {file_path}",
                    file_path=file_path
                ))
                return result
            
            if file_size > self.max_file_size:
                severity = ValidationSeverity.ERROR if self.validation_mode == ValidationMode.STRICT else ValidationSeverity.WARNING
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.FILE_TOO_LARGE,
                    severity=severity,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"File is too large: {file_size / (1024*1024):.1f}MB",
                    file_path=file_path,
                    suggested_fix="Consider splitting the file into smaller chunks"
                ))
                if severity == ValidationSeverity.ERROR:
                    result.is_valid = False
            
            # Detect file format and validate structure
            file_extension = Path(file_path).suffix.lower()
            
            if file_extension in ['.csv', '.tsv', '.txt']:
                # Use unified Polars-based validation for both S3 and local files
                dataset_config_with_org = dict(dataset_config)
                dataset_config_with_org['organization_code'] = organization_code
                self._validate_csv_file_structure_with_polars(file_path, dataset_config_with_org, result)
            elif file_extension == '.json':
                if is_s3_path:
                    self._validate_json_file_structure_s3(file_path, dataset_config, result, organization_code)
                else:
                    self._validate_json_file_structure(file_path, dataset_config, result)
            else:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"Unsupported file format: {file_extension}",
                    file_path=file_path
                ))
        
        except Exception as e:
            self.logger.error(f"File structure validation failed for {file_path}: {str(e)}")
            result.is_valid = False
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"Validation failed: {str(e)}",
                file_path=file_path,
                details={"exception": str(e)}
            ))
        
        return result
    
    def validate_dataset_column_mappings_with_mixin(self, 
                                                  file_validation_results: List[FileValidationResult],
                                                  mapping_config: Dict[str, Any],
                                                  organization_code: Optional[str] = None,
                                                  request = None,
                                                  organization_id: Optional[int] = None) -> ColumnMappingValidationResult:
        """
        Validate column mappings using the CSVMappingCoordinatorMixin validation method.
        
        This is the preferred method as it reuses the mixin's validation logic.
        """
        result = ColumnMappingValidationResult(
            mapped_columns={},
            unmapped_columns=[],
            missing_required_columns=[],
            type_mismatches=[],
            transformation_warnings=[],
            coverage_percentage=0.0
        )
        
        if not request or not organization_id:
            self.logger.warning("Cannot use mixin validation without request and organization_id, falling back to config-based validation")
            return self.validate_dataset_column_mappings(file_validation_results, mapping_config, organization_code, request, organization_id)
        
        try:
            # Extract all file columns from validation results
            all_file_columns = set()
            for file_result in file_validation_results:
                if file_result.is_valid:
                    try:
                        file_columns = self._extract_file_columns(file_result.file_path, organization_code)
                        all_file_columns.update(file_columns)
                    except Exception as e:
                        self.logger.warning(f"Could not extract columns from {file_result.file_path}: {e}")
            
            # Use the mixin's validation method
            validation_result = self.mapping_coordinator.validate_mapping_structure(
                request, organization_id, list(all_file_columns)
            )
            
            # Convert to our result format
            result.mapped_columns = validation_result['mapped_columns']
            result.unmapped_columns = validation_result['unmapped_columns']
            result.missing_required_columns = validation_result['missing_required_columns']
            result.coverage_percentage = validation_result['coverage_percentage']
            
            # Convert issues to ValidationIssue objects
            for issue in validation_result['issues']:
                result.issues.append(ValidationIssue(
                    code=issue['code'],
                    severity=ValidationSeverity.ERROR if issue['severity'] == 'ERROR' else ValidationSeverity.WARNING,
                    category=ValidationCategory.COLUMN_MAPPING,
                    message=issue['message'],
                    column_name=issue.get('column_name'),
                    suggested_fix=issue.get('suggested_fix')
                ))
            
            self.logger.info(f"Mixin validation: {len(result.mapped_columns)} mapped, {len(result.unmapped_columns)} unmapped, {len(result.missing_required_columns)} missing")
            
        except Exception as e:
            self.logger.error(f"Mixin validation failed: {str(e)}")
            # Fall back to the original method
            return self.validate_dataset_column_mappings(file_validation_results, mapping_config, organization_code, request, organization_id)
        
        return result

    def validate_dataset_column_mappings(self, 
                                       file_validation_results: List[FileValidationResult],
                                       mapping_config: Dict[str, Any],
                                       organization_code: Optional[str] = None,
                                       request = None,
                                       organization_id: Optional[int] = None) -> ColumnMappingValidationResult:
        """
        Validate column mappings at the dataset level - matching files to datasets
        and validating columns within each dataset context.
        """
        result = ColumnMappingValidationResult(
            mapped_columns={},
            unmapped_columns=[],
            missing_required_columns=[],
            type_mismatches=[],
            transformation_warnings=[],
            coverage_percentage=0.0
        )
        
        try:
            # Use the mixin's method to get workspace_columns if request and organization_id are provided
            if request and organization_id:
                workspace_columns = self.get_workspace_columns(request, organization_id)
                self.logger.info(f"Retrieved workspace_columns using mixin: {len(workspace_columns)} columns")
            else:
                # Fallback to extracting from mapping config
                workspace_columns = mapping_config.get('workspace_columns', {})
                self.logger.info(f"Using workspace_columns from mapping config: {len(workspace_columns)} columns")
            
            selected_datasets = mapping_config.get('selected_datasets', [])
            self.logger.info(f"Selected datasets: {selected_datasets}")
            
            # If selected_datasets is empty, extract from workspace_columns
            if not selected_datasets:
                dataset_names = set()
                for key in workspace_columns.keys():
                    if '::' in key:
                        parts = key.split('::')
                        if len(parts) >= 2:
                            dataset_names.add(parts[1])
                selected_datasets = list(dataset_names)
                self.logger.info(f"Extracted {len(selected_datasets)} datasets from workspace_columns: {selected_datasets}")
            
            # Group files by dataset
            dataset_files = {}
            for file_result in file_validation_results:
                if file_result.is_valid:
                    dataset_name = self._extract_dataset_name_from_file_path(file_result.file_path)
                    if dataset_name:
                        if dataset_name not in dataset_files:
                            dataset_files[dataset_name] = []
                        dataset_files[dataset_name].append(file_result.file_path)
            
            self.logger.info(f"Grouped files into {len(dataset_files)} datasets: {list(dataset_files.keys())}")
            
            # Validate each dataset
            all_mapped_columns = {}
            all_unmapped_columns = []
            all_missing_required = []
            
            for dataset_name in selected_datasets:
                dataset_result = self._validate_dataset_columns(
                    dataset_name, 
                    dataset_files.get(dataset_name, []),
                    workspace_columns,
                    organization_code
                )
                
                # Aggregate results
                all_mapped_columns.update(dataset_result.mapped_columns)
                all_unmapped_columns.extend(dataset_result.unmapped_columns)
                all_missing_required.extend(dataset_result.missing_required_columns)
                result.issues.extend(dataset_result.issues)
            
            # Set final results
            result.mapped_columns = all_mapped_columns
            result.unmapped_columns = all_unmapped_columns
            result.missing_required_columns = all_missing_required
            
            # Calculate coverage
            total_columns = len(all_mapped_columns) + len(all_unmapped_columns)
            if total_columns > 0:
                result.coverage_percentage = (len(all_mapped_columns) / total_columns) * 100
            
        except Exception as e:
            self.logger.error(f"Dataset column mapping validation failed: {str(e)}")
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message=f"Dataset column mapping validation failed: {str(e)}",
                details={"exception": str(e)}
            ))
        
        return result
    
    def _extract_dataset_name_from_file_path(self, file_path: str) -> Optional[str]:
        """Extract dataset name from file path (e.g., 'AkteurIn.csv' -> 'AkteurIn')"""
        from pathlib import Path
        
        # Get filename without extension
        filename = Path(file_path).stem
        
        # Handle common dataset naming patterns
        if filename.startswith('Dataset_'):
            # Remove 'Dataset_' prefix
            return filename[8:]  # 'Dataset_123' -> '123'
        
        # For S3 paths like 'metadata/AkteurIn.csv'
        if '/' in filename:
            filename = filename.split('/')[-1]
        
        return filename
    
    def _validate_dataset_columns(self, 
                                dataset_name: str,
                                dataset_files: List[str],
                                workspace_columns: Dict[str, Any],
                                organization_code: Optional[str] = None) -> ColumnMappingValidationResult:
        """Validate column mappings for a specific dataset"""
        result = ColumnMappingValidationResult(
            mapped_columns={},
            unmapped_columns=[],
            missing_required_columns=[],
            type_mismatches=[],
            transformation_warnings=[],
            coverage_percentage=0.0
        )
        
        try:
            # Extract columns from dataset files
            dataset_columns = set()
            for file_path in dataset_files:
                try:
                    file_columns = self._extract_file_columns(file_path, organization_code)
                    dataset_columns.update(file_columns)
                except Exception as e:
                    self.logger.warning(f"Could not extract columns from {file_path}: {e}")
            
            # Find mapped columns for this dataset
            required_columns = set()
            mapped_columns = {}
            
            self.logger.info(f"Looking for columns for dataset {dataset_name}")
            self.logger.info(f"Sample workspace_columns keys: {list(workspace_columns.keys())[:10]}")
            
            for key, value in workspace_columns.items():
                # Check if this column belongs to the current dataset
                if '::' in key:
                    parts = key.split('::')
                    if len(parts) >= 3:
                        # Extract dataset name from parts[1], handling both "dataset.csv" and "dataset" formats
                        workspace_dataset_name = parts[1]
                        if workspace_dataset_name.endswith('.csv'):
                            workspace_dataset_name = workspace_dataset_name[:-4]
                        
                        if workspace_dataset_name == dataset_name:
                            column_name = parts[2]
                            if isinstance(value, dict):
                                arkumu_type = value.get('arkumu_type', '')
                                if arkumu_type:
                                    required_columns.add(column_name)
                                    mapped_columns[column_name] = arkumu_type
                                    self.logger.debug(f"Found mapped column: {column_name} -> {arkumu_type}")
                            elif isinstance(value, str) and value:
                                required_columns.add(column_name)
                                mapped_columns[column_name] = value
                                self.logger.debug(f"Found mapped column: {column_name} -> {value}")
                elif key == dataset_name or key.startswith(dataset_name):
                    # Direct dataset column mapping
                    if isinstance(value, dict):
                        arkumu_type = value.get('arkumu_type', '')
                        if arkumu_type:
                            required_columns.add(key)
                            mapped_columns[key] = arkumu_type
                            self.logger.debug(f"Found mapped column: {key} -> {arkumu_type}")
                    elif isinstance(value, str) and value:
                        required_columns.add(key)
                        mapped_columns[key] = value
                        self.logger.debug(f"Found mapped column: {key} -> {value}")
                elif key in dataset_columns:
                    # Direct column name match (for GUI format)
                    if isinstance(value, dict):
                        arkumu_type = value.get('arkumu_type', '')
                        if arkumu_type:
                            required_columns.add(key)
                            mapped_columns[key] = arkumu_type
                            self.logger.debug(f"Found mapped column: {key} -> {arkumu_type}")
                    elif isinstance(value, str) and value:
                        required_columns.add(key)
                        mapped_columns[key] = value
                        self.logger.debug(f"Found mapped column: {key} -> {value}")
            
            self.logger.info(f"Dataset {dataset_name}: found {len(required_columns)} required columns, {len(mapped_columns)} mapped columns")
            self.logger.info(f"Required columns: {list(required_columns)[:10]}")
            self.logger.info(f"File columns: {list(dataset_columns)[:10]}")
            
            # Check for missing required columns
            missing_required = required_columns - dataset_columns
            result.missing_required_columns = list(missing_required)
            
            # Check for unmapped columns
            unmapped = dataset_columns - required_columns
            result.unmapped_columns = list(unmapped)
            
            # Set mapped columns (only those that exist in files)
            result.mapped_columns = {col: mapped_columns.get(col, '') 
                                   for col in dataset_columns if col in mapped_columns}
            
            # Calculate coverage
            if dataset_columns:
                result.coverage_percentage = (len(result.mapped_columns) / len(dataset_columns)) * 100
            
            # Generate issues
            for missing_col in missing_required:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.COLUMN_MAPPING,
                    message=f"Required column missing in dataset {dataset_name}: {missing_col}",
                    column_name=missing_col,
                    suggested_fix="Add the missing column to the data files or update the mapping"
                ))
            
            for unmapped_col in unmapped:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.UNMAPPED_REQUIRED_COLUMN,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.COLUMN_MAPPING,
                    message=f"Column not mapped in dataset {dataset_name}: {unmapped_col}",
                    column_name=unmapped_col,
                    suggested_fix="Consider mapping this column if it contains useful data"
                ))
            
            self.logger.info(f"Dataset {dataset_name}: {len(result.mapped_columns)} mapped, {len(result.unmapped_columns)} unmapped, {len(result.missing_required_columns)} missing")
            
        except Exception as e:
            self.logger.error(f"Dataset column validation failed for {dataset_name}: {str(e)}")
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message=f"Dataset column validation failed for {dataset_name}: {str(e)}",
                details={"exception": str(e)}
            ))
        
        return result
    
    def validate_column_mapping(self, 
                              file_columns: List[str], 
                              mapping_columns: Dict[str, Any],
                              organization_code: Optional[str] = None) -> ColumnMappingValidationResult:
        """
        Validate column mapping between files and mapping configuration.
        
        Args:
            file_columns: List of column names from files
            mapping_columns: Mapping configuration for columns
            
        Returns:
            ColumnMappingValidationResult with mapping validation details
        """
        result = ColumnMappingValidationResult(
            mapped_columns={},
            unmapped_columns=[],
            missing_required_columns=[],
            type_mismatches=[],
            transformation_warnings=[],
            coverage_percentage=0.0
        )
        
        try:
            # Extract column mappings from configuration - check different possible locations
            self.logger.info(f"Mapping config keys: {list(mapping_columns.keys())}")
            
            # Extract column mappings from workspace_columns structure
            workspace_columns = mapping_columns.get('workspace_columns', {})
            selected_datasets = mapping_columns.get('selected_datasets', [])
            
            self.logger.info(f"Found workspace_columns for {len(workspace_columns)} columns")
            self.logger.info(f"Selected datasets: {selected_datasets}")
            
            # If selected_datasets is empty, use all datasets from workspace_columns
            if not selected_datasets:
                # Extract unique dataset names from workspace_columns keys
                dataset_names = set()
                if isinstance(workspace_columns, dict):
                    for key in workspace_columns.keys():
                        if '::' in key:
                            parts = key.split('::')
                            if len(parts) >= 2:
                                dataset_names.add(parts[1])  # Extract dataset name from "org::dataset::column"
                selected_datasets = list(dataset_names)
                self.logger.info(f"No selected datasets specified, extracted {len(selected_datasets)} datasets from workspace_columns")
            
            required_columns = set()
            mapped_columns = {}
            
            # Process workspace columns structure - handles multiple formats
            if isinstance(workspace_columns, dict):
                for key, value in workspace_columns.items():
                    # Handle different key formats and value types
                    if '::' in key:
                        # Format: "org::dataset::column" (MappingCoordinator format)
                        parts = key.split('::')
                        if len(parts) >= 3:
                            dataset_name = parts[1]
                            column_name = parts[2]
                        else:
                            self.logger.warning(f"Invalid column_id format: {key}")
                            continue
                            
                        # Only process if dataset is selected
                        if dataset_name not in selected_datasets:
                            self.logger.debug(f"Skipping column {column_name} - dataset {dataset_name} not in selected datasets")
                            continue
                            
                        # Extract mapping from column config
                        if isinstance(value, dict):
                            arkumu_type = value.get('arkumu_type', '')
                            if arkumu_type:
                                required_columns.add(column_name)
                                mapped_columns[column_name] = arkumu_type
                                self.logger.debug(f"Mapped column: {column_name} -> {arkumu_type}")
                        elif isinstance(value, str) and value:
                            required_columns.add(column_name)
                            mapped_columns[column_name] = value
                            self.logger.debug(f"Mapped column: {column_name} -> {value}")
                            
                    elif key.startswith('Dataset_'):
                        # Format: "Dataset_123" -> "arkumu_type_123" (test/internal format)
                        # This represents a dataset, not a column name
                        # Skip unless it's also a real column name in the files
                        continue
                        
                    else:
                        # Assume key is an actual column name (GUI format)
                        column_name = key
                        
                        # Extract mapping from column config
                        if isinstance(value, dict):
                            arkumu_type = value.get('arkumu_type', '')
                            if arkumu_type:
                                required_columns.add(column_name)
                                mapped_columns[column_name] = arkumu_type
                                self.logger.debug(f"Mapped column: {column_name} -> {arkumu_type}")
                        elif isinstance(value, str) and value:
                            required_columns.add(column_name)
                            mapped_columns[column_name] = value
                            self.logger.debug(f"Mapped column: {column_name} -> {value}")
            
            # Also check legacy mappings format for backward compatibility
            if 'mappings' in mapping_columns:
                self.logger.info("Found legacy 'mappings' format, processing as fallback")
                for mapping_rule in mapping_columns['mappings']:
                    source_column = mapping_rule.get('source_column')
                    target_property = mapping_rule.get('property')
                    
                    if source_column:
                        required_columns.add(source_column)
                        mapped_columns[source_column] = target_property
                        
                        # Check for object_properties (sub-mappings)
                        if 'object_properties' in mapping_rule:
                            for sub_rule in mapping_rule['object_properties']:
                                sub_source = sub_rule.get('source_column')
                                sub_target = sub_rule.get('property')
                                if sub_source:
                                    required_columns.add(sub_source)
                                    mapped_columns[sub_source] = sub_target
            
            # For file-based validation, we need to check against actual file columns
            if isinstance(file_columns, list) and len(file_columns) > 0:
                # If file_columns is a list of file paths, load columns from files
                is_file_path = isinstance(file_columns[0], str) and (os.path.exists(file_columns[0]) or self._is_s3_path(file_columns[0]))
                if is_file_path:
                    actual_columns = set()
                    for file_path in file_columns:
                        file_cols = self._extract_file_columns(file_path, organization_code)
                        actual_columns.update(file_cols)
                else:
                    # Direct column list
                    actual_columns = set(file_columns)
            else:
                actual_columns = set()
            
            # Check for missing required columns
            missing_required = required_columns - actual_columns
            result.missing_required_columns = list(missing_required)
            
            # Check for unmapped columns
            unmapped = actual_columns - required_columns
            result.unmapped_columns = list(unmapped)
            
            # Set mapped columns
            result.mapped_columns = {col: mapped_columns.get(col, '') 
                                   for col in actual_columns if col in mapped_columns}
            
            # Calculate coverage percentage
            if actual_columns:
                result.coverage_percentage = (len(result.mapped_columns) / len(actual_columns)) * 100
            
            # Generate validation issues
            for missing_col in missing_required:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.COLUMN_MAPPING,
                    message=f"Required column missing: {missing_col}",
                    column_name=missing_col,
                    suggested_fix="Add the missing column to the data files or update the mapping"
                ))
            
            for unmapped_col in unmapped:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.UNMAPPED_REQUIRED_COLUMN,
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.COLUMN_MAPPING,
                    message=f"Column not mapped: {unmapped_col}",
                    column_name=unmapped_col,
                    suggested_fix="Consider mapping this column if it contains useful data"
                ))
        
        except Exception as e:
            self.logger.error(f"Column mapping validation failed: {str(e)}")
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.COLUMN_MAPPING,
                message=f"Column mapping validation failed: {str(e)}",
                details={"exception": str(e)}
            ))
        
        return result
    
    def validate_relationship_requirements(self, 
                                         mapping_config: Dict[str, Any]) -> RelationshipValidationResult:
        """
        Validate relationship requirements in mapping configuration.
        
        Args:
            mapping_config: Mapping configuration dictionary
            
        Returns:
            RelationshipValidationResult with relationship validation details
        """
        result = RelationshipValidationResult(
            valid_relationships=[],
            invalid_relationships=[],
            missing_dependencies=[],
            circular_dependencies=[],
            foreign_key_issues=[],
            orphaned_records_estimate=0
        )
        
        try:
            # Extract relationship information from mapping
            relationships = []
            dependencies = {}
            
            # Check workspace_columns structure for FK relationships
            workspace_columns = mapping_config.get('workspace_columns', {})
            selected_datasets = mapping_config.get('selected_datasets', [])
            
            # If selected_datasets is empty, use all datasets from workspace_columns
            if not selected_datasets:
                selected_datasets = list(workspace_columns.keys())
            
            for dataset_name, dataset_columns in workspace_columns.items():
                if dataset_name not in selected_datasets:
                    continue
                
                # Handle different types of dataset_columns values
                if isinstance(dataset_columns, dict):
                    for column_name, column_config in dataset_columns.items():
                        # Check if this column has external ontology or FK relationships
                        if isinstance(column_config, dict) and column_config.get('is_external_ontology', False):
                            external_ontology = column_config.get('external_ontology', {})
                            if external_ontology:
                                relationships.append({
                                    'source_column': column_name,
                                    'target_table': external_ontology.get('ontology_type', 'external'),
                                    'rule': column_config,
                                    'type': 'external_ontology'
                                })
                # If dataset_columns is a string, skip relationship extraction
            
            # Also check fk_relationships structure
            fk_relationships = mapping_config.get('fk_relationships', {})
            for fk_id, fk_config in fk_relationships.items():
                source_column = fk_config.get('source_column')
                target_dataset = fk_config.get('target_dataset')
                
                if source_column and target_dataset:
                    relationships.append({
                        'source_column': source_column,
                        'target_table': target_dataset,
                        'rule': fk_config,
                        'type': 'foreign_key'
                    })
                    
                    # Track dependencies
                    if source_column not in dependencies:
                        dependencies[source_column] = []
                    dependencies[source_column].append(target_dataset)
            
            # Fallback to legacy mappings format
            if 'mappings' in mapping_config:
                for mapping_rule in mapping_config['mappings']:
                    source_column = mapping_rule.get('source_column')
                    object_column = mapping_rule.get('object_column')
                    
                    if object_column:
                        # This is a relationship mapping
                        relationships.append({
                            'source_column': source_column,
                            'target_table': object_column,
                            'rule': mapping_rule,
                            'type': 'legacy_mapping'
                        })
                        
                        # Track dependencies
                        if source_column not in dependencies:
                            dependencies[source_column] = []
                        dependencies[source_column].append(object_column)
            
            # Validate each relationship
            for relationship in relationships:
                try:
                    # Check if target table exists (basic validation)
                    target_table = relationship['target_table']
                    
                    # In a full implementation, this would check against actual database
                    # For now, we'll do basic validation
                    if self._is_valid_reference_table(target_table):
                        result.valid_relationships.append(f"{relationship['source_column']} -> {target_table}")
                    else:
                        result.invalid_relationships.append(f"{relationship['source_column']} -> {target_table}")
                        result.issues.append(ValidationIssue(
                            code=ValidationErrorCodes.REFERENCE_TABLE_MISSING,
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.RELATIONSHIP_VALIDATION,
                            message=f"Reference table not found: {target_table}",
                            details={"relationship": relationship},
                            suggested_fix="Import the reference table before executing this mapping"
                        ))
                
                except Exception as e:
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.INVALID_RELATIONSHIP,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.RELATIONSHIP_VALIDATION,
                        message=f"Invalid relationship: {str(e)}",
                        details={"relationship": relationship, "exception": str(e)}
                    ))
            
            # Check for circular dependencies
            circular_deps = self._detect_circular_dependencies(dependencies)
            result.circular_dependencies = circular_deps
            
            for cycle in circular_deps:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.CIRCULAR_DEPENDENCY,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.RELATIONSHIP_VALIDATION,
                    message=f"Circular dependency detected: {' -> '.join(cycle)}",
                    details={"cycle": cycle},
                    suggested_fix="Review and break the circular dependency"
                ))
        
        except Exception as e:
            self.logger.error(f"Relationship validation failed: {str(e)}")
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.RELATIONSHIP_VALIDATION,
                message=f"Relationship validation failed: {str(e)}",
                details={"exception": str(e)}
            ))
        
        return result
    
    def estimate_resource_requirements(self, 
                                     mapping_config: Dict[str, Any], 
                                     file_sizes: List[int]) -> ResourceEstimate:
        """
        Estimate resource requirements for mapping execution.
        
        Args:
            mapping_config: Mapping configuration dictionary
            file_sizes: List of file sizes in bytes
            
        Returns:
            ResourceEstimate with resource estimation details
        """
        try:
            # Calculate basic metrics
            total_file_size = sum(file_sizes)
            max_file_size = max(file_sizes) if file_sizes else 0
            num_files = len(file_sizes)
            
            # Extract mapping complexity
            mappings = mapping_config.get('mappings', [])
            num_mappings = len(mappings)
            num_relationships = sum(1 for m in mappings if m.get('object_column'))
            num_transformations = sum(1 for m in mappings if m.get('object_properties'))
            
            # Calculate complexity score (1-10)
            complexity_score = min(10, max(1, (
                (num_mappings // 10) +
                (num_relationships // 5) +
                (num_transformations // 3) +
                (num_files // 5)
            )))
            
            # Estimate execution time (in seconds)
            base_time = 30  # Base processing time
            size_factor = total_file_size / (1024 * 1024)  # MB
            complexity_factor = complexity_score * 2
            
            estimated_time = base_time + (size_factor * 0.5) + complexity_factor
            
            # Estimate memory usage (in MB)
            base_memory = 128  # Base memory usage
            file_memory = max_file_size / (1024 * 1024) * 2  # 2x file size for processing
            mapping_memory = num_mappings * 0.5  # Memory per mapping
            
            estimated_memory = int(base_memory + file_memory + mapping_memory)
            
            # Estimate disk usage (in MB)
            processing_overhead = total_file_size * 0.3  # 30% overhead
            output_size = total_file_size * 0.8  # Estimated output size
            
            estimated_disk = int((total_file_size + processing_overhead + output_size) / (1024 * 1024))
            
            # CPU usage estimation
            estimated_cpu = min(100.0, 20.0 + (complexity_score * 5))
            
            # Recommendations
            parallel_processing = num_files > 2 and complexity_score < 7
            chunking_recommendation = None
            
            if max_file_size > 50 * 1024 * 1024:  # 50MB
                chunking_recommendation = {
                    "recommended": True,
                    "chunk_size": 10000,  # rows
                    "reason": "Large file size detected"
                }
            
            return ResourceEstimate(
                estimated_execution_time=estimated_time,
                estimated_memory_usage=estimated_memory,
                estimated_disk_usage=estimated_disk,
                estimated_cpu_usage=estimated_cpu,
                complexity_score=complexity_score,
                parallel_processing_recommendation=parallel_processing,
                chunking_recommendation=chunking_recommendation
            )
        
        except Exception as e:
            self.logger.error(f"Resource estimation failed: {str(e)}")
            # Return conservative estimates
            return ResourceEstimate(
                estimated_execution_time=300,  # 5 minutes
                estimated_memory_usage=1024,  # 1GB
                estimated_disk_usage=2048,  # 2GB
                estimated_cpu_usage=50.0,
                complexity_score=5
            )
    
    def _validate_mapping_configuration(self, 
                                      mapping_config: Dict[str, Any], 
                                      result: PreExecutionValidationResult):
        """Validate the mapping configuration structure"""
        required_fields = ['institution', 'domain', 'anchor_column', 'mappings']
        
        for field in required_fields:
            if field not in mapping_config:
                result.add_issue(ValidationIssue(
                    code=ValidationErrorCodes.MISSING_CONFIGURATION,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.CONFIGURATION,
                    message=f"Required configuration field missing: {field}",
                    details={"field": field}
                ))
        
        # Validate mappings structure
        mappings = mapping_config.get('mappings', [])
        if not isinstance(mappings, list):
            result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.INVALID_MAPPING_CONFIG,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.CONFIGURATION,
                message="Mappings must be a list of rules",
                details={"mappings_type": type(mappings).__name__}
            ))
    
    def _validate_csv_file_structure_with_polars(self, 
                                                file_path: str, 
                                                dataset_config: Dict[str, Any], 
                                                result: FileValidationResult):
        """Validate CSV file structure using exact same method as S3DirectDataAnalyzer"""
        import polars as pl
        import tempfile
        
        try:
            if self._is_s3_path(file_path):
                # S3 file - use exact same approach as S3DirectDataAnalyzer._read_s3_source_eager_sample
                organization_code = dataset_config.get('organization_code')
                if not organization_code:
                    result.add_issue(ValidationIssue(
                        code=ValidationErrorCodes.MISSING_CONFIGURATION,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.CONFIGURATION,
                        message="Organization code required for S3 file validation",
                        file_path=file_path
                    ))
                    return
                
                bucket_name = self.bucket_service.get_organization_bucket(organization_code)
                
                # Use exact same temp file approach as S3DirectDataAnalyzer
                with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp_file:
                    temp_file_path = temp_file.name
                
                try:
                    # Download file using S3 client (same as S3DirectDataAnalyzer)
                    self.bucket_service.base_s3_service.s3_client.download_file(
                        bucket_name, 
                        file_path, 
                        temp_file_path
                    )
                    
                    # Use exact same Polars call as S3DirectDataAnalyzer._read_s3_source_eager_sample
                    df = pl.read_csv(
                        temp_file_path, 
                        separator=';',  # Use semicolon as default like import_metadata.py
                        n_rows=1000,  # Sample for validation
                        ignore_errors=True  # Handle malformed rows gracefully
                    )
                    
                    # Set file info
                    result.file_size = os.path.getsize(temp_file_path)
                    result.encoding = 'utf-8'  # Polars handles encoding automatically
                    result.delimiter = ';'
                    result.column_count = len(df.columns)
                    result.row_count = len(df)
                    result.is_valid = True
                    
                finally:
                    # Clean up temp file (same as S3DirectDataAnalyzer)
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass
            else:
                # Local file - use exact same Polars call as S3DirectDataAnalyzer
                try:
                    df = pl.read_csv(
                        file_path, 
                        separator=';',  # Use semicolon as default like import_metadata.py
                        n_rows=1000,  # Sample for validation
                        ignore_errors=True  # Handle malformed rows gracefully
                    )
                    
                    # Set file info
                    result.file_size = os.path.getsize(file_path)
                    result.encoding = 'utf-8'  # Polars handles encoding automatically
                    result.delimiter = ';'
                    result.column_count = len(df.columns)
                    result.row_count = len(df)
                    result.is_valid = True
                    
                except Exception as e:
                    result.add_issue(ValidationIssue(
                        code=ValidationErrorCodes.ENCODING_ERROR,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"Cannot read file with Polars: {str(e)}",
                        file_path=file_path
                    ))
                    return
                    
        except Exception as e:
            result.add_issue(ValidationIssue(
                code=ValidationErrorCodes.ENCODING_ERROR,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"File validation failed: {str(e)}",
                file_path=file_path
            ))
    
    def _validate_csv_file_structure(self, 
                                   file_path: str, 
                                   dataset_config: Dict[str, Any], 
                                   result: FileValidationResult):
        """Validate CSV file structure"""
        try:
            # Detect encoding
            encoding = self._detect_encoding(file_path)
            result.encoding = encoding
            
            # Detect delimiter
            delimiter = self._detect_delimiter(file_path, encoding)
            result.delimiter = delimiter
            
            # Read and validate structure
            with open(file_path, 'r', encoding=encoding) as f:
                reader = csv.reader(f, delimiter=delimiter)
                
                # Read header
                try:
                    headers = next(reader)
                    result.column_count = len(headers)
                except StopIteration:
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.HEADER_MISSING,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message="CSV file has no header row",
                        file_path=file_path
                    ))
                    result.is_valid = False
                    return
                
                # Check for duplicate headers
                if len(headers) != len(set(headers)):
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.DUPLICATE_HEADERS,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message="CSV file has duplicate column headers",
                        file_path=file_path
                    ))
                    result.is_valid = False
                
                # Count rows and validate structure
                row_count = 0
                for row_num, row in enumerate(reader, start=2):
                    row_count += 1
                    
                    # Check row length consistency
                    if len(row) != len(headers):
                        result.issues.append(ValidationIssue(
                            code=ValidationErrorCodes.MALFORMED_CSV,
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.FILE_STRUCTURE,
                            message=f"Row {row_num} has {len(row)} columns, expected {len(headers)}",
                            file_path=file_path,
                            line_number=row_num
                        ))
                    
                    # Stop counting after reasonable limit for performance
                    if row_count > self.max_row_count:
                        result.issues.append(ValidationIssue(
                            code=ValidationErrorCodes.FILE_TOO_LARGE,
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.FILE_STRUCTURE,
                            message=f"File has more than {self.max_row_count} rows",
                            file_path=file_path,
                            suggested_fix="Consider processing in chunks"
                        ))
                        break
                
                result.row_count = row_count
        
        except UnicodeDecodeError as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.ENCODING_ERROR,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"Encoding error: {str(e)}",
                file_path=file_path,
                suggested_fix="Try different encoding or fix file encoding"
            ))
            result.is_valid = False
        
        except Exception as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.MALFORMED_CSV,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"CSV parsing error: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
    
    def _validate_json_file_structure(self, 
                                    file_path: str, 
                                    dataset_config: Dict[str, Any], 
                                    result: FileValidationResult):
        """Validate JSON file structure"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                result.row_count = len(data)
                if data:
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        result.column_count = len(first_item.keys())
                    else:
                        result.issues.append(ValidationIssue(
                            code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.FILE_STRUCTURE,
                            message="JSON array should contain objects",
                            file_path=file_path
                        ))
                        result.is_valid = False
                else:
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_EMPTY,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message="JSON array is empty",
                        file_path=file_path
                    ))
                    result.is_valid = False
            
            elif isinstance(data, dict):
                result.row_count = 1
                result.column_count = len(data.keys())
            
            else:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message="JSON should be object or array of objects",
                    file_path=file_path
                ))
                result.is_valid = False
        
        except json.JSONDecodeError as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"Invalid JSON format: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
        
        except Exception as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"JSON validation failed: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
    
    def _extract_file_columns(self, file_path: str, organization_code: Optional[str] = None) -> List[str]:
        """Extract column names from a file (local or S3) using Polars (same as S3DirectDataAnalyzer)"""
        import polars as pl
        import tempfile
        
        try:
            file_extension = Path(file_path).suffix.lower()
            is_s3_path = self._is_s3_path(file_path)
            
            if file_extension in ['.csv', '.tsv', '.txt']:
                if is_s3_path and organization_code:
                    # Use same approach as S3DirectDataAnalyzer
                    bucket_name = self.bucket_service.get_organization_bucket(organization_code)
                    
                    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp_file:
                        temp_file_path = temp_file.name
                    
                    try:
                        # Download file using S3 client (same as S3DirectDataAnalyzer)
                        self.bucket_service.base_s3_service.s3_client.download_file(
                            bucket_name, 
                            file_path, 
                            temp_file_path
                        )
                        
                        # Use exact same Polars call as S3DirectDataAnalyzer
                        df = pl.read_csv(
                            temp_file_path, 
                            separator=';',  # Use semicolon as default like import_metadata.py
                            n_rows=1,  # Only need first row for column names
                            ignore_errors=True  # Handle malformed rows gracefully
                        )
                        
                        return list(df.columns)
                        
                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass
                else:
                    # Local file - use same Polars approach
                    df = pl.read_csv(
                        file_path, 
                        separator=';',  # Use semicolon as default like import_metadata.py
                        n_rows=1,  # Only need first row for column names
                        ignore_errors=True  # Handle malformed rows gracefully
                    )
                    
                    return list(df.columns)
            
            elif file_extension == '.json':
                if is_s3_path and organization_code:
                    # Get from S3
                    bucket_name = self.bucket_service.get_organization_bucket(organization_code)
                    file_content_response = self.bucket_service.get_file_content(bucket_name, file_path)
                    
                    if file_content_response.get('success'):
                        content_bytes = file_content_response.get('content', b'')
                        content_str = content_bytes.decode('utf-8')
                        data = json.loads(content_str)
                        
                        if isinstance(data, list) and data:
                            return list(data[0].keys()) if isinstance(data[0], dict) else []
                        elif isinstance(data, dict):
                            return list(data.keys())
                else:
                    # Local file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list) and data:
                        return list(data[0].keys()) if isinstance(data[0], dict) else []
                    elif isinstance(data, dict):
                        return list(data.keys())
            
            return []
        
        except Exception as e:
            self.logger.warning(f"Failed to extract columns from {file_path}: {str(e)}")
            return []
    
    def _detect_encoding(self, file_path: str) -> str:
        """Detect file encoding"""
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result['encoding'] or 'utf-8'
        except ImportError:
            # Fallback without chardet
            for encoding in self.supported_encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        f.read(1000)  # Try to read first 1KB
                    return encoding
                except UnicodeDecodeError:
                    continue
            return 'utf-8'  # Default fallback
    
    def _detect_delimiter(self, file_path: str, encoding: str) -> str:
        """Detect CSV delimiter"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                sample = f.read(1024)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=',;\t|')
                return dialect.delimiter
        except:
            return ';'  # Default fallback - consistent with execution system
    
    def _is_valid_reference_table(self, table_name: str) -> bool:
        """Check if a reference table is valid (placeholder implementation)"""
        # This would normally check against database or metadata
        # For now, return True as a placeholder
        return True
    
    def _detect_circular_dependencies(self, dependencies: Dict[str, List[str]]) -> List[List[str]]:
        """Detect circular dependencies in the dependency graph"""
        cycles = []
        
        def visit(node, path, visited):
            if node in path:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            path.append(node)
            
            for neighbor in dependencies.get(node, []):
                visit(neighbor, path, visited)
            
            path.pop()
        
        visited = set()
        for node in dependencies:
            if node not in visited:
                visit(node, [], visited)
        
        return cycles
    
    def _generate_execution_recommendations(self, result: PreExecutionValidationResult):
        """Generate execution recommendations based on validation results"""
        recommendations = []
        required_actions = []
        
        # Check for blocking issues
        if result.has_blocking_issues():
            required_actions.append("Resolve all critical and error-level issues before execution")
        
        # File-specific recommendations
        large_files = [fr for fr in result.file_validation_results if fr.file_size > 50 * 1024 * 1024]
        if large_files:
            recommendations.append("Consider chunked processing for large files")
        
        # Resource-based recommendations
        if result.resource_estimate:
            if result.resource_estimate.estimated_memory_usage > self.performance_thresholds['memory_warning']:
                recommendations.append("High memory usage expected - monitor system resources")
            
            if result.resource_estimate.estimated_execution_time > self.performance_thresholds['execution_time_warning']:
                recommendations.append("Long execution time expected - consider running during off-peak hours")
            
            if result.resource_estimate.parallel_processing_recommendation:
                recommendations.append("Parallel processing recommended for better performance")
        
        # Column mapping recommendations
        if result.column_mapping_result:
            if result.column_mapping_result.coverage_percentage < 80:
                recommendations.append("Low column mapping coverage - review unmapped columns")
        
        result.execution_recommendations = recommendations
        result.required_actions = required_actions
    
    def _determine_overall_validity(self, result: PreExecutionValidationResult) -> bool:
        """Determine overall validity based on validation mode and issues"""
        if self.validation_mode == ValidationMode.LENIENT:
            return not any(issue.severity == ValidationSeverity.CRITICAL for issue in result.all_issues)
        elif self.validation_mode == ValidationMode.WARNING_ONLY:
            return not any(issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR] 
                          for issue in result.all_issues)
        else:  # STRICT
            return not result.has_blocking_issues()
    
    def _is_s3_path(self, file_path: str) -> bool:
        """Check if a file path is an S3 path (not a local file path)"""
        # S3 paths don't start with / and don't have drive letters (C:, etc.)
        # They typically look like: "metadata/file.csv" or "folder/subfolder/file.csv"
        # But they should not start with . (like ./file.csv or ../file.csv)
        # Also check that it looks like a file path (has a file extension or contains /)
        if not file_path or len(file_path) < 3:
            return False
        
        # Must look like a file path (has extension or contains path separators)
        has_extension = '.' in file_path and file_path.rfind('.') > 0
        has_path_separator = '/' in file_path
        
        if not (has_extension or has_path_separator):
            return False
            
        return (not os.path.isabs(file_path) and 
                ':' not in file_path and 
                not file_path.startswith('.') and
                not file_path.startswith('~'))
    
    def _check_s3_file_exists(self, bucket_name: str, file_path: str) -> Tuple[bool, int]:
        """Check if a file exists in S3 and return its size"""
        try:
            # Use the bucket service's S3 client to check file
            response = self.bucket_service.base_s3_service.s3_client.head_object(
                Bucket=bucket_name,
                Key=file_path
            )
            return True, response.get('ContentLength', 0)
        except Exception as e:
            self.logger.debug(f"File not found in S3: {bucket_name}/{file_path}")
            return False, 0
    
    def _get_file_size(self, file_path: str, organization_code: Optional[str] = None) -> int:
        """Get file size for either local or S3 file"""
        if self._is_s3_path(file_path) and organization_code:
            bucket_name = self.bucket_service.get_organization_bucket(organization_code)
            _, size = self._check_s3_file_exists(bucket_name, file_path)
            return size
        elif os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    
    def _validate_csv_file_structure_s3(self, 
                                       file_path: str, 
                                       dataset_config: Dict[str, Any], 
                                       result: FileValidationResult,
                                       organization_code: str):
        """Validate CSV file structure from S3"""
        try:
            # Get file content from S3
            bucket_name = self.bucket_service.get_organization_bucket(organization_code)
            file_content_response = self.bucket_service.get_file_content(bucket_name, file_path)
            
            if not file_content_response.get('success'):
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.FILE_NOT_READABLE,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"Cannot read file from S3: {file_path}",
                    file_path=file_path
                ))
                result.is_valid = False
                return
            
            # Get content as string
            content_bytes = file_content_response.get('content', b'')
            
            # Detect encoding
            encoding = self._detect_encoding_from_bytes(content_bytes[:10000])
            result.encoding = encoding
            
            # Decode content
            content_str = content_bytes.decode(encoding)
            
            # Detect delimiter
            delimiter = self._detect_delimiter_from_string(content_str[:1024])
            result.delimiter = delimiter
            
            # Parse CSV
            csv_file = io.StringIO(content_str)
            reader = csv.reader(csv_file, delimiter=delimiter)
            
            # Read header
            try:
                headers = next(reader)
                result.column_count = len(headers)
            except StopIteration:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.HEADER_MISSING,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message="CSV file has no header row",
                    file_path=file_path
                ))
                result.is_valid = False
                return
            
            # Check for duplicate headers
            if len(headers) != len(set(headers)):
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.DUPLICATE_HEADERS,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message="CSV file has duplicate column headers",
                    file_path=file_path
                ))
                result.is_valid = False
            
            # Count rows and validate structure
            row_count = 0
            for row_num, row in enumerate(reader, start=2):
                row_count += 1
                
                # Check row length consistency
                if len(row) != len(headers):
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.MALFORMED_CSV,
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"Row {row_num} has {len(row)} columns, expected {len(headers)}",
                        file_path=file_path,
                        line_number=row_num
                    ))
                
                # Stop counting after reasonable limit for performance
                if row_count > self.max_row_count:
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_TOO_LARGE,
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message=f"File has more than {self.max_row_count} rows",
                        file_path=file_path,
                        suggested_fix="Consider processing in chunks"
                    ))
                    break
            
            result.row_count = row_count
            
        except UnicodeDecodeError as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.ENCODING_ERROR,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"Encoding error: {str(e)}",
                file_path=file_path,
                suggested_fix="Try different encoding or fix file encoding"
            ))
            result.is_valid = False
        
        except Exception as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.MALFORMED_CSV,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"CSV parsing error: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
    
    def _validate_json_file_structure_s3(self, 
                                        file_path: str, 
                                        dataset_config: Dict[str, Any], 
                                        result: FileValidationResult,
                                        organization_code: str):
        """Validate JSON file structure from S3"""
        try:
            # Get file content from S3
            bucket_name = self.bucket_service.get_organization_bucket(organization_code)
            file_content_response = self.bucket_service.get_file_content(bucket_name, file_path)
            
            if not file_content_response.get('success'):
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.FILE_NOT_READABLE,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message=f"Cannot read file from S3: {file_path}",
                    file_path=file_path
                ))
                result.is_valid = False
                return
            
            # Parse JSON from content
            content_bytes = file_content_response.get('content', b'')
            content_str = content_bytes.decode('utf-8')
            data = json.loads(content_str)
            
            if isinstance(data, list):
                result.row_count = len(data)
                if data:
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        result.column_count = len(first_item.keys())
                    else:
                        result.issues.append(ValidationIssue(
                            code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.FILE_STRUCTURE,
                            message="JSON array should contain objects",
                            file_path=file_path
                        ))
                        result.is_valid = False
                else:
                    result.issues.append(ValidationIssue(
                        code=ValidationErrorCodes.FILE_EMPTY,
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.FILE_STRUCTURE,
                        message="JSON array is empty",
                        file_path=file_path
                    ))
                    result.is_valid = False
            
            elif isinstance(data, dict):
                result.row_count = 1
                result.column_count = len(data.keys())
            
            else:
                result.issues.append(ValidationIssue(
                    code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.FILE_STRUCTURE,
                    message="JSON should be object or array of objects",
                    file_path=file_path
                ))
                result.is_valid = False
        
        except json.JSONDecodeError as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.INVALID_FILE_FORMAT,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"Invalid JSON format: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
        
        except Exception as e:
            result.issues.append(ValidationIssue(
                code=ValidationErrorCodes.VALIDATION_FAILED,
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.FILE_STRUCTURE,
                message=f"JSON validation failed: {str(e)}",
                file_path=file_path
            ))
            result.is_valid = False
    
    def _detect_encoding_from_bytes(self, content_bytes: bytes) -> str:
        """Detect encoding from byte content"""
        try:
            import chardet
            result = chardet.detect(content_bytes)
            return result['encoding'] or 'utf-8'
        except ImportError:
            # Fallback without chardet
            for encoding in self.supported_encodings:
                try:
                    content_bytes.decode(encoding)
                    return encoding
                except UnicodeDecodeError:
                    continue
            return 'utf-8'  # Default fallback
    
    def _detect_delimiter_from_string(self, content_str: str) -> str:
        """Detect CSV delimiter from string content"""
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(content_str, delimiters=',;\t|')
            return dialect.delimiter
        except:
            return ';'  # Default fallback - consistent with execution system