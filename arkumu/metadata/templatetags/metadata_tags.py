from django import template

register = template.Library()

@register.filter
def get_col_header(index, col_headers):
    """Get the column header at the given index."""
    try:
        if col_headers and index < len(col_headers):
            return col_headers[index]
        return f"column_{index}"
    except:
        return f"column_{index}"

@register.filter
def get_row_id(index, row_ids):
    """Get the row ID at the given index."""
    try:
        if row_ids and index < len(row_ids):
            return row_ids[index]
        return f"row_{index}"
    except:
        return f"row_{index}" 