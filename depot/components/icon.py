import os
from django.conf import settings
from django_components import Component, register
from django.utils.safestring import mark_safe
from bs4 import BeautifulSoup  # Use to manipulate SVG content
from depot.components.base_component import BaseComponent


@register("icon")
class IconComponent(BaseComponent):
    # Define which arguments this component accepts
    def get_context_data(self, icon, family="regular", class_attr="", c=""):
        class_attr = c if c else class_attr

        svg_html = self.get_svg_html(icon, family=family, class_attr=class_attr)

        return {
            "svg_html": svg_html,
        }

    template = """
        {{ svg_html }}
    """

    # This method renders the actual SVG
    def get_svg_html(self, icon, family="fas", class_attr=""):
        # Construct the path to the SVG file based on the type
        icon_path = os.path.join(
            settings.BASE_DIR, "static/icons", family, f"{icon}.svg"
        )

        try:
            with open(icon_path, "r") as svg_file:
                svg_content = svg_file.read()

                # Use BeautifulSoup to parse the SVG and add the custom class
                soup = BeautifulSoup(svg_content, "html.parser")
                svg_tag = soup.find("svg")

                # Add the class attribute
                if svg_tag and class_attr:
                    svg_tag["class"] = "svg-icon " + class_attr

                # Return the modified SVG content
                return mark_safe(str(svg_tag))
        except FileNotFoundError:
            return mark_safe(f"<!-- Icon not found: {icon_path} -->")
