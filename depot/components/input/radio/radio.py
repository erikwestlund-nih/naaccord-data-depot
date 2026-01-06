from django_components import register

from depot.components.input_component import InputComponent


@register("input.radio")
class InputRadioComponent(InputComponent):
    class_attrs = "h-4 w-4 border-gray-300 text-red-600 focus:ring-red-600"
    error_attrs = ""
    template_name = "radio.html"

    def get_data(self, options: list = None, **kwargs):
        if not options:
            options = []
        else:
            options = [
                {"value": option.get("value"), "label": option.get("label")}
                for option in options
            ]

        return {
            "options": options,
        }
