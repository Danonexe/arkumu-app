"""
Mapping Coordinator - Orchestrates all mapping analyzers to build complete processing plans.

This module is responsible for:
- Coordinating FK analysis, dependency resolution, and configuration extraction
- Building complete FKProcessingPlan for the importer
- Validating the overall mapping configuration
- Providing a clean interface for execution views
"""

import logging
from typing import Dict, List, Any, Optional

from .processing_plan import (
    FKProcessingPlan, FKConfig, ExternalOntologyConfig, 
    AnchorColumnConfig, RelationshipContextConfig, ValidationResult
)
from .fk_analyzer import FKAnalyzer
from .dependency_resolver import DependencyResolver

logger = logging.getLogger(__name__)


class MappingCoordinator:
    """Coordinates all mapping analyzers to build complete processing plans."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
        self.fk_analyzer = FKAnalyzer(organization_id)
        self.dependency_resolver = DependencyResolver()
    
    def build_processing_plan(self, 
                            workspace_columns: Dict[str, Any],
                            selected_datasets: List[str]) -> FKProcessingPlan:
        """
        Build complete FK processing plan from GUI mapping configuration.
        
        Args:
            workspace_columns: GUI mapping configuration
            selected_datasets: List of datasets to process
            
        Returns:
            Complete FKProcessingPlan ready for importer execution
        """
        logger.info(f"Building processing plan for {len(selected_datasets)} datasets with {len(workspace_columns)} configured columns")
        
        plan = FKProcessingPlan(
            organization_id=self.organization_id,
            base_uri=self.base_uri
        )
        
        # Step 1: Extract FK configurations
        plan.fk_relationships = self.fk_analyzer.extract_fk_configurations(workspace_columns)
        logger.info(f"Extracted {len(plan.fk_relationships)} FK relationships")
        
        # Step 2: Extract anchor column configurations  
        plan.anchor_columns = self._extract_anchor_columns(workspace_columns)
        logger.info(f"Extracted {len(plan.anchor_columns)} anchor column configurations")
        
        # Step 3: Extract external ontology configurations
        plan.external_ontologies = self._extract_external_ontologies(workspace_columns)
        logger.info(f"Extracted {len(plan.external_ontologies)} external ontology configurations")
        
        # Step 4: Extract relationship context configurations
        plan.relationship_contexts = self._extract_relationship_contexts(workspace_columns)
        logger.info(f"Extracted {len(plan.relationship_contexts)} relationship context configurations")
        
        # Step 5: Extract multi-value configurations
        plan.multi_value_columns = self._extract_multi_value_columns(workspace_columns)
        logger.info(f"Extracted {len(plan.multi_value_columns)} multi-value column configurations")
        
        # Step 6: Build processing order based on FK dependencies
        plan.processing_order = self.dependency_resolver.build_processing_order(
            plan.fk_relationships, 
            selected_datasets
        )
        logger.info(f"Built processing order with {len(plan.processing_order)} layers")
        
        return plan
    
    def validate_processing_plan(self, 
                               plan: FKProcessingPlan,
                               available_datasets: List[str]) -> ValidationResult:
        """
        Validate complete processing plan.
        
        Args:
            plan: Processing plan to validate
            available_datasets: Available datasets for validation
            
        Returns:
            ValidationResult with errors and warnings
        """
        logger.info("Validating processing plan")
        
        result = ValidationResult(is_valid=True)
        
        # Validate FK configurations
        fk_validation = self.fk_analyzer.validate_fk_configurations(
            plan.fk_relationships, 
            available_datasets
        )
        result.errors.extend(fk_validation.errors)
        result.warnings.extend(fk_validation.warnings)
        if not fk_validation.is_valid:
            result.is_valid = False
        
        # Validate processing order
        processing_errors = self.dependency_resolver.validate_processing_order(
            plan.processing_order,
            plan.fk_relationships
        )
        result.errors.extend(processing_errors)
        if processing_errors:
            result.is_valid = False
        
        # Validate external ontology configurations
        ontology_validation = self._validate_external_ontologies(plan.external_ontologies)
        result.errors.extend(ontology_validation.errors)
        result.warnings.extend(ontology_validation.warnings)
        if not ontology_validation.is_valid:
            result.is_valid = False
        
        # Validate anchor columns
        anchor_validation = self._validate_anchor_columns(plan.anchor_columns, available_datasets)
        result.errors.extend(anchor_validation.errors)
        result.warnings.extend(anchor_validation.warnings)
        if not anchor_validation.is_valid:
            result.is_valid = False
        
        logger.info(f"Validation complete: {'PASSED' if result.is_valid else 'FAILED'} with {len(result.errors)} errors and {len(result.warnings)} warnings")
        
        return result
    
    def analyze_plan_complexity(self, plan: FKProcessingPlan) -> Dict[str, Any]:
        """
        Analyze processing plan complexity for optimization and reporting.
        
        Args:
            plan: Processing plan to analyze
            
        Returns:
            Analysis results
        """
        analysis = {}
        
        # FK complexity analysis
        fk_complexity = self.fk_analyzer.analyze_fk_complexity(plan.fk_relationships)
        analysis['fk_complexity'] = fk_complexity
        
        # Processing order complexity
        processing_complexity = self.dependency_resolver.analyze_processing_complexity(
            plan.processing_order,
            plan.fk_relationships
        )
        analysis['processing_complexity'] = processing_complexity
        
        # External ontology analysis
        analysis['external_ontology_complexity'] = {
            'total_external_columns': len(plan.external_ontologies),
            'ontology_types': list(set(config.ontology_type for config in plan.external_ontologies.values())),
            'patterns_count': len(set(config.identifier_pattern for config in plan.external_ontologies.values() if config.identifier_pattern))
        }
        
        # Overall complexity score
        complexity_score = self._calculate_complexity_score(plan)
        analysis['overall_complexity'] = {
            'score': complexity_score,
            'level': self._get_complexity_level(complexity_score)
        }
        
        return analysis
    
    def get_optimization_suggestions(self, plan: FKProcessingPlan) -> List[str]:
        """
        Get optimization suggestions for the processing plan.
        
        Args:
            plan: Processing plan to optimize
            
        Returns:
            List of optimization suggestions
        """
        suggestions = []
        
        # FK relationship suggestions
        fk_suggestions = self.dependency_resolver.suggest_optimizations(
            plan.processing_order,
            plan.fk_relationships
        )
        suggestions.extend(fk_suggestions)
        
        # External ontology suggestions
        if len(plan.external_ontologies) > 20:
            suggestions.append(
                f"Large number of external ontology columns ({len(plan.external_ontologies)}) - "
                "consider caching external URI resolution for better performance"
            )
        
        # Multi-value column suggestions
        if len(plan.multi_value_columns) > 10:
            suggestions.append(
                f"Many multi-value columns ({len(plan.multi_value_columns)}) detected - "
                "ensure adequate memory allocation for value splitting"
            )
        
        return suggestions
    
    def _extract_anchor_columns(self, workspace_columns: Dict[str, Any]) -> Dict[str, AnchorColumnConfig]:
        """Extract anchor column configurations from workspace_columns."""
        anchor_configs = {}
        
        for column_id, column_config in workspace_columns.items():
            if not column_config.get('is_anchor', False):
                continue
            
            # Parse column_id: "org::dataset::column"
            source_info = self.fk_analyzer._parse_column_id(column_id)
            if not source_info:
                logger.error(f"Could not parse column_id: {column_id}")
                continue
            
            dataset = source_info['dataset']
            column = source_info['column']
            
            anchor_config = AnchorColumnConfig(
                dataset=dataset,
                column=column,
                is_composite=column_config.get('is_composite_anchor', False),
                composite_columns=column_config.get('composite_anchor_columns', [])
            )
            
            anchor_configs[dataset] = anchor_config
            logger.debug(f"Extracted anchor column: {dataset}.{column}")
        
        return anchor_configs
    
    def _extract_external_ontologies(self, workspace_columns: Dict[str, Any]) -> Dict[str, ExternalOntologyConfig]:
        """Extract external ontology configurations from workspace_columns."""
        ontology_configs = {}
        
        for column_id, column_config in workspace_columns.items():
            if not column_config.get('is_external_ontology', False):
                continue
            
            ontology_data = column_config.get('external_ontology', {})
            if not ontology_data:
                logger.warning(f"Column {column_id} marked as external ontology but missing configuration")
                continue
            
            ontology_config = ExternalOntologyConfig(
                ontology_type=ontology_data.get('ontology_type', ''),
                uri_template=ontology_data.get('uri_template', ''),
                identifier_pattern=ontology_data.get('identifier_pattern')
            )
            
            ontology_configs[column_id] = ontology_config
            logger.debug(f"Extracted external ontology: {column_id} -> {ontology_config.ontology_type}")
        
        return ontology_configs
    
    def _extract_relationship_contexts(self, workspace_columns: Dict[str, Any]) -> Dict[str, RelationshipContextConfig]:
        """Extract relationship context configurations from workspace_columns."""
        context_configs = {}
        
        for column_id, column_config in workspace_columns.items():
            if not column_config.get('is_relationship_context', False):
                continue
            
            context_data = column_config.get('relationship_context', {})
            if not context_data:
                logger.warning(f"Column {column_id} marked as relationship context but missing configuration")
                continue
            
            # Parse column_id for context dataset
            source_info = self.fk_analyzer._parse_column_id(column_id)
            if not source_info:
                logger.error(f"Could not parse column_id: {column_id}")
                continue
            
            context_config = RelationshipContextConfig(
                context_predicate=context_data.get('context_predicate', ''),
                primary_fk_dataset=context_data.get('primary_fk_dataset', ''),
                primary_fk_column=context_data.get('primary_fk_column', ''),
                secondary_fk_dataset=context_data.get('secondary_fk_dataset', ''),
                secondary_fk_column=context_data.get('secondary_fk_column', ''),
                context_dataset=source_info['dataset']
            )
            
            context_configs[column_id] = context_config
            logger.debug(f"Extracted relationship context: {column_id}")
        
        return context_configs
    
    def _extract_multi_value_columns(self, workspace_columns: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract multi-value column configurations from workspace_columns."""
        multi_value_configs = {}
        
        for column_id, column_config in workspace_columns.items():
            if not column_config.get('is_multi_value', False):
                continue
            
            multi_value_configs[column_id] = {
                'separator': column_config.get('multi_value_separator', ','),
                'clean_values': column_config.get('clean_multi_values', True),
                'skip_empty': column_config.get('skip_empty_values', True)
            }
            
            logger.debug(f"Extracted multi-value config: {column_id}")
        
        return multi_value_configs
    
    def _validate_external_ontologies(self, ontology_configs: Dict[str, ExternalOntologyConfig]) -> ValidationResult:
        """Validate external ontology configurations."""
        result = ValidationResult(is_valid=True)
        
        for column_id, config in ontology_configs.items():
            if not config.ontology_type:
                result.add_error(f"External ontology {column_id} missing ontology_type")
            
            if not config.uri_template:
                result.add_error(f"External ontology {column_id} missing uri_template")
            elif '{identifier}' not in config.uri_template:
                result.add_warning(f"External ontology {column_id} uri_template missing {{identifier}} placeholder")
        
        return result
    
    def _validate_anchor_columns(self, 
                                anchor_configs: Dict[str, AnchorColumnConfig],
                                available_datasets: List[str]) -> ValidationResult:
        """Validate anchor column configurations."""
        result = ValidationResult(is_valid=True)
        
        for dataset, config in anchor_configs.items():
            if dataset not in available_datasets:
                result.add_error(f"Anchor column configured for unavailable dataset: {dataset}")
        
        # Check for datasets without anchor columns
        datasets_without_anchors = set(available_datasets) - set(anchor_configs.keys())
        for dataset in datasets_without_anchors:
            result.add_warning(f"Dataset {dataset} has no configured anchor column, will use first column")
        
        return result
    
    def _calculate_complexity_score(self, plan: FKProcessingPlan) -> float:
        """Calculate overall complexity score for the processing plan."""
        score = 0.0
        
        # FK complexity (0-40 points)
        fk_count = len(plan.fk_relationships)
        score += min(fk_count * 2, 40)
        
        # Processing layers (0-30 points)
        layer_count = len(plan.processing_order)
        score += min(layer_count * 5, 30)
        
        # External ontologies (0-20 points)
        ontology_count = len(plan.external_ontologies)
        score += min(ontology_count * 1, 20)
        
        # Multi-value columns (0-10 points)
        multi_value_count = len(plan.multi_value_columns)
        score += min(multi_value_count * 0.5, 10)
        
        return score
    
    def _get_complexity_level(self, score: float) -> str:
        """Convert complexity score to descriptive level."""
        if score < 20:
            return "Simple"
        elif score < 50:
            return "Moderate"
        elif score < 80:
            return "Complex"
        else:
            return "Very Complex" 