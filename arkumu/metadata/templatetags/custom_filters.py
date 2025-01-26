from django import template

register = template.Library()

@register.filter
def get_attribute(obj, field):
    """
    Gets an attribute of an object dynamically from a string name
    """
    try:
        return getattr(obj, field, '')
    except (AttributeError, TypeError):
        return ''
