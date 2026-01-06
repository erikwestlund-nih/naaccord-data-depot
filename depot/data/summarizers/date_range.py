from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Date Range"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        # Must be date
        if not variable_data.dtype.kind in "M":
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not a date.",
            }

        min = variable_data.min()
        max = variable_data.max()

        years_between = max.year - min.year
        return {
            "status": "success",
            "value": f"{years_between} years",
        }
