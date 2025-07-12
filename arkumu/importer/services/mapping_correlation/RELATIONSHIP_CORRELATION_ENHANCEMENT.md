# Relationship-Aware Correlation Service Enhancement Plan

## Executive Summary

The current correlation service (`correlation_service.py`) successfully validates basic column mappings but lacks support for relationship validation including foreign keys (FK), joins, and relationship contexts (junction tables). This document outlines the current state analysis and a comprehensive enhancement plan.

## Current State Analysis

### What Works ✅

1. **Basic column correlation**: Files are matched to datasets and column existence is validated
2. **Type validation**: Data types are checked against expected types
3. **Exact matching**: Filename-to-dataset matching works correctly
4. **Recommendations**: Basic recommendations for missing files/columns are generated

### Critical Gap Found ❌

The correlation service extracts relationships but **does not use them in correlation analysis**:

- **Line 258**: `MappingExtractor.extract_relationships(mapping_config)` - Relationships are extracted ✅
- **Line 267**: Relationships stored in `MappingAnalysis` ✅  
- **Lines 270-329**: Correlation analysis **ignores relationships entirely** ❌

### Missing Functionality

1. **FK Relationship Validation**: No checking if files contain required FK columns
2. **Cross-Dataset Dependencies**: No validation of referential integrity between datasets
3. **Join Requirements**: No verification that related datasets are both present
4. **Relationship-Based Recommendations**: Missing specific guidance for FK/join issues
5. **Processing Order Validation**: No dependency-based ordering validation

## Supported Relationship Types in Mappings

### 1. Foreign Key Relationships
```python
FKRelationship(
    source_column="ref_id",
    source_dataset="dataset2", 
    target_column="id",
    target_dataset="dataset1",
    relationship_type="references"
)
```

### 2. Property-to-Property Relationships  
```json
"relationships": [
  {
    "from_column": "event_name", 
    "to_column": "location",
    "relationship_type": "P7",
    "description": "Event took place at location"
  }
]
```

### 3. Relationship Contexts (Junction Tables)
```python
RelationshipContext(
    context_id: str,
    primary_fk: str,
    secondary_fk: str,
    context_columns: List[str],  # Additional attributes
    context_type: str,
    dataset_name: str
)
```

## Enhancement Plan

### Phase 1: Extend MappingExtractor

Add comprehensive relationship extraction methods:

```python
@staticmethod
def extract_all_relationships(mapping_config: Dict) -> Dict[str, Any]:
    """Extract all types of relationships from mapping configuration"""
    return {
        'fk_relationships': MappingExtractor.extract_fk_relationships(mapping_config),
        'relationship_contexts': MappingExtractor.extract_relationship_contexts(mapping_config),
        'relationships': mapping_config.get('relationships', [])  # P2P relationships
    }

@staticmethod
def extract_fk_relationships(mapping_config: Dict) -> List[Dict]:
    """Extract FK relationships from both old and new formats"""
    fk_rels = []
    
    # Check new format (fk_relationships)
    if 'fk_relationships' in mapping_config:
        # Parse structured FK configs
        
    # Check workspace columns for FK flags
    workspace_columns = mapping_config.get('workspace_columns', {})
    for col_id, col_data in workspace_columns.items():
        if col_data.get('is_fk'):
            # Extract FK config
            
    return fk_rels

@staticmethod
def extract_relationship_contexts(mapping_config: Dict) -> List[Dict]:
    """Extract junction table configurations with attributes"""
    contexts = []
    relationship_contexts = mapping_config.get('relationship_contexts', {})
    
    for ctx_id, ctx_config in relationship_contexts.items():
        contexts.append({
            'context_id': ctx_id,
            'dataset': ctx_config.get('dataset'),
            'primary_fk': ctx_config.get('primary_fk'),
            'secondary_fk': ctx_config.get('secondary_fk'),
            'context_columns': ctx_config.get('context_columns', [])
        })
    
    return contexts
```

### Phase 2: Create RelationshipValidator Component

New validator class for all relationship types:

```python
class RelationshipValidator:
    """Validates all relationship types in correlation analysis"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_fk_relationships(self, 
                                 fk_rels: List[Dict], 
                                 file_analyses: List[FileAnalysis]) -> Dict:
        """
        Validate FK columns exist and reference valid targets
        
        Returns:
            {
                'valid': bool,
                'issues': [
                    {
                        'type': 'missing_fk_column',
                        'dataset': 'orders',
                        'column': 'customer_id',
                        'target': 'customers.id'
                    }
                ]
            }
        """
        issues = []
        
        for fk in fk_rels:
            # Check source column exists
            source_file = self._find_file_for_dataset(
                fk['source_dataset'], file_analyses
            )
            
            if not source_file:
                issues.append({
                    'type': 'missing_source_dataset',
                    'dataset': fk['source_dataset']
                })
                continue
                
            if fk['source_column'] not in source_file.columns:
                issues.append({
                    'type': 'missing_fk_column',
                    'dataset': fk['source_dataset'],
                    'column': fk['source_column'],
                    'target': f"{fk['target_dataset']}.{fk['target_column']}"
                })
            
            # Check target exists
            target_file = self._find_file_for_dataset(
                fk['target_dataset'], file_analyses
            )
            
            if not target_file:
                issues.append({
                    'type': 'missing_target_dataset',
                    'dataset': fk['target_dataset'],
                    'referenced_by': f"{fk['source_dataset']}.{fk['source_column']}"
                })
            elif fk['target_column'] not in target_file.columns:
                issues.append({
                    'type': 'missing_target_column',
                    'dataset': fk['target_dataset'],
                    'column': fk['target_column']
                })
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
    
    def validate_relationship_contexts(self, 
                                     contexts: List[Dict],
                                     file_analyses: List[FileAnalysis]) -> Dict:
        """Validate junction tables have required FK columns and attributes"""
        issues = []
        
        for ctx in contexts:
            junction_file = self._find_file_for_dataset(
                ctx['dataset'], file_analyses
            )
            
            if not junction_file:
                issues.append({
                    'type': 'missing_junction_table',
                    'dataset': ctx['dataset']
                })
                continue
            
            # Check both FK columns exist
            missing_fks = []
            if ctx['primary_fk'] not in junction_file.columns:
                missing_fks.append(ctx['primary_fk'])
            if ctx['secondary_fk'] not in junction_file.columns:
                missing_fks.append(ctx['secondary_fk'])
                
            if missing_fks:
                issues.append({
                    'type': 'missing_junction_fks',
                    'dataset': ctx['dataset'],
                    'missing_fks': missing_fks
                })
            
            # Check context columns
            missing_attrs = []
            for attr in ctx.get('context_columns', []):
                if attr not in junction_file.columns:
                    missing_attrs.append(attr)
                    
            if missing_attrs:
                issues.append({
                    'type': 'missing_context_attributes',
                    'dataset': ctx['dataset'],
                    'missing_attrs': missing_attrs
                })
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
    
    def validate_join_requirements(self, 
                                  relationships: List[Dict],
                                  file_analyses: List[FileAnalysis]) -> Dict:
        """Validate columns needed for joins exist in both datasets"""
        issues = []
        
        for rel in relationships:
            # Check both columns exist
            from_parts = rel['from_column'].split('.')
            to_parts = rel['to_column'].split('.')
            
            if len(from_parts) == 2:
                dataset, column = from_parts
                file_analysis = self._find_file_for_dataset(dataset, file_analyses)
                if not file_analysis or column not in file_analysis.columns:
                    issues.append({
                        'type': 'missing_join_column',
                        'dataset': dataset,
                        'column': column,
                        'relationship': rel.get('relationship_type')
                    })
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
```

### Phase 3: Enhance Correlation Service

Modify `_perform_exact_correlation_with_validator` to include relationship validation:

```python
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
    
    # 6. Dependency order validation (reuse existing DependencyResolver)
    dependency_validation = self._validate_dependency_order(
        file_analyses, mapping_analysis
    )
    
    return {
        'correlations': correlations,
        'fk_validation': fk_validation,
        'context_validation': context_validation,
        'join_validation': join_validation,
        'dependency_validation': dependency_validation
    }
```

### Phase 4: Enhanced Recommendations

Generate specific recommendations for relationship issues:

```python
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
    
    # Junction table issues  
    for issue in validation_results['context_validation']['issues']:
        if issue['type'] == 'missing_junction_fks':
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
            f"Circular Dependency: {' -> '.join(dep_val['cycle'])} -> ..."
        )
    
    # Join issues
    for issue in validation_results['join_validation']['issues']:
        recommendations.append(
            f"Join Error: Column '{issue['dataset']}.{issue['column']}' "
            f"needed for {issue['relationship']} relationship not found"
        )
    
    return recommendations
```

## Reusable Components

The enhancement plan leverages existing components:

1. **DependencyResolver** (`arkumu/metadata/services/mapping/dependency_resolver.py`)
   - Topological sorting for processing order
   - Cycle detection in dependencies

2. **FKAnalyzer** (`arkumu/metadata/services/mapping/fk_analyzer.py`)
   - FK configuration parsing
   - Target validation logic

3. **MappingValidator** (already integrated)
   - Column mapping validation
   - Type checking

4. **RelationshipDiscoveryService** (`arkumu/metadata/services/relationship_discovery/`)
   - Relationship detection patterns
   - Validation utilities

## Implementation Priority

1. **High Priority**: FK validation (most common use case)
2. **Medium Priority**: Relationship contexts (junction tables)
3. **Low Priority**: Complex join validation

## Testing Strategy

1. Unit tests for each validator method
2. Integration tests with sample mappings containing:
   - Simple FK relationships
   - Multi-level FK chains
   - Junction tables with attributes
   - Circular dependencies
3. Performance tests with large relationship graphs

## Expected Outcomes

- Complete validation of relational integrity in mappings
- Clear, actionable error messages for relationship issues
- Prevention of runtime FK constraint violations
- Proper dependency-based processing order validation
- Support for complex many-to-many relationships with attributes