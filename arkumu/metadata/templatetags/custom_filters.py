from django import template
import re

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

@register.filter
def highlight_search(text, search_term):
    """Highlights the search term in the text with Bootstrap classes"""
    if not search_term or not text:
        return f"DEBUG: Empty input - text: '{text}', search_term: '{search_term}'"
    
    text = str(text)
    search_term = str(search_term)
    
    print(f"DEBUG: Highlighting '{search_term}' in '{text}'")  # Debug print
    
    escaped_search = re.escape(search_term)
    pattern = re.compile(f'({escaped_search})', re.IGNORECASE)
    
    # Use Bootstrap's bg-warning class for more visible highlighting during testing
    highlighted = pattern.sub(r'<span class="bg-warning fw-bold">\1</span>', text)
    
    return highlighted

# Mark the output as safe HTML
highlight_search.is_safe = True
