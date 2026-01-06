from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.variable_summary")
class AuditVariableSummaryComponent(AuditComponent):
    template_name = "variable_summary.html"

    def get_context_data(
        self,
        summary_data,
        validation_data,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        variable_list = self.get_variable_list(summary_data)

        # zip together the summary data and the validation data
        data = {
            variable: {
                "name": variable,
                "type": (
                    summary_data[variable]["type"]
                    if "type" in summary_data[variable]
                    else None
                ),
                "description": (
                    summary_data[variable]["description"]
                    if "description" in summary_data[variable]
                    else None
                ),
                "summary": (
                    summary_data[variable] if variable in summary_data else None
                ),
                "validation": (
                    validation_data[variable] if variable in validation_data else None
                ),
            }
            for variable in variable_list
        }

        context.update(
            {
                "variables": data,
            }
        )

        return context

    def get_variable_list(self, summary_data):
        return [name for name in summary_data]
