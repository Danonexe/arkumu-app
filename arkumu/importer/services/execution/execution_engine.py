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
from .uri_generator import UnifiedURIGenerator


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

        # Initialize URI generator for entity-based processing
        self.uri_generator = UnifiedURIGenerator(base_uri, organization_id)

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
            
            # Update rows processed
            self.statistics.current_metrics.rows_processed += batch_df.height

        # Step 4: Handle special column types (FK, external ontology, etc.)
        if mapping_config:
            self._process_special_columns(df, dataset_name, mapping_config)

        return self.statistics.current_metrics

    def _process_batch(self,
                      batch_df: pl.DataFrame,
                      dataset_name: str,
                      mapping_config: dict | None,
                      column_resources: dict[str, Any]) -> None:
        """Process batch using entity-based approach."""
        logger.debug(f"Processing batch with {batch_df.height} rows using entity-based approach")
        
        if batch_df.height == 0:
            logger.debug("No rows to process, returning early")
            return
        
        # Step 1: Resolve anchor columns
        csv_headers = [col for col in batch_df.columns if col != "row_id"]
        anchor_columns = self.uri_generator.resolve_anchor_columns(mapping_config, csv_headers)
        logger.debug(f"Resolved anchor columns: {anchor_columns}")
        
        # Step 2: Generate entity URIs for all rows
        entity_uris = self.uri_generator.generate_entity_uris_bulk(batch_df, dataset_name, anchor_columns)
        logger.debug(f"Generated {len(entity_uris)} entity URIs")
        
        # Step 3: Create entity resources
        # Extract entity IDs from URIs for bulk creation
        entity_data = []
        for uri in entity_uris:
            entity_id = uri.split('/')[-1]  # Get the last part of the URI as entity ID
            entity_data.append((dataset_name, entity_id))
        
        entity_resources = self.resource_manager.create_entity_resources_bulk(entity_data)
        logger.debug(f"Created {len(entity_resources)} entity resources")
        
        # Step 4: Create property triples for each column
        property_data = []
        for row_idx, row_data in enumerate(batch_df.iter_rows(named=True)):
            entity_uri = entity_uris[row_idx]
            entity_resource = entity_resources.get(entity_uri)
            
            if not entity_resource:
                logger.warning(f"Could not find entity resource for URI: {entity_uri}")
                continue
            
            for column_name, value in row_data.items():
                if column_name == "row_id" or value is None:
                    continue
                    
                value_str = str(value).strip()
                if not value_str:
                    continue
                
                # Generate property URI from column name
                property_uri = self._generate_property_uri(column_name, mapping_config)
                property_data.append((entity_resource, property_uri, value_str))
        
        logger.debug(f"Prepared {len(property_data)} property triples")
        
        # Step 5: Create all property triples in bulk
        if property_data:
            self.resource_manager.create_property_triples_bulk(property_data)
            logger.debug("Property triples created successfully")
        
        # Step 6: Update statistics
        self.statistics.current_metrics.entities_processed += len(entity_data)
        self.statistics.current_metrics.properties_created += len(property_data)
        logger.debug(f"Updated statistics: entities_processed = {self.statistics.current_metrics.entities_processed}, "
                    f"properties_created = {self.statistics.current_metrics.properties_created}")

    def _extract_mapping_config(self, dataset_name: str, workspace_columns: list[dict]) -> dict | None:
        """Enhanced mapping config extraction with anchor column detection."""
        # Find columns for this dataset
        dataset_columns = [
            col for col in workspace_columns
            if col.get("dataset_name") == dataset_name
        ]

        if not dataset_columns:
            return None

        mapping_config = {
            "columns": {},
            "anchor_columns": [],  # New: explicitly track anchor columns
        }

        anchor_columns_found = []
        for col in dataset_columns:
            col_name = col.get("column_name")
            if col_name:
                mapping_config["columns"][col_name] = {
                    "is_anchor": col.get("is_anchor", False),
                    "arkumu_type": col.get("arkumu_type", col_name),
                    "is_fk": col.get("is_fk", False),
                    "is_multi_value": col.get("is_multi_value", False),
                    "is_relationship_context": col.get("is_relationship_context", False),
                    "is_external_ontology": col.get("is_external_ontology", False),
                    "target_dataset": col.get("target_dataset"),
                    "target_column": col.get("target_column"),
                    "separator": col.get("separator", ","),
                }
                
                if col.get("is_anchor", False):
                    anchor_columns_found.append(col_name)

        # Set anchor columns (will be used by URI generator)
        mapping_config["anchor_columns"] = anchor_columns_found

        return mapping_config

    def _should_create_row_resources(self, mapping_config: dict | None) -> bool:
        """Determine if row resources should be created based on configuration."""
        # For now, default to not creating row resources (column-only topology)
        # This can be made configurable later
        return False

    def _generate_property_uri(self, column_name: str, mapping_config: dict | None) -> str:
        """
        Generate property URI for a column.
        Uses arkumu_type from mapping if available, otherwise uses column name.
        """
        if mapping_config and "columns" in mapping_config:
            column_config = mapping_config["columns"].get(column_name, {})
            arkumu_type = column_config.get("arkumu_type", column_name)
        else:
            arkumu_type = column_name
        
        # Use existing property URI generation logic
        from arkumu.common.uri_utils import mint_uri, slugify_uri_part
        safe_property = slugify_uri_part(arkumu_type)
        return mint_uri(self.base_uri, self.organization_id, "properties", safe_property)

    def _process_special_columns(self,
                               df: pl.DataFrame,
                               dataset_name: str,
                               mapping_config: dict) -> None:
        """Process special column types (FK, external ontology, etc.)."""
        if "columns" not in mapping_config:
            return

        # Process FK relationships with entity-based URIs
        for col_name, col_config in mapping_config["columns"].items():
            if col_config.get("is_fk", False):
                logger.info(f"Processing FK column: {col_name} -> {col_config.get('target_dataset')}")
                
                # Generate FK relationships between entities
                target_dataset = col_config.get("target_dataset")
                target_column = col_config.get("target_column")
                
                if target_dataset and target_column:
                    # Create entity-to-entity relationships
                    self._create_entity_relationships(df, col_name, dataset_name, target_dataset, target_column, col_config)
                else:
                    logger.warning(f"FK column {col_name} missing target configuration: target_dataset={target_dataset}, target_column={target_column}")

            elif col_config.get("is_external_ontology", False):
                # Placeholder for external ontology processing
                logger.debug(f"External ontology column detected: {col_name}")
                # TODO: Implement external ontology lookup

            elif col_config.get("is_multi_value", False):
                # Placeholder for multi-value processing
                logger.debug(f"Multi-value column detected: {col_name}")
                # TODO: Implement multi-value splitting

    def _create_entity_relationships(self,
                                   df: pl.DataFrame,
                                   col_name: str,
                                   dataset_name: str,
                                   target_dataset: str,
                                   target_column: str,
                                   col_config: dict) -> None:
        """
        Create entity-to-entity relationships for foreign keys.
        
        Args:
            df: DataFrame containing the data
            col_name: Name of the FK column
            dataset_name: Source dataset name
            target_dataset: Target dataset name
            target_column: Target column name
            col_config: Column configuration dictionary
        """
        logger.info(f"Creating entity relationships for {col_name}: {dataset_name} -> {target_dataset}")
        
        # Check if the FK column exists in the DataFrame
        if col_name not in df.columns:
            logger.warning(f"FK column {col_name} not found in DataFrame columns: {df.columns}")
            return
        
        # Get mapping config for anchor column resolution
        anchor_columns = self.uri_generator.resolve_anchor_columns(None, [col for col in df.columns if col != "row_id"])
        
        relationship_count = 0
        error_count = 0
        
        # Use the provided column configuration for multi-value support
        
        # Process each row to create FK relationships
        for row_data in df.iter_rows(named=True):
            fk_value = row_data.get(col_name)
            
            # Skip empty or null FK values
            if fk_value is None or str(fk_value).strip() == "":
                continue
            
            fk_value_str = str(fk_value).strip()
            
            # Handle multi-value FK columns (comma-separated values)
            fk_values = []
            if col_config and col_config.get("is_multi_value", False):
                separator = col_config.get("separator", ",")
                fk_values = [v.strip() for v in fk_value_str.split(separator) if v.strip()]
            else:
                fk_values = [fk_value_str]
            
            # Generate source entity URI once per row
            try:
                source_entity_uri = self._generate_source_entity_uri(
                    dataset_name, row_data, anchor_columns
                )
                
                # Create or get source entity resource
                source_entity_resource = self.resource_manager.create_entity_resource(
                    source_entity_uri, dataset_name
                )
                
                # Generate relationship property URI
                relationship_property_uri = self._generate_relationship_property_uri(
                    col_name, target_dataset
                )
                
                # Create relationships for each FK value
                for single_fk_value in fk_values:
                    try:
                        # Generate target entity URI using FK value as entity ID
                        target_entity_uri = self.resource_manager.generate_entity_uri(
                            target_dataset, single_fk_value
                        )
                        
                        # Create or get target entity resource (stub if doesn't exist)
                        target_entity_resource = self.resource_manager.create_entity_resource(
                            target_entity_uri, target_dataset, is_stub=True
                        )
                        
                        # Create the relationship triple
                        self.resource_manager.create_relationship_triple(
                            source_entity_resource,
                            relationship_property_uri, 
                            target_entity_resource
                        )
                        
                        relationship_count += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to create FK relationship for {col_name}={single_fk_value}: {e}")
                        error_count += 1
                        self.statistics.add_error(f"FK relationship creation failed: {e}", dataset_name)
                
            except Exception as e:
                logger.error(f"Failed to process FK relationships for row in {col_name}: {e}")
                error_count += 1
                self.statistics.add_error(f"FK row processing failed: {e}", dataset_name)
        
        # Update statistics
        self.statistics.current_metrics.relationships_created += relationship_count
        if hasattr(self.statistics, 'increment_fk_relationships'):
            self.statistics.increment_fk_relationships(relationship_count, dataset_name)
        
        logger.info(f"FK relationships created for {col_name}: {relationship_count} successful, {error_count} errors")

    def _generate_source_entity_uri(self, 
                                  dataset_name: str, 
                                  row_data: dict, 
                                  anchor_columns: list[str]) -> str:
        """Generate source entity URI using anchor columns or row_id."""
        if anchor_columns:
            # Use anchor columns to generate entity ID
            anchor_values = []
            for anchor_col in anchor_columns:
                value = row_data.get(anchor_col)
                if value is not None and str(value).strip():
                    anchor_values.append(str(value).strip())
            
            if anchor_values:
                entity_id = '_'.join(anchor_values)
                return self.resource_manager.generate_entity_uri(dataset_name, entity_id)
        
        # Fall back to row_id
        row_id = row_data.get('row_id', 0)
        display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
        return self.resource_manager.generate_entity_uri(dataset_name, str(display_row_id))

    def _generate_relationship_property_uri(self, 
                                          col_name: str, 
                                          target_dataset: str) -> str:
        """Generate property URI for FK relationships."""
        # Create a meaningful relationship property name
        relationship_name = f"has_{target_dataset.lower()}_reference"
        
        # Use standard property URI generation
        from arkumu.common.uri_utils import mint_uri, slugify_uri_part
        safe_property = slugify_uri_part(relationship_name)
        return mint_uri(self.base_uri, self.organization_id, "properties", safe_property)

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
