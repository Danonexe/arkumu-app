"""
Preview Service

Provides preview and simulation capabilities for semantic transformations.
Allows users to see transformation impact before applying changes.
"""

import polars as pl
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PreviewChange:
    """Represents a single change that would be made during transformation"""
    type: str  # 'entity_creation', 'relationship_creation', 'type_assignment'
    source_data: Dict[str, Any]
    target_data: Dict[str, Any]
    confidence: float
    rule_id: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class PreviewSummary:
    """Summary of preview results"""
    total_changes: int
    changes_by_type: Dict[str, int]
    estimated_entities: int
    estimated_relationships: int
    estimated_triples: int
    quality_issues: List[str]
    warnings: List[str]
    dataset_impact: Dict[str, Any]


class PreviewService:
    """Service for previewing transformation results before execution"""
    
    def __init__(self, table_analysis_service, mapping_config_service, 
                 reference_resolution_service, validation_service):
        """
        Initialize with required services
        
        Args:
            table_analysis_service: TableAnalysisService instance
            mapping_config_service: MappingConfigurationService instance
            reference_resolution_service: ReferenceResolutionService instance
            validation_service: ValidationService instance
        """
        self.table_analysis = table_analysis_service
        self.mapping_config = mapping_config_service
        self.reference_resolution = reference_resolution_service
        self.validation = validation_service
    
    def preview_dataset_transformation(self, dataset_path: str, configuration_id: str, 
                                     sample_size: int = 100) -> Dict[str, Any]:
        """
        Preview transformation of a single dataset
        
        Args:
            dataset_path: Path to CSV file
            configuration_id: ID of mapping configuration
            sample_size: Number of rows to preview
            
        Returns:
            Dictionary with preview results
        """
        try:
            # Get configuration
            config = self.mapping_config.get_configuration(configuration_id)
            if not config:
                raise ValueError(f"Configuration {configuration_id} not found")
            
            # Analyze dataset
            analysis = self.table_analysis.analyze_csv(dataset_path)
            
            # Read sample data with polars
            df = pl.read_csv(dataset_path, n_rows=sample_size)
            
            # Generate preview changes
            changes = self._simulate_transformation(df, analysis, config)
            
            # Generate summary
            summary = self._generate_preview_summary(changes, analysis, df)
            
            return {
                'dataset_path': dataset_path,
                'configuration_id': configuration_id,
                'analysis': analysis,
                'sample_size': len(df),
                'total_dataset_rows': self._get_total_rows(dataset_path) if sample_size < 1000 else 'large',
                'preview_timestamp': datetime.now().isoformat(),
                'changes': [self._change_to_dict(change) for change in changes],
                'summary': self._summary_to_dict(summary),
                'quality_assessment': self._assess_transformation_quality(changes, analysis)
            }
            
        except Exception as e:
            logger.error(f"Error previewing dataset transformation: {str(e)}")
            raise
    
    def preview_multi_dataset_transformation(self, dataset_paths: List[str], 
                                           configuration_id: str, 
                                           sample_size: int = 50) -> Dict[str, Any]:
        """
        Preview transformation across multiple datasets
        
        Args:
            dataset_paths: List of CSV file paths
            configuration_id: ID of mapping configuration
            sample_size: Number of rows to preview per dataset
            
        Returns:
            Dictionary with aggregated preview results
        """
        try:
            config = self.mapping_config.get_configuration(configuration_id)
            if not config:
                raise ValueError(f"Configuration {configuration_id} not found")
            
            dataset_previews = {}
            all_changes = []
            
            for dataset_path in dataset_paths:
                try:
                    analysis = self.table_analysis.analyze_csv(dataset_path)
                    df = pl.read_csv(dataset_path, n_rows=sample_size)
                    
                    changes = self._simulate_transformation(df, analysis, config)
                    all_changes.extend(changes)
                    
                    dataset_previews[dataset_path] = {
                        'analysis': analysis,
                        'sample_size': len(df),
                        'changes_count': len(changes),
                        'estimated_total_changes': len(changes) * (self._get_total_rows(dataset_path) / len(df)) if len(df) > 0 else 0
                    }
                    
                except Exception as e:
                    logger.error(f"Error previewing dataset {dataset_path}: {str(e)}")
                    dataset_previews[dataset_path] = {'error': str(e)}
            
            # Generate cross-dataset analysis
            cross_dataset_analysis = self._analyze_cross_dataset_relationships(dataset_previews, all_changes)
            
            return {
                'configuration_id': configuration_id,
                'dataset_count': len(dataset_paths),
                'preview_timestamp': datetime.now().isoformat(),
                'dataset_previews': dataset_previews,
                'cross_dataset_analysis': cross_dataset_analysis,
                'aggregate_summary': self._generate_aggregate_summary(all_changes),
                'potential_issues': self._identify_cross_dataset_issues(dataset_previews)
            }
            
        except Exception as e:
            logger.error(f"Error in multi-dataset preview: {str(e)}")
            raise
    
    def preview_relationship_creation(self, dataset_path: str, relationship_templates: List[Dict], 
                                    sample_size: int = 100) -> Dict[str, Any]:
        """
        Preview relationship creation from a dataset
        
        Args:
            dataset_path: Path to CSV file (usually a junction table)
            relationship_templates: List of relationship templates
            sample_size: Number of rows to preview
            
        Returns:
            Dictionary with relationship preview results
        """
        try:
            analysis = self.table_analysis.analyze_csv(dataset_path)
            df = pl.read_csv(dataset_path, n_rows=sample_size)
            
            potential_relationships = []
            relationship_stats = {}
            
            for template in relationship_templates:
                template_relationships = []
                
                for row_data in df.iter_rows(named=True):
                    source_value = row_data.get(template.get('source_column'))
                    target_value = row_data.get(template.get('target_column'))
                    
                    if source_value is not None and target_value is not None:
                        relationship = {
                            'template_id': template.get('id'),
                            'source_value': str(source_value),
                            'target_value': str(target_value),
                            'predicate': template.get('predicate'),
                            'metadata': {col: row_data.get(col) for col in template.get('metadata_columns', [])}
                        }
                        template_relationships.append(relationship)
                
                potential_relationships.extend(template_relationships)
                relationship_stats[template.get('id')] = {
                    'count': len(template_relationships),
                    'template': template
                }
            
            return {
                'dataset_path': dataset_path,
                'table_type': analysis.table_type,
                'sample_size': len(df),
                'potential_relationships': potential_relationships,
                'relationship_stats': relationship_stats,
                'preview_timestamp': datetime.now().isoformat(),
                'estimated_total_relationships': len(potential_relationships) * (self._get_total_rows(dataset_path) / len(df)) if len(df) > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error previewing relationship creation: {str(e)}")
            raise
    
    def validate_preview_quality(self, preview_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the quality of a preview result
        
        Args:
            preview_result: Result from preview_dataset_transformation
            
        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []
        quality_score = 0.0
        
        try:
            changes = preview_result.get('changes', [])
            summary = preview_result.get('summary', {})
            
            # Check for no changes
            if len(changes) == 0:
                issues.append("No transformations would be applied - check mapping configuration")
                quality_score = 0.0
            else:
                # Check confidence levels
                low_confidence_changes = [c for c in changes if c.get('confidence', 1.0) < 0.5]
                if low_confidence_changes:
                    warnings.append(f"{len(low_confidence_changes)} changes have low confidence")
                
                # Check for missing entity types
                entity_changes = [c for c in changes if c['type'] == 'entity_creation']
                untyped_entities = [c for c in entity_changes if not c.get('target_data', {}).get('type')]
                if untyped_entities:
                    issues.append(f"{len(untyped_entities)} entities would be created without semantic types")
                
                # Calculate quality score
                total_changes = len(changes)
                high_confidence = len([c for c in changes if c.get('confidence', 1.0) >= 0.8])
                quality_score = (high_confidence / total_changes) * 100 if total_changes > 0 else 0
            
            return {
                'quality_score': quality_score,
                'issues': issues,
                'warnings': warnings,
                'recommendations': self._generate_quality_recommendations(issues, warnings, summary),
                'validation_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error validating preview quality: {str(e)}")
            return {
                'quality_score': 0.0,
                'issues': [f"Validation error: {str(e)}"],
                'warnings': [],
                'recommendations': []
            }
    
    def _simulate_transformation(self, df: pl.DataFrame, analysis, config) -> List[PreviewChange]:
        """Simulate transformation changes for a dataframe"""
        changes = []
        
        # Simulate entity creation
        entity_changes, entity_context = self._preview_entity_creation(df, analysis, config)
        changes.extend(entity_changes)
        
        # Simulate relationship creation
        relationship_changes, relationship_context = self._preview_relationship_creation(df, analysis, config)
        changes.extend(relationship_changes)
        
        return changes
    
    def _preview_entity_creation(self, df: pl.DataFrame, analysis, config) -> Tuple[List[PreviewChange], List[Dict]]:
        """Preview entity creation from dataframe"""
        changes = []
        entities = []
        
        entity_rules = config.get('entity_rules', [])
        
        for row_data in df.iter_rows(named=True):
            for rule in entity_rules:
                for col_name, value in row_data.items():
                    if value is None or (isinstance(value, str) and not value.strip()):
                        continue
                    
                    if self._rule_applies(rule, col_name, str(value)):
                        entity_id = self._generate_preview_entity_id(str(value), rule)
                        
                        entity_data = {
                            'id': entity_id,
                            'type': rule.get('target_type'),
                            'source_value': str(value),
                            'source_column': col_name
                        }
                        
                        change = PreviewChange(
                            type='entity_creation',
                            source_data={'column': col_name, 'value': str(value)},
                            target_data=entity_data,
                            confidence=rule.get('confidence', 0.8),
                            rule_id=rule.get('id'),
                            metadata={'rule_type': rule.get('pattern_type')}
                        )
                        
                        changes.append(change)
                        entities.append(entity_data)
        
        return changes, entities
    
    def _preview_relationship_creation(self, df: pl.DataFrame, analysis, config) -> Tuple[List[PreviewChange], List[Dict]]:
        """Preview relationship creation from dataframe"""
        changes = []
        relationships = []
        
        relationship_templates = config.get('relationship_templates', [])
        
        for template in relationship_templates:
            if not self._template_applies_to_table(template, analysis):
                continue
            
            for row_data in df.iter_rows(named=True):
                source_column = template.get('source_column')
                target_column = template.get('target_column')
                
                if not source_column or not target_column:
                    continue
                
                source_value = row_data.get(source_column)
                target_value = row_data.get(target_column)
                
                if source_value is not None and target_value is not None:
                    relationship_data = {
                        'source_entity': f"entity:{source_value}",
                        'target_entity': f"entity:{target_value}",
                        'predicate': template.get('predicate'),
                        'source_value': str(source_value),
                        'target_value': str(target_value)
                    }
                    
                    change = PreviewChange(
                        type='relationship_creation',
                        source_data={'source': str(source_value), 'target': str(target_value)},
                        target_data=relationship_data,
                        confidence=template.get('confidence', 0.7),
                        rule_id=template.get('id'),
                        metadata={'template_type': template.get('type')}
                    )
                    
                    changes.append(change)
                    relationships.append(relationship_data)
        
        return changes, relationships
    
    def _generate_preview_summary(self, changes: List[PreviewChange], analysis, df: pl.DataFrame) -> PreviewSummary:
        """Generate summary of preview changes"""
        changes_by_type = {}
        for change in changes:
            changes_by_type[change.type] = changes_by_type.get(change.type, 0) + 1
        
        entity_changes = [c for c in changes if c.type == 'entity_creation']
        relationship_changes = [c for c in changes if c.type == 'relationship_creation']
        
        # Estimate totals (very rough)
        estimated_triples = len(entity_changes) * 2 + len(relationship_changes)  # entities have type + label, relationships are 1 triple
        
        quality_issues = []
        warnings = []
        
        # Check for potential issues
        if len(changes) == 0:
            quality_issues.append("No transformations would be applied")
        
        low_confidence = [c for c in changes if c.confidence < 0.5]
        if low_confidence:
            warnings.append(f"{len(low_confidence)} changes have low confidence")
        
        return PreviewSummary(
            total_changes=len(changes),
            changes_by_type=changes_by_type,
            estimated_entities=len(entity_changes),
            estimated_relationships=len(relationship_changes),
            estimated_triples=estimated_triples,
            quality_issues=quality_issues,
            warnings=warnings,
            dataset_impact={
                'rows_processed': len(df),
                'columns_analyzed': analysis.column_count,
                'table_type': analysis.table_type,
                'quality_score': analysis.quality_score
            }
        )
    
    def _rule_applies(self, rule: Dict[str, Any], col_name: str, value: str) -> bool:
        """Check if a rule applies to a column/value combination"""
        pattern_type = rule.get('pattern_type', 'contains')
        pattern_value = rule.get('pattern_value', '')
        
        if pattern_type == 'prefix':
            return value.startswith(pattern_value)
        elif pattern_type == 'suffix':
            return value.endswith(pattern_value)
        elif pattern_type == 'contains':
            return pattern_value in value
        elif pattern_type == 'column_name':
            return pattern_value in col_name
        
        return False
    
    def _template_applies_to_table(self, template: Dict[str, Any], analysis) -> bool:
        """Check if a relationship template applies to a table"""
        # Check table type compatibility
        if template.get('table_type') and template.get('table_type') != analysis.table_type:
            return False
        
        # Check if required columns exist
        source_col = template.get('source_column')
        target_col = template.get('target_column')
        
        if source_col and target_col:
            col_names = [col.name for col in analysis.columns]
            return source_col in col_names and target_col in col_names
        
        return True
    
    def _generate_preview_entity_id(self, value: str, rule: Dict[str, Any]) -> str:
        """Generate a preview entity ID"""
        prefix = rule.get('id_prefix', 'entity')
        safe_value = value.replace(' ', '_').replace('/', '_')
        return f"{prefix}:{safe_value}"
    
    def _get_total_rows(self, dataset_path: str) -> int:
        """Get total number of rows in dataset"""
        try:
            # Use polars to count rows efficiently
            return pl.read_csv(dataset_path).height
        except Exception:
            return 0
    
    def _analyze_cross_dataset_relationships(self, dataset_previews: Dict, all_changes: List[PreviewChange]) -> Dict[str, Any]:
        """Analyze potential relationships across datasets"""
        # Simple implementation - could be much more sophisticated
        entity_types = {}
        potential_links = []
        
        for change in all_changes:
            if change.type == 'entity_creation':
                entity_type = change.target_data.get('type')
                if entity_type:
                    entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
        
        return {
            'entity_types_found': entity_types,
            'potential_cross_links': potential_links,
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _generate_aggregate_summary(self, all_changes: List[PreviewChange]) -> Dict[str, Any]:
        """Generate aggregate summary across all datasets"""
        total_entities = len([c for c in all_changes if c.type == 'entity_creation'])
        total_relationships = len([c for c in all_changes if c.type == 'relationship_creation'])
        
        avg_confidence = sum(c.confidence for c in all_changes) / len(all_changes) if all_changes else 0
        
        return {
            'total_changes': len(all_changes),
            'total_entities': total_entities,
            'total_relationships': total_relationships,
            'average_confidence': avg_confidence,
            'estimated_triples': total_entities * 2 + total_relationships
        }
    
    def _identify_cross_dataset_issues(self, dataset_previews: Dict) -> List[str]:
        """Identify potential issues across datasets"""
        issues = []
        
        # Check for datasets with errors
        error_datasets = [path for path, preview in dataset_previews.items() if 'error' in preview]
        if error_datasets:
            issues.append(f"Errors in datasets: {', '.join(error_datasets)}")
        
        # Check for datasets with no changes
        no_change_datasets = [path for path, preview in dataset_previews.items() 
                            if preview.get('changes_count', 0) == 0]
        if no_change_datasets:
            issues.append(f"No changes in datasets: {', '.join(no_change_datasets)}")
        
        return issues
    
    def _assess_transformation_quality(self, changes: List[PreviewChange], analysis) -> Dict[str, Any]:
        """Assess the quality of the planned transformation"""
        if not changes:
            return {
                'score': 0.0,
                'level': 'poor',
                'issues': ['No transformations planned'],
                'recommendations': ['Check mapping configuration']
            }
        
        # Calculate confidence-based score
        avg_confidence = sum(c.confidence for c in changes) / len(changes)
        
        # Assess coverage
        columns_with_changes = len(set(c.source_data.get('column') for c in changes if c.source_data.get('column')))
        coverage = columns_with_changes / analysis.column_count if analysis.column_count > 0 else 0
        
        # Combined score
        score = (avg_confidence * 0.7 + coverage * 0.3) * 100
        
        if score >= 80:
            level = 'excellent'
        elif score >= 60:
            level = 'good'
        elif score >= 40:
            level = 'fair'
        else:
            level = 'poor'
        
        return {
            'score': score,
            'level': level,
            'confidence': avg_confidence * 100,
            'coverage': coverage * 100,
            'issues': self._identify_quality_issues(changes, analysis),
            'recommendations': self._generate_quality_recommendations([], [], {'total_changes': len(changes)})
        }
    
    def _identify_quality_issues(self, changes: List[PreviewChange], analysis) -> List[str]:
        """Identify quality issues in planned transformation"""
        issues = []
        
        low_confidence = [c for c in changes if c.confidence < 0.5]
        if low_confidence:
            issues.append(f"{len(low_confidence)} changes have low confidence")
        
        untyped_entities = [c for c in changes if c.type == 'entity_creation' and not c.target_data.get('type')]
        if untyped_entities:
            issues.append(f"{len(untyped_entities)} entities would be created without types")
        
        return issues
    
    def _generate_quality_recommendations(self, issues: List[str], warnings: List[str], 
                                        summary: Dict[str, Any]) -> List[str]:
        """Generate recommendations for improving transformation quality"""
        recommendations = []
        
        if 'No transformations' in str(issues):
            recommendations.append("Add mapping rules to your configuration")
        
        if 'low confidence' in str(warnings):
            recommendations.append("Review and refine mapping patterns for better confidence")
        
        if summary.get('total_changes', 0) == 0:
            recommendations.append("Check that your data matches the configured patterns")
        
        return recommendations
    
    def _change_to_dict(self, change: PreviewChange) -> Dict[str, Any]:
        """Convert PreviewChange to dictionary"""
        return {
            'type': change.type,
            'source_data': change.source_data,
            'target_data': change.target_data,
            'confidence': change.confidence,
            'rule_id': change.rule_id,
            'metadata': change.metadata
        }
    
    def _summary_to_dict(self, summary: PreviewSummary) -> Dict[str, Any]:
        """Convert PreviewSummary to dictionary"""
        return {
            'total_changes': summary.total_changes,
            'changes_by_type': summary.changes_by_type,
            'estimated_entities': summary.estimated_entities,
            'estimated_relationships': summary.estimated_relationships,
            'estimated_triples': summary.estimated_triples,
            'quality_issues': summary.quality_issues,
            'warnings': summary.warnings,
            'dataset_impact': summary.dataset_impact
        } 