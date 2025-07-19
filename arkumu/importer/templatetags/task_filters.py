from django import template

register = template.Library()

@register.filter
def task_state_color(state):
    """Get color class for task state"""
    colors = {
        'pending': 'info',
        'running': 'primary',
        'cancelling': 'warning',
        'cancelled': 'warning',
        'completed': 'success',
        'failed': 'error',
        'error': 'error',
        'not_found': 'neutral'
    }
    return colors.get(state, 'neutral')