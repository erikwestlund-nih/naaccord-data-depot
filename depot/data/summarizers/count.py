from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Count"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        return {
            "status": "success",
            "value": variable_data.count(),
        }
