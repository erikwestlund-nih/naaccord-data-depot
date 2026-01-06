import numpy as np

from .base_summarizer import BaseSummarizer
from ..utils import filter_empty_values


class Summarizer(BaseSummarizer):
    display_name = "Example Values"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        unique_values = (
            variable_data.value_counts()
            .rename_axis("value")
            .reset_index(name="count")
            .sort_values(
                ["count", "value"], ascending=[False, True]
            )  # Sort by count (desc), then value (asc)
            .head(20)
            .set_index("value")["count"]
        )

        unique_values = filter_empty_values(unique_values)

        return {
            "status": "success",
            "value": unique_values.to_dict(),
        }
