from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Min"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iufM"
        ):  # iuf = integer, unsigned integer, float, or datetime
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric.",
            }

        min = variable_data.min()

        if type == "date":
            min = min.strftime("%Y-%m-%d")

        return {
            "status": "success",
            "value": min,
        }
