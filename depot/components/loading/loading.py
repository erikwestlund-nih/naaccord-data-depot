from django_components import register, Component
from depot.components.base_component import BaseComponent


@register("loading")
class LoadingComponent(BaseComponent):
    template_name = "loading.html"

    def get_context_data(self, c="h-4 w-4", **kwargs):
        c = c + " spin"

        return {"c": c}
