from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Range"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iuf"
        ):  # iuf = integer, unsigned integer, or float
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric.",
            }

        return {
            "status": "success",
            "value": round(variable_data.max() - variable_data.min(), 1),
        }
