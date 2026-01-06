from django_components import Component, register

from depot.components.base_component import BaseComponent


@register("separator")
class SeparatorComponent(BaseComponent):

    template = """
        <div {% html_attrs attrs class="border-t border-gray-200" %}></div>
    """
