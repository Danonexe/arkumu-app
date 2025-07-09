"""
File Dataset Matcher Service

Provides comprehensive file-to-dataset matching functionality for the import pipeline.
Handles various naming conventions, file validation, and structured matching results.
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arkumu.importer.services.mapping_consumer.config_translator import ExecutionConfig, DatasetConfig
    from arkumu.importer.services.error_handling.error_manager import ErrorManager
    from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService

logger = logging.getLogger(__name__)


class MatchingStrategy(Enum):
    """Available file matching strategies"""
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    PATTERN_MATCH = "pattern_match"
    CONTAINS_MATCH = "contains_match"


@dataclass
class FileInfo:
    """Information about a file for matching"""
    file_path: str
    filename: str
    basename: str  # filename without extension
    extension: str
    size: int
    exists: bool
    is_readable: bool
    directory: str
    relative_path: str = ""
    
    def __post_init__(self):
        """Calculate additional properties after initialization"""
        path_obj = Path(self.file_path)
        self.directory = str(path_obj.parent)
        self.basename = path_obj.stem
        self.extension = path_obj.suffix.lower()
        self.filename = path_obj.name


@dataclass
class DatasetMatchCandidate:
    """Candidate dataset for file matching"""
    dataset_name: str
    normalized_name: str
    config: Any  # DatasetConfig
    required_columns: List[str] = field(default_factory=list)
    primary_keys: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class MatchResult:
    """Result of file-to-dataset matching"""
    file_info: FileInfo
    dataset_name: Optional[str]
    confidence: float
    matching_strategy: MatchingStrategy
    reasons: List[str] = field(default_factory=list)
    validation_issues: List[str] = field(default_factory=list)
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchMatchResult:
    """Result of batch file matching"""
    successful_matches: List[MatchResult]
    failed_matches: List[MatchResult]
    unmatched_files: List[FileInfo]
    unmatched_datasets: List[str]
    total_files: int
    total_datasets: int
    match_rate: float = 0.0
    
    def __post_init__(self):
        """Calculate match rate after initialization"""
        if self.total_files > 0:
            self.match_rate = len(self.successful_matches) / self.total_files


class FileDatasetMatcher:
    """
    Service for matching files to dataset configurations.
    
    Provides comprehensive file-to-dataset matching with support for:
    - Various naming conventions (underscore, hyphen, exact match)
    - Fuzzy matching for dataset names
    - File validation against dataset expectations
    - Batch processing capabilities
    - Integration with existing services
    """
    
    def __init__(self, error_manager: Optional['ErrorManager'] = None):
        """
        Initialize the file dataset matcher.
        
        Args:
            error_manager: Optional error manager for structured error handling
        """
        self.error_manager = error_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Configuration
        self.fuzzy_threshold = 0.6  # Minimum similarity for fuzzy matching
        self.supported_extensions = {'.csv', '.tsv', '.txt', '.json', '.xml'}
        
        # Naming patterns for dataset extraction
        self.naming_patterns = [
            r'^([^_.-]+).*',  # First part before delimiter
            r'^([^_-]+)_.*',  # Underscore separated
            r'^([^-_]+)-.*',  # Hyphen separated
            r'^(.+?)(?:_\d+)?(?:\.[^.]+)?$',  # Without trailing numbers
            r'^(.+?)(?:-\d+)?(?:\.[^.]+)?$',  # Without trailing numbers (hyphen)
        ]
    
    def match_files_to_datasets(
        self,
        selected_files: List[str],
        execution_config: 'ExecutionConfig',
        base_directory: Optional[str] = None
    ) -> BatchMatchResult:
        """
        Match a list of files to dataset configurations.
        
        Args:
            selected_files: List of file paths to match
            execution_config: Execution configuration with dataset information
            base_directory: Optional base directory for resolving relative paths
            
        Returns:
            BatchMatchResult with comprehensive matching results
        """
        self.logger.info(f"Starting file-to-dataset matching for {len(selected_files)} files")
        
        # Prepare file information
        file_infos = []
        for file_path in selected_files:
            try:
                file_info = self._create_file_info(file_path, base_directory)
                file_infos.append(file_info)
            except Exception as e:
                if self.error_manager:
                    self.error_manager.record_error(
                        error_code="FILE_INFO_CREATION_ERROR",
                        error_type="FileProcessingError",
                        error_message=f"Failed to create file info for {file_path}: {str(e)}",
                        error_category="file_processing",
                        context={"file_path": file_path}
                    )
                continue
        
        # Prepare dataset candidates
        dataset_candidates = self._create_dataset_candidates(execution_config)
        
        # Perform matching
        successful_matches = []
        failed_matches = []
        unmatched_files = []
        
        for file_info in file_infos:
            try:
                match_result = self._match_single_file(file_info, dataset_candidates)
                
                if match_result.dataset_name and match_result.is_valid:
                    successful_matches.append(match_result)
                elif match_result.dataset_name:
                    failed_matches.append(match_result)
                else:
                    unmatched_files.append(file_info)
                    
            except Exception as e:
                if self.error_manager:
                    self.error_manager.record_error(
                        error_code="FILE_MATCHING_ERROR",
                        error_type="MatchingError",
                        error_message=f"Failed to match file {file_info.file_path}: {str(e)}",
                        error_category="file_processing",
                        context={"file_path": file_info.file_path}
                    )
                unmatched_files.append(file_info)
        
        # Identify unmatched datasets
        matched_datasets = {match.dataset_name for match in successful_matches}
        unmatched_datasets = [
            candidate.dataset_name for candidate in dataset_candidates
            if candidate.dataset_name not in matched_datasets
        ]
        
        result = BatchMatchResult(
            successful_matches=successful_matches,
            failed_matches=failed_matches,
            unmatched_files=unmatched_files,
            unmatched_datasets=unmatched_datasets,
            total_files=len(file_infos),
            total_datasets=len(dataset_candidates)
        )
        
        self.logger.info(f"Matching completed: {len(successful_matches)} successful, "
                        f"{len(failed_matches)} failed, {len(unmatched_files)} unmatched files")
        
        return result
    
    def validate_file_structure(
        self,
        file_path: str,
        dataset_config: 'DatasetConfig',
        base_directory: Optional[str] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate file structure against dataset expectations.
        
        Args:
            file_path: Path to the file to validate
            dataset_config: Dataset configuration to validate against
            base_directory: Optional base directory for resolving relative paths
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        try:
            # Create file info
            file_info = self._create_file_info(file_path, base_directory)
            
            # Basic file existence and readability
            if not file_info.exists:
                issues.append(f"File does not exist: {file_path}")
                return False, issues
            
            if not file_info.is_readable:
                issues.append(f"File is not readable: {file_path}")
                return False, issues
            
            # File extension validation
            if file_info.extension not in self.supported_extensions:
                issues.append(f"Unsupported file extension: {file_info.extension}")
            
            # File size validation
            if file_info.size == 0:
                issues.append("File is empty")
            elif file_info.size > 100 * 1024 * 1024:  # 100MB limit
                issues.append(f"File is too large: {file_info.size / (1024*1024):.1f}MB")
            
            # CSV-specific validation
            if file_info.extension in {'.csv', '.tsv'}:
                csv_issues = self._validate_csv_structure(file_info, dataset_config)
                issues.extend(csv_issues)
            
            # JSON-specific validation
            elif file_info.extension == '.json':
                json_issues = self._validate_json_structure(file_info, dataset_config)
                issues.extend(json_issues)
            
            return len(issues) == 0, issues
            
        except Exception as e:
            if self.error_manager:
                self.error_manager.record_error(
                    error_code="FILE_VALIDATION_ERROR",
                    error_type="ValidationError",
                    error_message=f"Failed to validate file {file_path}: {str(e)}",
                    error_category="validation",
                    context={"file_path": file_path, "dataset": dataset_config.dataset_name}
                )
            return False, [f"Validation error: {str(e)}"]
    
    def get_dataset_from_filename(self, filename: str) -> Optional[str]:
        """
        Extract dataset name from filename using various patterns.
        
        Args:
            filename: Name of the file
            
        Returns:
            Extracted dataset name or None if no pattern matches
        """
        # Remove extension
        basename = Path(filename).stem
        
        # Try each naming pattern
        for pattern in self.naming_patterns:
            match = re.match(pattern, basename)
            if match:
                dataset_name = match.group(1)
                # Clean up common prefixes/suffixes
                dataset_name = self._clean_dataset_name(dataset_name)
                if dataset_name:
                    self.logger.debug(f"Extracted dataset '{dataset_name}' from '{filename}' using pattern '{pattern}'")
                    return dataset_name
        
        # If no pattern matches, return the basename cleaned up
        cleaned_name = self._clean_dataset_name(basename)
        if cleaned_name:
            self.logger.debug(f"Using cleaned basename '{cleaned_name}' from '{filename}'")
            return cleaned_name
        
        return None
    
    def analyze_file_compatibility(
        self,
        file_path: str,
        dataset_requirements: Dict[str, Any],
        base_directory: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze file compatibility with dataset requirements.
        
        Args:
            file_path: Path to the file to analyze
            dataset_requirements: Dictionary with dataset requirements
            base_directory: Optional base directory for resolving relative paths
            
        Returns:
            Dictionary with compatibility analysis results
        """
        try:
            file_info = self._create_file_info(file_path, base_directory)
            
            analysis = {
                'file_path': file_path,
                'file_info': {
                    'filename': file_info.filename,
                    'size': file_info.size,
                    'extension': file_info.extension,
                    'exists': file_info.exists,
                    'is_readable': file_info.is_readable
                },
                'compatibility_score': 0.0,
                'compatible': False,
                'issues': [],
                'recommendations': [],
                'metadata': {}
            }
            
            if not file_info.exists:
                analysis['issues'].append("File does not exist")
                return analysis
            
            # Basic compatibility checks
            score = 0.0
            max_score = 100.0
            
            # File existence and readability (20 points)
            if file_info.exists and file_info.is_readable:
                score += 20.0
            
            # File extension (20 points)
            if file_info.extension in self.supported_extensions:
                score += 20.0
            else:
                analysis['issues'].append(f"Unsupported file extension: {file_info.extension}")
                analysis['recommendations'].append("Convert file to supported format (.csv, .tsv, .json)")
            
            # File size (10 points)
            if 0 < file_info.size < 100 * 1024 * 1024:
                score += 10.0
            elif file_info.size == 0:
                analysis['issues'].append("File is empty")
            else:
                analysis['issues'].append("File is too large")
                analysis['recommendations'].append("Split large files into smaller chunks")
            
            # Dataset requirements compatibility (50 points)
            if dataset_requirements:
                req_score = self._analyze_dataset_requirements_compatibility(
                    file_info, dataset_requirements, analysis
                )
                score += req_score
            
            analysis['compatibility_score'] = score / max_score
            analysis['compatible'] = score >= 60.0  # 60% threshold
            
            return analysis
            
        except Exception as e:
            if self.error_manager:
                self.error_manager.record_error(
                    error_code="FILE_COMPATIBILITY_ANALYSIS_ERROR",
                    error_type="AnalysisError",
                    error_message=f"Failed to analyze file compatibility for {file_path}: {str(e)}",
                    error_category="analysis",
                    context={"file_path": file_path}
                )
            return {
                'file_path': file_path,
                'compatibility_score': 0.0,
                'compatible': False,
                'issues': [f"Analysis error: {str(e)}"],
                'recommendations': [],
                'metadata': {}
            }
    
    def _create_file_info(self, file_path: str, base_directory: Optional[str] = None) -> FileInfo:
        """Create FileInfo object from file path"""
        # Resolve relative paths
        if base_directory and not os.path.isabs(file_path):
            full_path = os.path.join(base_directory, file_path)
        else:
            full_path = file_path
        
        # Get file stats
        exists = os.path.exists(full_path)
        is_readable = os.access(full_path, os.R_OK) if exists else False
        size = os.path.getsize(full_path) if exists else 0
        
        # Calculate relative path
        relative_path = file_path
        if base_directory and full_path.startswith(base_directory):
            relative_path = os.path.relpath(full_path, base_directory)
        
        return FileInfo(
            file_path=full_path,
            filename=os.path.basename(full_path),
            basename="",  # Will be calculated in __post_init__
            extension="",  # Will be calculated in __post_init__
            size=size,
            exists=exists,
            is_readable=is_readable,
            directory="",  # Will be calculated in __post_init__
            relative_path=relative_path
        )
    
    def _create_dataset_candidates(self, execution_config: 'ExecutionConfig') -> List[DatasetMatchCandidate]:
        """Create dataset candidates from execution configuration"""
        candidates = []
        
        for dataset_config in execution_config.datasets:
            # Get required columns
            required_columns = [col.column_name for col in dataset_config.columns]
            
            candidate = DatasetMatchCandidate(
                dataset_name=dataset_config.dataset_name,
                normalized_name=self._normalize_dataset_name(dataset_config.dataset_name),
                config=dataset_config,
                required_columns=required_columns,
                primary_keys=dataset_config.primary_key_columns,
                dependencies=dataset_config.dependencies
            )
            candidates.append(candidate)
        
        return candidates
    
    def _match_single_file(self, file_info: FileInfo, candidates: List[DatasetMatchCandidate]) -> MatchResult:
        """Match a single file to dataset candidates"""
        best_match = None
        best_confidence = 0.0
        best_strategy = None
        
        # Extract potential dataset name from filename
        potential_dataset = self.get_dataset_from_filename(file_info.filename)
        
        for candidate in candidates:
            # Try different matching strategies
            strategies = [
                (MatchingStrategy.EXACT_MATCH, self._exact_match),
                (MatchingStrategy.FUZZY_MATCH, self._fuzzy_match),
                (MatchingStrategy.PATTERN_MATCH, self._pattern_match),
                (MatchingStrategy.CONTAINS_MATCH, self._contains_match)
            ]
            
            for strategy, match_func in strategies:
                confidence = match_func(potential_dataset, candidate.normalized_name)
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = candidate
                    best_strategy = strategy
        
        # Create match result
        result = MatchResult(
            file_info=file_info,
            dataset_name=best_match.dataset_name if best_match else None,
            confidence=best_confidence,
            matching_strategy=best_strategy or MatchingStrategy.EXACT_MATCH,
            reasons=[],
            metadata={"potential_dataset": potential_dataset}
        )
        
        # Add reasons for the match
        if best_match:
            result.reasons.append(f"Matched using {best_strategy.value} strategy")
            result.reasons.append(f"Confidence: {best_confidence:.2f}")
            
            # Validate the match
            if best_confidence >= self.fuzzy_threshold:
                try:
                    is_valid, issues = self.validate_file_structure(
                        file_info.file_path, best_match.config
                    )
                    result.is_valid = is_valid
                    result.validation_issues = issues
                except Exception as e:
                    result.is_valid = False
                    result.validation_issues = [f"Validation error: {str(e)}"]
            else:
                result.is_valid = False
                result.validation_issues = [f"Match confidence too low: {best_confidence:.2f}"]
        
        return result
    
    def _exact_match(self, potential_dataset: Optional[str], candidate_name: str) -> float:
        """Exact matching strategy"""
        if potential_dataset and potential_dataset.lower() == candidate_name.lower():
            return 1.0
        return 0.0
    
    def _fuzzy_match(self, potential_dataset: Optional[str], candidate_name: str) -> float:
        """Fuzzy matching strategy using sequence similarity"""
        if not potential_dataset:
            return 0.0
        
        similarity = SequenceMatcher(None, potential_dataset.lower(), candidate_name.lower()).ratio()
        return similarity
    
    def _pattern_match(self, potential_dataset: Optional[str], candidate_name: str) -> float:
        """Pattern matching strategy"""
        if not potential_dataset:
            return 0.0
        
        # Check if one is a subset of the other
        potential_lower = potential_dataset.lower()
        candidate_lower = candidate_name.lower()
        
        if potential_lower in candidate_lower or candidate_lower in potential_lower:
            return 0.8
        
        # Check common patterns
        if potential_lower.replace('_', '') == candidate_lower.replace('_', ''):
            return 0.9
        
        if potential_lower.replace('-', '') == candidate_lower.replace('-', ''):
            return 0.9
        
        return 0.0
    
    def _contains_match(self, potential_dataset: Optional[str], candidate_name: str) -> float:
        """Contains matching strategy"""
        if not potential_dataset:
            return 0.0
        
        potential_lower = potential_dataset.lower()
        candidate_lower = candidate_name.lower()
        
        if potential_lower in candidate_lower:
            return 0.7
        
        if candidate_lower in potential_lower:
            return 0.7
        
        return 0.0
    
    def _normalize_dataset_name(self, name: str) -> str:
        """Normalize dataset name for matching"""
        # Convert to lowercase and replace common separators
        normalized = name.lower()
        normalized = re.sub(r'[_-]', '', normalized)
        normalized = re.sub(r'\s+', '', normalized)
        return normalized
    
    def _clean_dataset_name(self, name: str) -> str:
        """Clean dataset name by removing common prefixes/suffixes"""
        # Remove common prefixes
        for prefix in ['data_', 'dataset_', 'table_', 'file_']:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
                break
        
        # Remove common suffixes
        for suffix in ['_data', '_dataset', '_table', '_file']:
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        # Remove numbers at the end
        name = re.sub(r'_?\d+$', '', name)
        
        return name.strip()
    
    def _validate_csv_structure(self, file_info: FileInfo, dataset_config: 'DatasetConfig') -> List[str]:
        """Validate CSV file structure"""
        issues = []
        
        try:
            import csv
            
            # Detect delimiter
            with open(file_info.file_path, 'r', encoding='utf-8') as f:
                sample = f.read(1024)
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                    delimiter = dialect.delimiter
                except:
                    delimiter = ',' if file_info.extension == '.csv' else '\t'
            
            # Read first few rows
            with open(file_info.file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter)
                try:
                    headers = next(reader)
                    first_row = next(reader) if reader else None
                except StopIteration:
                    issues.append("CSV file appears to be empty or has no data rows")
                    return issues
            
            # Validate headers
            if not headers:
                issues.append("CSV file has no headers")
                return issues
            
            # Check for required columns
            required_columns = [col.column_name for col in dataset_config.columns]
            missing_columns = set(required_columns) - set(headers)
            
            if missing_columns:
                issues.append(f"Missing required columns: {', '.join(missing_columns)}")
            
            # Check for duplicate headers
            if len(headers) != len(set(headers)):
                issues.append("CSV file has duplicate column headers")
            
            # Check data consistency
            if first_row:
                if len(first_row) != len(headers):
                    issues.append("First data row has different number of columns than headers")
        
        except Exception as e:
            issues.append(f"Error reading CSV file: {str(e)}")
        
        return issues
    
    def _validate_json_structure(self, file_info: FileInfo, dataset_config: 'DatasetConfig') -> List[str]:
        """Validate JSON file structure"""
        issues = []
        
        try:
            import json
            
            with open(file_info.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it's a list of objects (common format)
            if isinstance(data, list):
                if not data:
                    issues.append("JSON file is empty")
                    return issues
                
                # Check first object
                first_obj = data[0]
                if not isinstance(first_obj, dict):
                    issues.append("JSON file should contain list of objects")
                    return issues
                
                # Check for required fields
                required_columns = [col.column_name for col in dataset_config.columns]
                missing_columns = set(required_columns) - set(first_obj.keys())
                
                if missing_columns:
                    issues.append(f"Missing required fields: {', '.join(missing_columns)}")
            
            elif isinstance(data, dict):
                # Single object or nested structure
                required_columns = [col.column_name for col in dataset_config.columns]
                missing_columns = set(required_columns) - set(data.keys())
                
                if missing_columns:
                    issues.append(f"Missing required fields: {', '.join(missing_columns)}")
            
            else:
                issues.append("JSON file should contain object or array of objects")
        
        except json.JSONDecodeError as e:
            issues.append(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            issues.append(f"Error reading JSON file: {str(e)}")
        
        return issues
    
    def _analyze_dataset_requirements_compatibility(
        self,
        file_info: FileInfo,
        dataset_requirements: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> float:
        """Analyze compatibility with dataset requirements"""
        score = 0.0
        
        # Check required columns if available
        required_columns = dataset_requirements.get('required_columns', [])
        if required_columns:
            try:
                # Quick check for CSV files
                if file_info.extension in {'.csv', '.tsv'}:
                    import csv
                    with open(file_info.file_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        headers = next(reader)
                    
                    missing_cols = set(required_columns) - set(headers)
                    if not missing_cols:
                        score += 30.0
                    else:
                        score += max(0, 30.0 - len(missing_cols) * 5.0)
                        analysis['issues'].append(f"Missing columns: {', '.join(missing_cols)}")
                
                # Quick check for JSON files
                elif file_info.extension == '.json':
                    import json
                    with open(file_info.file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list) and data:
                        first_obj = data[0]
                        if isinstance(first_obj, dict):
                            missing_cols = set(required_columns) - set(first_obj.keys())
                            if not missing_cols:
                                score += 30.0
                            else:
                                score += max(0, 30.0 - len(missing_cols) * 5.0)
                                analysis['issues'].append(f"Missing fields: {', '.join(missing_cols)}")
                
            except Exception as e:
                analysis['issues'].append(f"Could not verify required columns: {str(e)}")
        
        # Check data type compatibility
        expected_types = dataset_requirements.get('expected_types', {})
        if expected_types:
            score += 10.0  # Basic bonus for having type information
        
        # Check file size expectations
        expected_size_range = dataset_requirements.get('size_range')
        if expected_size_range:
            min_size, max_size = expected_size_range
            if min_size <= file_info.size <= max_size:
                score += 10.0
            else:
                analysis['recommendations'].append(f"File size ({file_info.size} bytes) outside expected range")
        
        return score