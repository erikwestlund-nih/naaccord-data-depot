# depot/templatetags/svg.py
from django import template
from django.utils.safestring import mark_safe
from django.templatetags.static import static
import os

register = template.Library()


@register.simple_tag
def load_svg(icon, family="regular", class_=""):
    """
    Load an SVG file from static/icons/<family>/<icon>.svg and inject optional class.
    Always includes 'svg-icon' by default.
    """
    from django.conf import settings

    path = os.path.join(settings.BASE_DIR, "static", "icons", family, f"{icon}.svg")

    try:
        with open(path, "r") as f:
            svg = f.read()

        # Combine 'svg-icon' with any provided class
        combined_class = "svg-icon"
        if class_:
            combined_class += f" {class_}"

        if 'class="' in svg:
            svg = svg.replace('class="', f'class="{combined_class} ', 1)
        else:
            svg = svg.replace("<svg ", f'<svg class="{combined_class}" ', 1)

        return mark_safe(svg)

    except FileNotFoundError:
        return mark_safe(f"<!-- SVG not found: {path} -->")
