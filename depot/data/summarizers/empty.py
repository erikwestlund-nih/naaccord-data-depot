import numpy as np

from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Empty Count"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable].map(lambda x: np.nan if x == "" else x)

        return {
            "status": "success",
            "value": variable_data.isnull().sum(),
        }
