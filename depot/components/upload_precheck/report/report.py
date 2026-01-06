from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.report")
class AuditReportComponent(AuditComponent):
    template_name = "report.html"

    def get_context_data(
        self,
        report: dict = None,
        **kwargs,
    ):
        if not report:
            report = {
                "validation": {},
                "summary": {},
            }

        context = {
            "data_file_type": report["data_file_type"],
            "data_file_type_label": report["data_file_type_label"],
            "variable_count": report["variable_count"],
            "record_count": report["record_count"],
            "net_empty_pct": report["net_empty_pct"],
            "validation_data": report["validation"],
            "summary_data": report["summary"],
        }

        return context
