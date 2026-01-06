import numpy as np

from .base_summarizer import BaseSummarizer, MATPLOTLIB_AVAILABLE

if MATPLOTLIB_AVAILABLE:
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid")
else:
    plt = None
    sns = None


class Summarizer(BaseSummarizer):
    display_name = "Histogram"

    def summarize(self, variable, type, data, params=None):
        if not MATPLOTLIB_AVAILABLE:
            return {
                "status": "skipped",
                "message": "matplotlib not available",
            }

        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iuf"
        ):  # iuf = integer, unsigned integer, or float
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric.",
            }

        hist = self.gen_histogram(variable_data, title="Histogram")

        return {
            "status": "success",
            "value": hist,
            "value_rendered": {"type": "base64_image", "data": self.render_plot(hist)},
        }

    def gen_histogram(self, variable_data, title=None, xlabel=None, ylabel=None):
        fig, ax = plt.subplots(figsize=(8, 6))

        sns.set_color_codes("pastel")
        sns.histplot(
            variable_data,
            kde=False,
            bins=10,
            color="b",
            stat="count",
            # edgecolor="black",
            ax=ax,
        )

        if title:
            ax.set_title(title, fontsize=16, pad=15)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=12, labelpad=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=12, labelpad=10)

        sns.despine(left=True, bottom=True)

        return fig
