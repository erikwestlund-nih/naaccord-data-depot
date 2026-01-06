from django_components import register

from depot.components.input_component import InputComponent


@register("input.textarea")
class InputTextareaComponent(InputComponent):
    template_name = "textarea.html"
    rows = 3
