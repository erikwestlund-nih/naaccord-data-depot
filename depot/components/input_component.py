from django_components import Component, register

from depot.components.base_component import BaseComponent


class InputComponent(BaseComponent):
    class_attrs = "block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-800 sm:text-sm sm:leading-6"
    error_attrs = "ring-2 ring-red-600"

    def get_data(self, **kwargs):
        return {}

    def get_context_data(
        self,
        name: str,
        attrs: dict = None,
        container_attrs: dict = None,
        type: str = "",
        label: str = "",
        placeholder: str = "",
        autocomplete: str = "",
        xModel: str = "",
        required: bool = False,
        data: dict = None,
        errors: dict = None,
        **kwargs,
    ):
        component_data = self.get_data(**kwargs)

        if not attrs:
            attrs = {}

        if not container_attrs:
            container_attrs = {}

        if not component_data:
            component_data = {}

        if not data:
            data = {}

        if component_data:
            data = {**component_data, **data}

        if not errors:
            errors = {}

        value = data.get(name, "")
        error = name in errors
        error_messages = errors[name]["error_messages"] if name in errors else []

        class_attrs = self.class_attrs

        if "class" in attrs:
            class_attrs += f" {attrs['class']}"

        if error:
            class_attrs += f" {self.error_attrs}"

        attrs["class"] = class_attrs

        context = {
            "name": name,
            "attrs": attrs,
            "container_attrs": container_attrs,
            "type": type,
            "label": label,
            "placeholder": placeholder,
            "autocomplete": autocomplete,
            "xModel": xModel,
            "required": required,
            "value": value,
            "error": error,
            "error_messages": error_messages,
        }

        # This adds anythign in data (which can be passed as component_data or returned from get_data() in the component)
        for key, value in data.items():
            context[key] = value

        return context
