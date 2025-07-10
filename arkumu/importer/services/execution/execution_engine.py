"""
Main execution engine for mapping-aware data import.
"""

import logging
from typing import Any

import polars as pl

from arkumu.common.enums import UpdateStrategy
from arkumu.importer.services.mapping_validation.validator import MappingValidator
from arkumu.metadata.services.mapping import FKProcessingPlan
from arkumu.metadata.services.mapping import MappingCoordinator

from .data_processor import DataProcessor
from .resource_manager import ResourceManager
from .statistics import ExecutionMetrics
from .statistics import ExecutionStatistics
from .update_analyzer import UpdateAnalyzer


class ValidationError(Exception):
    """Exception raised when validation fails."""

logger = logging.getLogger(__name__)


class MappingExecutionEngine:
    """
    High-performance execution engine with mapping configuration support.

    Orchestrates data processing, resource management, and update analysis
    to execute sophisticated mapping configurations including FK relationships,
    external ontologies, and multi-value fields.
    """

    def __init__(self,
                 organization_id: str,
                 base_uri: str,
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: str | None = None,
                 batch_size: int = 1000):
        """
        Initialize the mapping execution engine.

        Args:
            organization_id: Organization identifier for URI generation
            base_uri: Base URI for resource generation
            default_strategy: Default update strategy
            timestamp_column: Column for timestamp-based updates
            batch_size: Batch size for bulk operations
        """
        self.organization_id = organization_id
        self.base_uri = base_uri
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
        self.batch_size = batch_size

        # Initialize component services
        self.statistics = ExecutionStatistics()
        self.data_processor = DataProcessor()
        self.resource_manager = ResourceManager(
            institution=organization_id,
            base_uri=base_uri,
            statistics=self.statistics,
        )
        self.update_analyzer = UpdateAnalyzer(
            resource_manager=self.resource_manager,
            default_strategy=default_strategy,
            timestamp_column=timestamp_column,
        )

        # Initialize mapping coordinator for FK/ontology processing
        self.mapping_coordinator = MappingCoordinator(organization_id, base_uri)

        # Initialize mapping validator
        self.validator = MappingValidator()

    def execute_with_processing_plan(self,
                                   csv_data: list[dict[str, Any]] | pl.DataFrame,
                                   processing_plan: FKProcessingPlan,
                                   dataset_name: str,
                                   workspace_columns: list[dict]) -> ExecutionMetrics:
        """
        Execute import using a complete FK processing plan.
        
        Args:
            csv_data: Input data
            processing_plan: Complete processing plan from mapping coordinator
            dataset_name: Name of the dataset
            workspace_columns: Column configurations
            
        Returns:
            Execution metrics
        """
        logger.info(f"Starting execution with processing plan for dataset: {dataset_name}")
        self.statistics.start_execution()
        self.statistics.start_dataset(dataset_name)

        try:
            # CRITICAL ADDITION: Pre-execution validation
            validation_result = self._validate_before_execution(csv_data, workspace_columns, dataset_name)

            # Handle critical validation errors
            if validation_result["critical_errors"]:
                error_messages = [error["message"] for error in validation_result["critical_errors"]]
                error_summary = f"Critical validation errors prevent execution: {'; '.join(error_messages)}"
                logger.error(f"Validation failed for {dataset_name}: {error_summary}")
                raise ValidationError(error_summary)

            # Log validation warnings but continue
            if validation_result["warnings"]:
                warning_messages = [warning["message"] for warning in validation_result["warnings"]]
                logger.warning(f"Validation warnings for {dataset_name} (proceeding with execution): {'; '.join(warning_messages)}")

            # Log successful validation
            if not validation_result["critical_errors"] and not validation_result["warnings"]:
                logger.info(f"Validation passed for {dataset_name}: No issues found")

            # Extract mapping configuration for this dataset
            mapping_config = self._extract_mapping_config(dataset_name, workspace_columns)

            # Execute the import
            return self._execute_dataset_import(csv_data, dataset_name, mapping_config)

        except Exception as e:
            self.statistics.add_error(f"Execution failed: {e}", dataset_name)
            logger.error(f"Execution failed for {dataset_name}: {e}", exc_info=True)
            raise
        finally:
            self.statistics.end_dataset(dataset_name)
            self.statistics.end_execution()

    def execute_simple_import(self,
                            csv_data: list[dict[str, Any]] | pl.DataFrame,
                            dataset_name: str,
                            mapping_config: dict | None = None,
                            workspace_columns: list[dict] | None = None) -> ExecutionMetrics:
        """
        Execute a simple import without complex FK processing.
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            workspace_columns: Optional workspace column configurations for validation
            
        Returns:
            Execution metrics
        """
        logger.info(f"Starting simple import for dataset: {dataset_name}")
        self.statistics.start_execution()
        self.statistics.start_dataset(dataset_name)

        try:
            # CRITICAL ADDITION: Pre-execution validation if workspace_columns provided
            if workspace_columns:
                validation_result = self._validate_before_execution(csv_data, workspace_columns, dataset_name)

                # Handle critical validation errors
                if validation_result["critical_errors"]:
                    error_messages = [error["message"] for error in validation_result["critical_errors"]]
                    error_summary = f"Critical validation errors prevent execution: {'; '.join(error_messages)}"
                    logger.error(f"Validation failed for {dataset_name}: {error_summary}")
                    raise ValidationError(error_summary)

                # Log validation warnings but continue
                if validation_result["warnings"]:
                    warning_messages = [warning["message"] for warning in validation_result["warnings"]]
                    logger.warning(f"Validation warnings for {dataset_name} (proceeding with execution): {'; '.join(warning_messages)}")

                # Log successful validation
                if not validation_result["critical_errors"] and not validation_result["warnings"]:
                    logger.info(f"Validation passed for {dataset_name}: No issues found")

            return self._execute_dataset_import(csv_data, dataset_name, mapping_config)
        except Exception as e:
            self.statistics.add_error(f"Simple import failed: {e}", dataset_name)
            logger.error(f"Simple import failed for {dataset_name}: {e}", exc_info=True)
            raise
        finally:
            self.statistics.end_dataset(dataset_name)
            self.statistics.end_execution()

    def analyze_import_impact(self,
                            csv_data: list[dict[str, Any]] | pl.DataFrame,
                            dataset_name: str,
                            mapping_config: dict | None = None) -> dict[str, Any]:
        """
        Analyze what would happen if we imported this data (dry run).
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            
        Returns:
            Analysis report
        """
        logger.info(f"Analyzing import impact for dataset: {dataset_name}")

        # Prepare data
        df = self.data_processor.prepare_for_processing(csv_data, mapping_config)

        # Analyze changes
        return self.update_analyzer.analyze_dataset_changes(dataset_name, df, mapping_config)

    def _execute_dataset_import(self,
                              csv_data: list[dict[str, Any]] | pl.DataFrame,
                              dataset_name: str,
                              mapping_config: dict | None = None) -> ExecutionMetrics:
        """
        Execute the actual dataset import.
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            
        Returns:
            Execution metrics
        """
        # Step 1: Prepare data
        logger.info(f"Step 1: Preparing data for {dataset_name}")
        df = self.data_processor.prepare_for_processing(csv_data, mapping_config)

        if df.height == 0:
            logger.warning(f"No data to import for {dataset_name}")
            return self.statistics.current_metrics

        # Step 2: Create dataset and structural resources
        logger.info("Step 2: Creating dataset and structural resources")
        dataset_resource = self.resource_manager.create_dataset_resource(dataset_name)

        # Get column names (excluding row_id)
        data_columns = [col for col in df.columns if col != "row_id"]
        column_resources = self.resource_manager.create_column_resources(dataset_name, data_columns)

        # Create row resources if needed (based on topology)
        row_resources = None
        if self._should_create_row_resources(mapping_config):
            row_ids = set(str(int(row_id) + 1) for row_id in df["row_id"].to_list())
            row_resources = self.resource_manager.create_row_resources(dataset_name, row_ids)

        # Create structural triples
        self.resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources, row_resources,
        )

        # Step 3: Process data in batches
        logger.info(f"Step 3: Processing {df.height} rows in batches of {self.batch_size}")
        total_rows = df.height

        for batch_start in range(0, total_rows, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_rows)
            batch_df = df[batch_start:batch_end]

            logger.debug(f"Processing batch {batch_start}-{batch_end}")
            self._process_batch(batch_df, dataset_name, mapping_config, column_resources)

        # Step 4: Handle special column types (FK, external ontology, etc.)
        if mapping_config:
            self._process_special_columns(df, dataset_name, mapping_config)

        return self.statistics.current_metrics

    def _process_batch(self,
                      batch_df: pl.DataFrame,
                      dataset_name: str,
                      mapping_config: dict | None,
                      column_resources: dict[str, Any]) -> None:
        """Process a batch of rows."""
        logger.debug(f"Processing batch with {batch_df.height} rows")
        cell_data = []
        value_data = []

        # Collect cell and value data
        for row_data in batch_df.iter_rows(named=True):
            row_id = row_data.get("row_id", 0)
            display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id

            for column_name, value in row_data.items():
                if column_name == "row_id" or value is None:
                    continue

                value_str = str(value).strip()
                if not value_str:
                    continue

                cell_data.append((dataset_name, column_name, str(display_row_id)))
                value_data.append((value_str, "http://www.w3.org/2001/XMLSchema#string"))

        logger.debug(f"Collected {len(cell_data)} cell data items, {len(value_data)} value data items")

        if not cell_data:
            logger.debug("No cell data to process, returning early")
            return

        # Create cell resources
        logger.debug("Creating cell resources...")
        cell_resources = self.resource_manager.create_cell_resources_bulk(cell_data)
        logger.debug(f"Created {len(cell_resources)} cell resources")

        # Create value resources
        logger.debug("Creating value resources...")
        unique_values = list(set(value_data))
        value_resources = self.resource_manager.create_value_resources_bulk(unique_values)
        logger.debug(f"Created {len(value_resources)} value resources")

        # Create value triples
        cell_value_pairs = []
        value_index = 0

        for row_data in batch_df.iter_rows(named=True):
            row_id = row_data.get("row_id", 0)
            display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id

            for column_name, value in row_data.items():
                if column_name == "row_id" or value is None:
                    continue

                value_str = str(value).strip()
                if not value_str:
                    continue

                cell_uri = self.resource_manager.generate_cell_uri(
                    dataset_name, column_name, str(display_row_id),
                )

                if cell_uri in cell_resources and value_str in value_resources:
                    cell_value_pairs.append((cell_resources[cell_uri], value_resources[value_str]))

        logger.debug(f"Prepared {len(cell_value_pairs)} cell-value pairs")

        # Create all value triples at once
        if cell_value_pairs:
            logger.debug("Creating value triples...")
            self.resource_manager.create_value_triples_bulk(cell_value_pairs)
            logger.debug("Value triples created successfully")

        # Update statistics
        self.statistics.current_metrics.cells_processed += len(cell_data)
        logger.debug(f"Updated statistics: cells_processed = {self.statistics.current_metrics.cells_processed}")

    def _extract_mapping_config(self, dataset_name: str, workspace_columns: list[dict]) -> dict | None:
        """Extract mapping configuration for a specific dataset."""
        # Find columns for this dataset
        dataset_columns = [
            col for col in workspace_columns
            if col.get("dataset_name") == dataset_name
        ]

        if not dataset_columns:
            return None

        mapping_config = {
            "columns": {},
        }

        for col in dataset_columns:
            col_name = col.get("column_name")
            if col_name:
                mapping_config["columns"][col_name] = {
                    "is_anchor": col.get("is_anchor", False),
                    "is_fk": col.get("is_fk", False),
                    "is_multi_value": col.get("is_multi_value", False),
                    "is_relationship_context": col.get("is_relationship_context", False),
                    "is_external_ontology": col.get("is_external_ontology", False),
                    "target_dataset": col.get("target_dataset"),
                    "target_column": col.get("target_column"),
                    "separator": col.get("separator", ","),
                }

        return mapping_config

    def _should_create_row_resources(self, mapping_config: dict | None) -> bool:
        """Determine if row resources should be created based on configuration."""
        # For now, default to not creating row resources (column-only topology)
        # This can be made configurable later
        return False

    def _process_special_columns(self,
                               df: pl.DataFrame,
                               dataset_name: str,
                               mapping_config: dict) -> None:
        """Process special column types (FK, external ontology, etc.)."""
        if "columns" not in mapping_config:
            return

        # Count special column types for statistics
        for col_name, col_config in mapping_config["columns"].items():
            if col_config.get("is_fk", False):
                # Placeholder for FK processing
                logger.debug(f"FK column detected: {col_name} -> {col_config.get('target_dataset')}")
                # TODO: Implement FK relationship creation

            elif col_config.get("is_external_ontology", False):
                # Placeholder for external ontology processing
                logger.debug(f"External ontology column detected: {col_name}")
                # TODO: Implement external ontology lookup

            elif col_config.get("is_multi_value", False):
                # Placeholder for multi-value processing
                logger.debug(f"Multi-value column detected: {col_name}")
                # TODO: Implement multi-value splitting

    def get_execution_summary(self) -> dict[str, Any]:
        """Get a complete execution summary."""
        summary = self.statistics.get_summary()
        summary["engine_info"] = {
            "organization_id": self.organization_id,
            "base_uri": self.base_uri,
            "batch_size": self.batch_size,
            "default_strategy": self.default_strategy.name,
        }
        return summary

    def _validate_before_execution(self, csv_data: list[dict[str, Any]] | pl.DataFrame,
                                 workspace_columns: list[dict], dataset_name: str) -> dict[str, Any]:
        """
        Comprehensive validation before data processing.
        
        Args:
            csv_data: Input data to validate
            workspace_columns: Column configurations
            dataset_name: Name of the dataset being processed
            
        Returns:
            Dict containing validation results with keys:
                - critical_errors: List of critical errors that prevent execution
                - warnings: List of warnings that don't prevent execution
                - all_issues: List of all validation issues found
        """
        logger.info(f"Starting comprehensive validation for dataset: {dataset_name}")
        issues = []

        try:
            # 1. Validate mapping completeness
            mapping_config = self._build_mapping_config_for_validation(dataset_name, workspace_columns)
            completeness_result = MappingValidator.validate_mapping_completeness(mapping_config)
            issues.extend(completeness_result.get("issues", []))

            # 2. Validate column mappings
            df = self.data_processor.ensure_dataframe(csv_data)
            file_columns = [col for col in df.columns if col != "row_id"]
            workspace_cols_dict = self._convert_workspace_columns_to_dict(workspace_columns, dataset_name)

            column_validation = MappingValidator.validate_column_mappings(workspace_cols_dict, file_columns)
            issues.extend(column_validation.get("issues", []))

            # 3. Validate relationships (if FK relationships exist)
            fk_relationships = self._extract_fk_relationships(workspace_columns, dataset_name)
            if fk_relationships:
                relationship_issues = MappingValidator.validate_relationships(workspace_cols_dict, fk_relationships)
                issues.extend(relationship_issues)

            # 4. Validate data types with sample data
            sample_data = self._get_sample_data_for_validation(df)
            type_issues = MappingValidator.validate_data_types(workspace_cols_dict, sample_data)
            issues.extend(type_issues)

            # Log comprehensive validation results
            error_count = len([issue for issue in issues if issue.get("severity") in ["ERROR", "CRITICAL"]])
            warning_count = len([issue for issue in issues if issue.get("severity") in ["WARNING", "INFO"]])

            logger.info(f"Validation completed for {dataset_name}: {len(issues)} total issues found "
                       f"({error_count} errors, {warning_count} warnings)")

            # Log detailed breakdown by category
            categories = {}
            for issue in issues:
                category = issue.get("category", "UNKNOWN")
                if category not in categories:
                    categories[category] = {"errors": 0, "warnings": 0}

                if issue.get("severity") in ["ERROR", "CRITICAL"]:
                    categories[category]["errors"] += 1
                elif issue.get("severity") in ["WARNING", "INFO"]:
                    categories[category]["warnings"] += 1

            if categories:
                logger.info("Validation issues by category:")
                for category, counts in categories.items():
                    logger.info(f"  {category}: {counts['errors']} errors, {counts['warnings']} warnings")

        except Exception as e:
            logger.error(f"Validation failed for {dataset_name}: {e!s}", exc_info=True)
            issues.append({
                "code": "VALIDATION_FAILED",
                "severity": "ERROR",
                "category": "VALIDATION",
                "message": f"Validation process failed: {e!s}",
                "details": {"exception": str(e)},
            })

        # Categorize issues by severity
        critical_errors = [issue for issue in issues if issue.get("severity") in ["ERROR", "CRITICAL"]]
        warnings = [issue for issue in issues if issue.get("severity") in ["WARNING", "INFO"]]

        # Add validation issues to statistics
        for issue in issues:
            if issue.get("severity") in ["ERROR", "CRITICAL"]:
                self.statistics.add_error(issue.get("message", "Unknown validation error"), dataset_name)
            elif issue.get("severity") in ["WARNING", "INFO"]:
                self.statistics.add_warning(issue.get("message", "Unknown validation warning"), dataset_name)

        return {
            "critical_errors": critical_errors,
            "warnings": warnings,
            "all_issues": issues,
        }

    def _build_mapping_config_for_validation(self, dataset_name: str, workspace_columns: list[dict]) -> dict[str, Any]:
        """Build mapping configuration for validation from workspace columns."""
        dataset_columns = [
            col for col in workspace_columns
            if col.get("dataset_name") == dataset_name
        ]

        return {
            "workspace_columns": {
                str(i): {
                    "name": col.get("column_name", ""),
                    "type": col.get("data_type", "string"),
                    "is_required": col.get("is_required", False),
                    "is_anchor": col.get("is_anchor", False),
                    "is_fk": col.get("is_fk", False),
                    "is_multi_value": col.get("is_multi_value", False),
                    "is_relationship_context": col.get("is_relationship_context", False),
                    "is_external_ontology": col.get("is_external_ontology", False),
                    "target_dataset": col.get("target_dataset"),
                    "target_column": col.get("target_column"),
                    "separator": col.get("separator", ","),
                }
                for i, col in enumerate(dataset_columns)
                if col.get("column_name")
            },
            "organization_id": self.organization_id,
            "dataset_name": dataset_name,
        }

    def _convert_workspace_columns_to_dict(self, workspace_columns: list[dict], dataset_name: str) -> dict[str, Any]:
        """Convert workspace columns list to dictionary format expected by validator."""
        dataset_columns = [
            col for col in workspace_columns
            if col.get("dataset_name") == dataset_name
        ]

        return {
            col.get("column_name", f"column_{i}"): {
                "name": col.get("column_name", ""),
                "type": col.get("data_type", "string"),
                "is_required": col.get("is_required", False),
                "is_anchor": col.get("is_anchor", False),
                "is_fk": col.get("is_fk", False),
                "is_multi_value": col.get("is_multi_value", False),
                "is_relationship_context": col.get("is_relationship_context", False),
                "is_external_ontology": col.get("is_external_ontology", False),
                "target_dataset": col.get("target_dataset"),
                "target_column": col.get("target_column"),
                "separator": col.get("separator", ","),
            }
            for i, col in enumerate(dataset_columns)
            if col.get("column_name")
        }

    def _extract_fk_relationships(self, workspace_columns: list[dict], dataset_name: str) -> dict[str, Any]:
        """Extract foreign key relationships from workspace columns."""
        fk_relationships = {}

        for col in workspace_columns:
            if (col.get("dataset_name") == dataset_name and
                col.get("is_fk", False) and
                col.get("column_name")):

                col_name = col.get("column_name")
                fk_relationships[col_name] = {
                    "target_dataset": col.get("target_dataset"),
                    "target_column": col.get("target_column"),
                    "source_column": col_name,
                }

        return fk_relationships

    def _get_sample_data_for_validation(self, df: pl.DataFrame) -> list[dict[str, Any]]:
        """Get sample data for validation in the format expected by validator."""
        if df.height == 0:
            return []

        # Get first 10 rows for validation
        sample_rows = min(10, df.height)
        sample_df = df.head(sample_rows)

        # Convert to list of dictionaries
        return sample_df.to_dicts()

    def _validate_files_if_needed(self, file_paths: list[str], organization_code: str) -> list[dict[str, Any]]:
        """
        Validate file structure and accessibility.
        
        Args:
            file_paths: List of file paths to validate
            organization_code: Organization code for S3 bucket access
            
        Returns:
            List of validation issues found
        """
        if not file_paths:
            return []

        all_issues = []
        for file_path in file_paths:
            try:
                file_issues = self.validator.validate_file_structure(file_path, organization_code)
                all_issues.extend(file_issues)
            except Exception as e:
                logger.error(f"File validation failed for {file_path}: {e!s}", exc_info=True)
                all_issues.append({
                    "code": "FILE_VALIDATION_FAILED",
                    "severity": "ERROR",
                    "category": "FILE_STRUCTURE",
                    "message": f"File validation failed: {e!s}",
                    "file_path": file_path,
                    "details": {"exception": str(e)},
                })

        return all_issues
