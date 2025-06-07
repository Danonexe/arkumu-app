from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()


@register.filter
def confidence_to_color(confidence):
    """Convert confidence score (0-1) to CSS color"""
    try:
        # Handle non-numeric inputs
        if not isinstance(confidence, (int, float)):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                return '#f3f4f6'  # gray-100 for invalid inputs
        
        if confidence == 0:
            return '#f3f4f6'  # gray-100
        
        # Convert to 0-10 scale and map to blue gradient
        level = min(10, max(1, int(confidence * 10)))
    except (TypeError, ValueError):
        return '#f3f4f6'  # gray-100 for any errors
    colors = {
        1: '#dbeafe',  # blue-100
        2: '#bfdbfe',  # blue-200
        3: '#93c5fd',  # blue-300
        4: '#60a5fa',  # blue-400
        5: '#3b82f6',  # blue-500
        6: '#2563eb',  # blue-600
        7: '#1d4ed8',  # blue-700
        8: '#1e40af',  # blue-800
        9: '#1e3a8a',  # blue-900
        10: '#172554'  # blue-950
    }
    return colors.get(level, '#3b82f6')


@register.filter
def high_confidence_count(relationships):
    """Count relationships with confidence > 0.7"""
    if not relationships:
        return 0
    try:
        return len([r for r in relationships if r.get('confidence', 0) > 0.7])
    except (TypeError, ValueError):
        return 0


@register.filter
def relationship_type_color(relationship_type):
    """Get color for relationship type"""
    colors = {
        'semantic_similar': '#3b82f6',    # blue
        'value_overlap': '#10b981',       # green
        'pattern_match': '#f59e0b',       # yellow
        'foreign_key': '#ef4444',         # red
        'cross_dataset_semantic': '#8b5cf6'  # purple
    }
    return colors.get(relationship_type, '#6b7280')  # gray default


@register.filter
def matrix_lookup(dictionary, key):
    """Look up a value in a dictionary safely"""
    if not dictionary or not key:
        return {}
    return dictionary.get(key, {})


@register.filter
def lookup(dictionary, key):
    """Look up a value in a dictionary safely (alias for matrix_lookup)"""
    if not dictionary or not key:
        return {}
    return dictionary.get(key, {})


@register.filter
def slugify_matrix_key(source_col, target_col):
    """Create a safe key for matrix lookup"""
    return f"{source_col}-{target_col}"


@register.filter
def relationship_summary(relationships, max_types=3):
    """Create a summary of relationship types"""
    if not relationships:
        return "No relationships"
    
    from collections import Counter
    type_counts = Counter(r.get('relationship_type', 'unknown') for r in relationships)
    
    summary_parts = []
    for rel_type, count in type_counts.most_common(max_types):
        display_name = rel_type.replace('_', ' ').title()
        summary_parts.append(f"{count} {display_name}")
    
    result = ", ".join(summary_parts)
    if len(type_counts) > max_types:
        result += f" and {len(type_counts) - max_types} more"
    
    return result


@register.filter
def confidence_level(confidence):
    """Convert confidence to descriptive level"""
    if confidence >= 0.8:
        return "High"
    elif confidence >= 0.6:
        return "Medium"
    elif confidence >= 0.4:
        return "Low"
    else:
        return "Very Low"


@register.filter
def format_evidence(evidence):
    """Format evidence dictionary for display"""
    if not evidence:
        return ""
    
    formatted = []
    for key, value in evidence.items():
        if key == 'common_values_count':
            formatted.append(f"{value} common values")
        elif key == 'jaccard_similarity':
            formatted.append(f"Similarity: {value:.2f}")
        elif key == 'overlap_ratio':
            formatted.append(f"Overlap: {value:.1%}")
        elif key == 'common_semantics':
            if value:
                formatted.append(f"Semantics: {', '.join(value)}")
        elif key == 'shared_pattern':
            formatted.append(f"Pattern: {value}")
    
    return "; ".join(formatted)


@register.filter
def relationship_icon(relationship_type):
    """Get icon for relationship type"""
    icons = {
        'semantic_similar': '🔗',
        'value_overlap': '📊',
        'pattern_match': '🎯',
        'foreign_key': '🔑',
        'cross_dataset_semantic': '🌐'
    }
    return icons.get(relationship_type, '❓')


@register.filter
def cluster_color(index):
    """Get color for cluster based on index"""
    colors = [
        '#3b82f6',  # blue
        '#10b981',  # green
        '#f59e0b',  # yellow
        '#ef4444',  # red
        '#8b5cf6',  # purple
        '#06b6d4',  # cyan
        '#84cc16',  # lime
        '#f97316',  # orange
    ]
    return colors[index % len(colors)]


@register.simple_tag
def relationship_matrix_cell(relationship_matrix, source_col, target_col):
    """Get the relationship value for a specific cell in the matrix"""
    key = f"{source_col}-{target_col}"
    return relationship_matrix.get(key, 0.0)


@register.inclusion_tag('partials/relationship_badge.html')
def relationship_badge(relationship):
    """Render a relationship as a badge"""
    return {
        'relationship': relationship,
        'color': relationship_type_color(relationship.get('relationship_type', '')),
        'icon': relationship_icon(relationship.get('relationship_type', ''))
    }


@register.filter
def to_json(value):
    """Convert a Python object to JSON string"""
    try:
        return mark_safe(json.dumps(value))
    except (TypeError, ValueError):
        return '{}'


@register.filter
def get_relationships_for_pair(relationships, pair_key):
    """Get all relationships for a specific column pair"""
    source_col, target_col = pair_key.split('-', 1)
    matching = []
    
    for rel in relationships:
        # Direct match
        if (rel.get('source_column') == source_col and rel.get('target_column') == target_col):
            matching.append(rel)
        # Reverse match for bidirectional relationships
        elif (rel.get('source_column') == target_col and rel.get('target_column') == source_col):
            matching.append(rel)
    
    return matching


@register.filter
def max_confidence_for_pair(relationships, pair_key):
    """Get the maximum confidence for a column pair"""
    matching_relationships = get_relationships_for_pair(relationships, pair_key)
    if not matching_relationships:
        return 0.0
    
    return max(rel.get('confidence', 0.0) for rel in matching_relationships)