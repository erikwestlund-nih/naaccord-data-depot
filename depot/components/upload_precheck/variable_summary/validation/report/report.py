from django_components import Component, register
from depot.components.audit_component import AuditComponent


@register("audit.variable_summary.validation.report")
class AuditVariableSummaryValidationReportComponent(AuditComponent):
    template_name = "report.html"

    def get_context_data(self, report, **kwargs):
        context = super().get_context_data(**kwargs)

        # print("REPORT:")
        # print(report)

        # Extract status and results
        status = report.get("status", "unknown")
        results = report.get("results", []) if status == "success" else []

        # Ensure results is a list
        if not isinstance(results, list):
            results = []

        # Total validation checks
        total = len(results)

        # Count passing results safely
        passing = sum(
            1
            for result in results
            if isinstance(result, dict) and result.get("report", {}).get("pass", False)
        )

        # Calculate pass rate safely
        pass_rate = round((passing / total * 100) if total > 0 else 0, 1)
        pass_rate = (
            f"{int(pass_rate)}%" if pass_rate.is_integer() else f"{pass_rate:.1f}%"
        )

        # Update context with computed values
        context.update(
            {
                "status": status,
                "results": results,
                "total": total,
                "passing": passing,
                "pass_rate": pass_rate,
            }
        )

        return context
