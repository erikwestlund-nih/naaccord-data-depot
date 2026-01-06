from django_components import Component, register

from depot.components.audit_component import AuditComponent


@register("audit.variable_summary.validation.error_summary")
class AuditVariableSummaryValidationReportComponent(AuditComponent):
    template_name = "error_summary.html"

    def get_context_data(
        self,
        errors,
        render_empty=False,
        **kwargs,
    ):
        context = super().get_context_data(**kwargs)

        processed_errors = self.process_errors(errors, render_empty)

        print("HELLLLLO")

        non_empty_error_count = [
            error for error in processed_errors if error["value"] or render_empty
        ]

        context.update(
            {
                "errors": processed_errors,
                "total_renderable_errors": len(processed_errors),
            }
        )

        return context

    def process_errors(self, errors, render_empty):
        # We filter out errors with empty values becuase these should be handled using the "required" validator.

        if render_empty:
            return [
                {
                    "value": error["value"] if error["value"] != "" else "(Missing)",
                    "rows": self.compress_row_ranges(
                        [record["row"] for record in error["records"]]
                    ),
                }
                for error in errors
            ]
        else:
            return [
                {
                    "value": error["value"],
                    "rows": self.compress_row_ranges(
                        [record["row"] for record in error["records"]]
                    ),
                }
                for error in errors
                if error["value"]
            ]

    def compress_row_ranges(self, rows):
        if not rows:
            return ""

        rows = sorted(set(rows))
        ranges = []
        start = prev = rows[0]

        print("TEST")

        for num in rows[1:]:
            if num == prev + 1:
                prev = num
            else:
                ranges.append((start, prev))
                start = prev = num

        ranges.append((start, prev))  # add the last range

        return ", ".join(
            f"{start}-{end}" if start != end else str(start) for start, end in ranges
        )
