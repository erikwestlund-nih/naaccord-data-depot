import pandas as pd

from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Potential Outliers"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iuf"
        ):  # iuf = integer, unsigned integer, or float
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric.",
            }

        if not isinstance(data, pd.Series):
            data = pd.Series(data)

        mean = data.mean()
        std_dev = data.std()

        lower_bound = mean - 3 * std_dev
        upper_bound = mean + 3 * std_dev

        outliers = data[(data < lower_bound) | (data > upper_bound)]

        return {"status": "success", "value": ", ".join(outliers.astype(str))}
