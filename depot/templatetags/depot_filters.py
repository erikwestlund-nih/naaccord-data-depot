from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
import bleach

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using a key."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)

@register.filter
def render_html_content(text):
    """Render HTML content safely (for Quill editor output)."""
    if not text:
        return ""

    # Handle Unicode escapes from JSON (e.g., \u003C becomes <)
    if '\\u' in text:
        try:
            text = text.encode().decode('unicode-escape')
        except:
            pass  # Use text as-is if decode fails

    # If it looks like HTML, sanitize and return it
    if '<' in text and '>' in text:
        # Sanitize HTML with bleach
        allowed_tags = [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li',
            'a', 'blockquote', 'code', 'pre',
            'div', 'span'
        ]
        allowed_attributes = {
            'a': ['href', 'title', 'target'],
            'div': ['class'],
            'span': ['class'],
        }

        cleaned = bleach.clean(
            text,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
        return mark_safe(cleaned)

    # Otherwise treat as plain text
    return text

@register.filter
def render_markdown(text):
    """Safely render markdown text to HTML."""
    if not text:
        return ""
    
    # Initialize markdown parser with safe defaults
    md = MarkdownIt("commonmark", {"breaks": True, "html": False})
    
    # Convert markdown to HTML
    html = md.render(text)
    
    # Sanitize HTML output with bleach
    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'a', 'code', 'pre', 'blockquote',
        'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]
    allowed_attributes = {
        'a': ['href', 'title'],
        'code': ['class'],
    }
    
    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )
    
    return mark_safe(clean_html)


@register.filter
def intcomma(value):
    """Add commas to integer values."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value


@register.filter
def percentage_of(numerator, denominator):
    """Calculate percentage: (numerator/denominator) * 100"""
    try:
        if int(denominator) == 0:
            return "0.0"
        return f"{(int(numerator) / int(denominator)) * 100:.1f}"
    except (ValueError, TypeError, ZeroDivisionError):
        return "0.0"


@register.filter
def add_spaces_to_camelcase(value):
    """Add spaces before capital letters in camelCase strings."""
    import re
    if not value:
        return value
    # Add space before capital letters (but not at the beginning)
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', str(value))


@register.filter
def replace_underscore(value):
    """Replace underscores with spaces."""
    if not value:
        return value
    return str(value).replace('_', ' ')