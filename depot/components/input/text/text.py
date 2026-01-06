from django_components import register

from depot.components.input_component import InputComponent


@register("input.text")
class InputTextComponent(InputComponent):
    template_name = "text.html"
