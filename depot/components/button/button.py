from django_components import register, Component
from depot.components.base_component import BaseComponent


@register("button")
class ButtonComponent(BaseComponent):
    template_name = "button.html"

    def get_context_data(self, type="button", **kwargs):
        return {"type": type}
