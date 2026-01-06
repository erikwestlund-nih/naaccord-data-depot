from typing import Any

from django_components import Component, register
from django_components.component import DataType
from depot.components.base_component import BaseComponent


@register("page_container")
class PageContainerComponent(BaseComponent):
    template = """
        <div class="w-full max-w-3xl mx-auto mb-32">
            {% component "heading" %} {{ heading }} {% endcomponent %}
            <div class="mt-4 sm:mt-6">
            {% slot "body" default %}  {% endslot %}
            </div>
        </div>  
    """

    def get_context_data(self, heading):
        return {
            "heading": heading,
        }
