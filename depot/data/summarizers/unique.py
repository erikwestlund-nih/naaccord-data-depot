from .base_summarizer import BaseSummarizer


class Summarizer(BaseSummarizer):
    display_name = "Unique Count"

    def summarize(self, variable, type, data, params=None):
        variable_data = data[variable]

        cleaned_data = variable_data.dropna()
        cleaned_data = cleaned_data[cleaned_data != ""]

        return {
            "status": "success",
            "value": (cleaned_data.nunique()),
        }
