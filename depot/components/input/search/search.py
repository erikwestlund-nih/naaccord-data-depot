from django_components import register

from depot.components.input_component import InputComponent


@register("input.search")
class InputSearchComponent(InputComponent):
    template_name = "search.html"
