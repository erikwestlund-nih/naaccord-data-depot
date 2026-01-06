from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.variable_summary.data.report")
class AuditVariableSummaryDataReportComponent(AuditComponent):
    template_name = "report.html"

    def get_context_data(
        self,
        report,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        results = report.get("results", [])

        context.update(
            {
                "results": results,
            }
        )

        return context
