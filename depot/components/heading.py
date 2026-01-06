from django_components import Component, register
from depot.components.base_component import BaseComponent


@register("heading")
class HeadingComponent(BaseComponent):
    template = """
        <h1 class="text-2xl font-bold leading-9">
            {% slot "body" default / %}
        </h1>
    """
