"""
Template filters for correlation analysis display.

Provides filters for formatting correlation data in templates,
including status badge styling and data formatting utilities.
"""

from django import template
from pathlib import Path

register = template.Library()


@register.filter
def status_badge(status):
    """
    Template filter for correlation status badge classes.
    
    Args:
        status: Status string from correlation result
        
    Returns:
        DaisyUI badge class string
    """
    status_classes = {
        'exact_match': 'badge-success',
        'no_match': 'badge-error', 
        'partial_match': 'badge-warning',
        'matched': 'badge-success',
        'missing': 'badge-error',
        'extra': 'badge-warning',
        'type_mismatch': 'badge-error'
    }
    return status_classes.get(status, 'badge-neutral')


@register.filter
def basename(file_path):
    """
    Template filter to get basename of file path.
    
    Args:
        file_path: Full file path string
        
    Returns:
        File name without directory path
    """
    if not file_path:
        return ''
    return Path(file_path).name


@register.filter
def pluralize(count, args=''):
    """
    Enhanced pluralize filter for correlation counts.
    
    Args:
        count: Number to check for pluralization
        args: Singular and plural forms separated by comma
        
    Returns:
        Appropriate singular or plural form
    """
    if args:
        singular, plural = args.split(',')
    else:
        singular, plural = '', 's'
    
    if count == 1:
        return singular
    return plural


@register.filter
def div(value, divisor):
    """
    Division filter for template calculations.
    
    Args:
        value: Dividend
        divisor: Divisor
        
    Returns:
        Division result or 0 if divisor is 0
    """
    try:
        if divisor == 0:
            return 0
        return float(value) / float(divisor)
    except (ValueError, TypeError):
        return 0


@register.filter
def mul(value, multiplier):
    """
    Multiplication filter for template calculations.
    
    Args:
        value: Value to multiply
        multiplier: Multiplier
        
    Returns:
        Multiplication result
    """
    try:
        return float(value) * float(multiplier)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    """
    Calculate percentage for coverage display.
    
    Args:
        value: Part value
        total: Total value
        
    Returns:
        Percentage as float
    """
    try:
        if total == 0:
            return 0
        return (float(value) / float(total)) * 100
    except (ValueError, TypeError):
        return 0


@register.filter
def correlation_icon(status):
    """
    Get icon for correlation status.
    
    Args:
        status: Correlation status
        
    Returns:
        Unicode icon string
    """
    icons = {
        'exact_match': '✓',
        'no_match': '✗',
        'partial_match': '~',
        'matched': '✓',
        'missing': '✗',
        'extra': '?',
        'type_mismatch': '⚠'
    }
    return icons.get(status, '?')


@register.filter
def issue_count(correlation):
    """
    Calculate total issue count for a correlation.
    
    Args:
        correlation: DatasetCorrelation object
        
    Returns:
        Total number of issues
    """
    if not correlation:
        return 0
    
    issues = 0
    if hasattr(correlation, 'missing_columns'):
        issues += len(correlation.missing_columns)
    if hasattr(correlation, 'type_mismatches'):
        issues += len(correlation.type_mismatches)
    
    return issues


@register.filter
def file_stem(file_path):
    """
    Get file stem (name without extension).
    
    Args:
        file_path: Full file path
        
    Returns:
        File name without extension
    """
    if not file_path:
        return ''
    return Path(file_path).stem


@register.filter
def replace(value, args):
    """
    Replace substring in value.
    
    Args:
        value: String to modify
        args: String in format "old,new" where old is replaced with new
        
    Returns:
        String with replacements made
    """
    if not value or not args:
        return value
    
    try:
        old, new = args.split(',', 1)
        return str(value).replace(old, new)
    except ValueError:
        return value


@register.simple_tag
def coverage_percentage(matched, total):
    """
    Calculate coverage percentage as a template tag.
    
    Args:
        matched: Number of matched items
        total: Total number of items
        
    Returns:
        Coverage percentage
    """
    if total == 0:
        return 100
    return round((matched / total) * 100, 1)