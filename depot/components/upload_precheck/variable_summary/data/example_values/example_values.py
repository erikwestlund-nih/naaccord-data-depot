from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.variable_summary.data.example_values")
class AuditVariableSummaryDataExampleValuesComponent(AuditComponent):
    template_name = "example_values.html"

    def get_context_data(
        self,
        report,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        values = report.get("value", {})

        context.update(
            {
                "values": values,
                "total_values": len(values),
            }
        )

        return context
