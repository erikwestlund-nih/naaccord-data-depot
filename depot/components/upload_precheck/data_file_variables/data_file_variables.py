from django_components import Component, register
from depot.components.audit_component import AuditComponent


@register("audit.data_file_variables")
class AuditDataFileVariablesComponent(AuditComponent):
    template_name = "data_file_variables.html"

    def get_context_data(
        self,
        validation_data,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        data = validation_data["data_file_variables"]

        context.update(
            {
                "data_file_variables": self.parse_data_file_variables(data),
                "extra_variables": data["extra_variables"],
            }
        )

        return context

    def parse_data_file_variables(self, data):
        return [
            {
                "name": variable,
                "missing_pct": data["missingness"][variable],
                "exists": variable in data["observed_variables"],
            }
            for variable in data["expected_variables"]
        ]
