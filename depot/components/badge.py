from django_components import Component, register

from depot.components.base_component import BaseComponent


@register("badge")
class BadgeComponent(BaseComponent):

    style_map = {
        "default": {
            "bg": "bg-gray-50",
            "text": "text-gray-600",
            "border": "border-gray-500",
        },
        "gray": {
            "bg": "bg-gray-50",
            "text": "text-gray-600",
            "border": "border-gray-500",
        },
        "red": {
            "bg": "bg-red-50",
            "text": "text-red-700",
            "border": "border-red-600",
        },
        "green": {
            "bg": "bg-green-50",
            "text": "text-green-700",
            "border": "border-green-600",
        },
        "blue": {
            "bg": "bg-blue-50",
            "text": "text-blue-700",
            "border": "border-blue-700",
        },
        "yellow": {
            "bg": "bg-yellow-50",
            "text": "text-yellow-800",
            "border": "border-yellow-600",
        },
    }

    template = """
        <span class="inline-flex items-center rounded-md {{ bg }} px-1.5 py-0.5 text-xs font-medium {{ text }} border {{ border }}/10">
            {% slot "body" default %}  {% endslot %}
        </span>
    """

    def get_context_data(self, color="default", **kwargs):
        context = super().get_context_data(**kwargs)

        bg = self.style_map[color]["bg"]
        text = self.style_map[color]["text"]
        border = self.style_map[color]["border"]

        context.update(
            {
                "bg": bg,
                "text": text,
                "border": border,
            }
        )

        return context
