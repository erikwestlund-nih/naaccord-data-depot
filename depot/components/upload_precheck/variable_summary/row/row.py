from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.variable_summary.row")
class AuditVariableSummaryRowComponent(AuditComponent):
    template_name = "row.html"

    def get_context_data(
        self,
        name,
        value_type=None,
        subtle=False,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        context.update(
            {
                "name": name,
                "description": value_type,
                "subtle": subtle,
                "value_type": value_type,
            }
        )

        return context
