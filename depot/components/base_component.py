from django_components import Component


class BaseComponent(Component):
    def get_context_data(self, attrs=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attrs"] = attrs or {}
        return context
