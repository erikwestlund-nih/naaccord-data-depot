from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Max"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iufM"
        ):  # iuf = integer, unsigned integer, float, or datetime
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric or datetime.",
            }

        max = variable_data.max()

        if type == "date":
            max = max.strftime("%Y-%m-%d")

        return {
            "status": "success",
            "value": max,
        }
