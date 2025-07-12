"""
DEPRECATED Validation Service

⚠️  WARNING: This module is DEPRECATED!
Use arkumu.importer.services.mapping_validation.validator.MappingValidator instead.

This legacy validator is too strict and expects deprecated 'selected_datasets' format.
The new MappingValidator handles modern mapping structures correctly.
"""

import logging
import warnings
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of mapping validation"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""
    
    def add_error(self, message: str):
        """Add an error message"""
        self.errors.append(message)
        self.is_valid = False
        
    def add_warning(self, message: str):
        """Add a warning message"""
        self.warnings.append(message)
    
    def has_issues(self) -> bool:
        """Check if there are any errors or warnings"""
        return len(self.errors) > 0 or len(self.warnings) > 0


class ValidationService:
    """
    DEPRECATED: Validates mapping configurations for execution readiness.
    
    ⚠️  Use arkumu.importer.services.mapping_validation.validator.MappingValidator instead.
    
    Performs comprehensive validation to ensure mappings can be executed
    successfully by the execution engine.
    """
    
    def __init__(self):
        warnings.warn(
            "ValidationService is deprecated. Use MappingValidator from "
            "arkumu.importer.services.mapping_validation.validator instead.",
            DeprecationWarning,
            stacklevel=2
        )
    
    def validate_mapping_config(self, mapping_config: Dict[str, Any]) -> ValidationResult:
        """
        Validate complete mapping configuration.
        
        Args:
            mapping_config: Raw mapping configuration from GUI
            
        Returns:
            ValidationResult with validation status and details
        """
        result = ValidationResult(is_valid=True)
        
        try:
            # Validate basic structure
            self._validate_basic_structure(mapping_config, result)
            
            # Validate workspace columns
            self._validate_workspace_columns(mapping_config, result)
            
            # Validate selected datasets
            self._validate_selected_datasets(mapping_config, result)
            
            # Validate FK relationships
            self._validate_fk_relationships(mapping_config, result)
            
            # Validate relationship contexts
            self._validate_relationship_contexts(mapping_config, result)
            
            # Validate external ontologies
            self._validate_external_ontologies(mapping_config, result)
            
            # Validate import strategy
            self._validate_import_strategy(mapping_config, result)
            
            # Generate summary
            self._generate_validation_summary(mapping_config, result)
            
        except Exception as e:
            logger.error(f"Validation failed with exception: {e}")
            result.add_error(f"Validation failed: {str(e)}")
        
        return result
    
    def _validate_basic_structure(self, config: Dict[str, Any], result: ValidationResult):
        """Validate basic configuration structure"""
        
        required_fields = ['workspace_columns', 'selected_datasets']
        for field in required_fields:
            if field not in config:
                result.add_error(f"Missing required field: {field}")
        
        # Check version
        version = config.get('version', '1.0')
        if version not in ['1.0', '1.1']:
            result.add_warning(f"Unknown configuration version: {version}")
        
        # Check metadata
        metadata = config.get('_metadata')
        if not metadata:
            result.add_warning("Missing mapping metadata")
        elif not metadata.get('mapping_id'):
            result.add_warning("Missing mapping ID in metadata")
    
    def _validate_workspace_columns(self, config: Dict[str, Any], result: ValidationResult):
        """Validate workspace columns configuration"""
        
        workspace_columns = config.get('workspace_columns', {})
        
        if not workspace_columns:
            result.add_error("No workspace columns configured")
            return
        
        total_columns = 0
        anchor_columns = 0
        
        for dataset_name, columns in workspace_columns.items():
            if not isinstance(columns, dict):
                result.add_error(f"Invalid columns configuration for dataset '{dataset_name}'")
                continue
            
            if not columns:
                result.add_warning(f"No columns configured for dataset '{dataset_name}'")
                continue
            
            dataset_anchor_count = 0
            for column_name, column_config in columns.items():
                total_columns += 1
                
                # Validate column configuration
                if not isinstance(column_config, dict):
                    result.add_error(f"Invalid configuration for column '{dataset_name}.{column_name}'")
                    continue
                
                # Check arkumu_type
                if not column_config.get('arkumu_type'):
                    result.add_warning(f"Missing arkumu_type for column '{dataset_name}.{column_name}'")
                
                # Check anchor columns
                if column_config.get('is_anchor', False):
                    anchor_columns += 1
                    dataset_anchor_count += 1
                
                # Validate multi-value configuration
                if column_config.get('is_multi_value', False):
                    separator = column_config.get('multi_value_separator', ',')
                    if not separator:
                        result.add_warning(f"Multi-value column '{dataset_name}.{column_name}' has empty separator")
                
                # Validate external ontology configuration
                if column_config.get('is_external_ontology', False):
                    ext_config = column_config.get('external_ontology', {})
                    if not ext_config.get('ontology_type'):
                        result.add_error(f"External ontology column '{dataset_name}.{column_name}' missing ontology_type")
                    if not ext_config.get('uri_template'):
                        result.add_error(f"External ontology column '{dataset_name}.{column_name}' missing uri_template")
            
            # Check anchor column count per dataset
            if dataset_anchor_count == 0:
                result.add_warning(f"Dataset '{dataset_name}' has no anchor columns - will use default row IDs")
            elif dataset_anchor_count > 3:
                result.add_warning(f"Dataset '{dataset_name}' has {dataset_anchor_count} anchor columns - may impact performance")
        
        logger.debug(f"Validated {total_columns} columns across {len(workspace_columns)} datasets")
    
    def _validate_selected_datasets(self, config: Dict[str, Any], result: ValidationResult):
        """Validate selected datasets"""
        
        selected_datasets = config.get('selected_datasets', [])
        workspace_columns = config.get('workspace_columns', {})
        
        if not selected_datasets:
            result.add_error("No datasets selected for processing")
            return
        
        # Check that all selected datasets have columns
        for dataset_name in selected_datasets:
            if dataset_name not in workspace_columns:
                result.add_error(f"Selected dataset '{dataset_name}' has no column configuration")
            elif not workspace_columns[dataset_name]:
                result.add_error(f"Selected dataset '{dataset_name}' has empty column configuration")
        
        # Check for datasets with columns but not selected
        for dataset_name in workspace_columns:
            if dataset_name not in selected_datasets:
                result.add_warning(f"Dataset '{dataset_name}' has columns but is not selected")
    
    def _validate_fk_relationships(self, config: Dict[str, Any], result: ValidationResult):
        """Validate FK relationships"""
        
        fk_relationships = config.get('fk_relationships', {})
        workspace_columns = config.get('workspace_columns', {})
        selected_datasets = config.get('selected_datasets', [])
        
        if not fk_relationships:
            logger.debug("No FK relationships to validate")
            return
        
        for fk_id, fk_config in fk_relationships.items():
            # Required fields
            required_fields = ['source_column', 'source_dataset', 'target_column', 'target_dataset']
            for field in required_fields:
                if not fk_config.get(field):
                    result.add_error(f"FK relationship '{fk_id}' missing required field: {field}")
                    continue
            
            source_dataset = fk_config.get('source_dataset')
            source_column = fk_config.get('source_column')
            target_dataset = fk_config.get('target_dataset')
            target_column = fk_config.get('target_column')
            
            # Validate source column exists
            if source_dataset in workspace_columns:
                if source_column not in workspace_columns[source_dataset]:
                    result.add_error(f"FK relationship '{fk_id}' references non-existent source column: {source_dataset}.{source_column}")
            else:
                result.add_error(f"FK relationship '{fk_id}' references non-existent source dataset: {source_dataset}")
            
            # Validate target dataset is selected (target column validation is less strict)
            if target_dataset not in selected_datasets:
                result.add_warning(f"FK relationship '{fk_id}' references unselected target dataset: {target_dataset}")
            
            # Validate relationship type
            relationship_type = fk_config.get('relationship_type')
            if not relationship_type:
                result.add_warning(f"FK relationship '{fk_id}' missing relationship_type")
            
            # Validate multi-value FK configuration
            if fk_config.get('is_multi_value', False):
                separator = fk_config.get('multi_value_separator', ',')
                if not separator:
                    result.add_warning(f"Multi-value FK relationship '{fk_id}' has empty separator")
    
    def _validate_relationship_contexts(self, config: Dict[str, Any], result: ValidationResult):
        """Validate relationship contexts (junction table attributes)"""
        
        relationship_contexts = config.get('relationship_contexts', {})
        fk_relationships = config.get('fk_relationships', {})
        workspace_columns = config.get('workspace_columns', {})
        
        if not relationship_contexts:
            logger.debug("No relationship contexts to validate")
            return
        
        for context_id, context_config in relationship_contexts.items():
            # Required fields
            required_fields = ['primary_fk', 'secondary_fk', 'context_columns', 'dataset_name']
            for field in required_fields:
                if not context_config.get(field):
                    result.add_error(f"Relationship context '{context_id}' missing required field: {field}")
                    continue
            
            primary_fk = context_config.get('primary_fk')
            secondary_fk = context_config.get('secondary_fk')
            context_columns = context_config.get('context_columns', [])
            dataset_name = context_config.get('dataset_name')
            
            # Validate FK references exist
            if primary_fk and primary_fk not in fk_relationships:
                result.add_error(f"Relationship context '{context_id}' references non-existent primary FK: {primary_fk}")
            
            if secondary_fk and secondary_fk not in fk_relationships:
                result.add_error(f"Relationship context '{context_id}' references non-existent secondary FK: {secondary_fk}")
            
            # Validate context columns exist
            if dataset_name in workspace_columns:
                dataset_columns = workspace_columns[dataset_name]
                for column_name in context_columns:
                    if column_name not in dataset_columns:
                        result.add_error(f"Relationship context '{context_id}' references non-existent context column: {dataset_name}.{column_name}")
            else:
                result.add_error(f"Relationship context '{context_id}' references non-existent dataset: {dataset_name}")
    
    def _validate_external_ontologies(self, config: Dict[str, Any], result: ValidationResult):
        """Validate external ontology configurations"""
        
        external_ontologies = config.get('external_ontologies', {})
        workspace_columns = config.get('workspace_columns', {})
        
        if not external_ontologies:
            logger.debug("No external ontologies to validate")
            return
        
        for ontology_id, ontology_config in external_ontologies.items():
            # Required fields
            required_fields = ['column_name', 'dataset_name', 'ontology_type', 'uri_template']
            for field in required_fields:
                if not ontology_config.get(field):
                    result.add_error(f"External ontology '{ontology_id}' missing required field: {field}")
                    continue
            
            column_name = ontology_config.get('column_name')
            dataset_name = ontology_config.get('dataset_name')
            ontology_type = ontology_config.get('ontology_type')
            uri_template = ontology_config.get('uri_template')
            
            # Validate column exists
            if dataset_name in workspace_columns:
                if column_name not in workspace_columns[dataset_name]:
                    result.add_error(f"External ontology '{ontology_id}' references non-existent column: {dataset_name}.{column_name}")
            else:
                result.add_error(f"External ontology '{ontology_id}' references non-existent dataset: {dataset_name}")
            
            # Validate URI template
            if uri_template and '{identifier}' not in uri_template:
                result.add_warning(f"External ontology '{ontology_id}' URI template missing {{identifier}} placeholder")
            
            # Validate known ontology types
            known_types = ['orcid', 'wikidata', 'dublin_core', 'foaf', 'schema_org', 'skos', 'custom']
            if ontology_type not in known_types:
                result.add_warning(f"External ontology '{ontology_id}' uses unknown type: {ontology_type}")
    
    def _validate_import_strategy(self, config: Dict[str, Any], result: ValidationResult):
        """Validate import strategy configuration"""
        
        import_strategy = config.get('import_strategy', {})
        
        if not import_strategy:
            result.add_warning("No import strategy configured - will use defaults")
            return
        
        # Validate update strategy
        update_strategy = import_strategy.get('update_strategy')
        if update_strategy:
            valid_strategies = ['SKIP_EXISTING', 'UPDATE_VALUES', 'TIMESTAMP_BASED']
            if update_strategy not in valid_strategies:
                result.add_warning(f"Unknown update strategy: {update_strategy}")
        
        # Validate bulk size
        bulk_size = import_strategy.get('bulk_size')
        if bulk_size is not None:
            try:
                bulk_size_int = int(bulk_size)
                if bulk_size_int <= 0 or bulk_size_int > 10000:
                    result.add_warning(f"Bulk size {bulk_size_int} may impact performance")
            except (ValueError, TypeError):
                result.add_warning(f"Invalid bulk size: {bulk_size}")
        
        # Validate multi-value threshold
        mv_threshold = import_strategy.get('multi_value_threshold')
        if mv_threshold is not None:
            try:
                threshold_float = float(mv_threshold)
                if threshold_float < 0 or threshold_float > 1:
                    result.add_warning(f"Multi-value threshold should be between 0 and 1, got: {threshold_float}")
            except (ValueError, TypeError):
                result.add_warning(f"Invalid multi-value threshold: {mv_threshold}")
    
    def _generate_validation_summary(self, config: Dict[str, Any], result: ValidationResult):
        """Generate validation summary"""
        
        if result.is_valid and not result.warnings:
            result.summary = "Mapping configuration is valid and ready for execution"
        elif result.is_valid and result.warnings:
            result.summary = f"Mapping configuration is valid with {len(result.warnings)} warnings"
        else:
            result.summary = f"Mapping configuration has {len(result.errors)} errors and {len(result.warnings)} warnings"
        
        # Add detailed statistics
        workspace_columns = config.get('workspace_columns', {})
        selected_datasets = config.get('selected_datasets', [])
        fk_relationships = config.get('fk_relationships', {})
        
        total_columns = sum(len(columns) for columns in workspace_columns.values())
        
        stats = [
            f"{len(selected_datasets)} datasets",
            f"{total_columns} columns",
            f"{len(fk_relationships)} FK relationships"
        ]
        
        result.summary += f" ({', '.join(stats)})"
        
        logger.info(f"Validation completed: {result.summary}")
    
    def quick_validate(self, mapping_config: Dict[str, Any]) -> bool:
        """
        Quick validation check - returns True if mapping is basically valid.
        
        Args:
            mapping_config: Raw mapping configuration
            
        Returns:
            True if mapping passes basic validation
        """
        try:
            # Check required fields
            if not mapping_config.get('workspace_columns'):
                return False
            if not mapping_config.get('selected_datasets'):
                return False
            
            # Check that selected datasets have columns
            workspace_columns = mapping_config['workspace_columns']
            selected_datasets = mapping_config['selected_datasets']
            
            for dataset_name in selected_datasets:
                if dataset_name not in workspace_columns or not workspace_columns[dataset_name]:
                    return False
            
            return True
            
        except Exception:
            return False