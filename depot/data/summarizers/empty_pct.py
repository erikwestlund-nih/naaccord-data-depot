import numpy as np

from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Empty Percent"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable].map(lambda x: np.nan if x == "" else x)
        empty = variable_data.isnull().sum()
        total = variable_data.size
        pct = 100 * empty / total if total > 0 else np.nan

        pct = str(
            int(pct) if isinstance(pct, float) and pct.is_integer() else round(pct, 1)
        )

        return {
            "status": "success",
            "value": pct + "%" if total > 0 else "N/A",
        }
