import numpy as np
import pandas as pd

from .base_summarizer import BaseSummarizer, MATPLOTLIB_AVAILABLE

if MATPLOTLIB_AVAILABLE:
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid")
else:
    plt = None
    sns = None


class Summarizer(BaseSummarizer):
    display_name = "Date Histogram"

    def summarize(self, variable, type, data, params=None):
        if not MATPLOTLIB_AVAILABLE:
            return {
                "status": "skipped",
                "message": "matplotlib not available",
            }

        variable_data = data[variable]

        if (
            not variable_data.dtype.kind in "iufM"
        ):  # iuf = integer, unsigned integer, float, or datetime
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric or datetime.",
            }

        hist = self.gen_date_histogram(variable_data, title="Histogram")

        return {
            "status": "success",
            "value": hist,
            "value_rendered": {"type": "base64_image", "data": self.render_plot(hist)},
        }

    def gen_date_histogram(self, date_data, title=None, xlabel=None, ylabel=None):
        if not isinstance(date_data, pd.Series):
            date_data = pd.Series(date_data)

        date_data = pd.to_datetime(date_data, format="%Y", errors="coerce")

        date_data = date_data.dropna()

        min_year = date_data.min().year
        max_year = date_data.max().year
        year_range = max_year - min_year

        if year_range <= 10:
            bins = np.arange(min_year, max_year + 2)
        else:
            bins = np.arange(min_year, max_year + 2, step=max(1, year_range // 10))

        fig, ax = plt.subplots(figsize=(10, 6))

        sns.set_color_codes("pastel")
        sns.histplot(
            date_data.dt.year,
            bins=bins,
            kde=False,
            stat="count",  # Ensure y-axis displays counts
            color="b",
            ax=ax,
        )

        ax.set_xticks(bins)
        ax.set_xticklabels([str(year) for year in bins], rotation=45)

        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

        # Set title and labels
        if title:
            ax.set_title(title, fontsize=16, pad=15)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=12, labelpad=10)
        else:
            ax.set_xlabel("Year", fontsize=12, labelpad=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=12, labelpad=10)
        else:
            ax.set_ylabel("Count", fontsize=12, labelpad=10)

        sns.despine(left=True, bottom=True)

        return fig
