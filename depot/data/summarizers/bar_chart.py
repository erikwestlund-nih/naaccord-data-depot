import pandas as pd

from .base_summarizer import BaseSummarizer, MATPLOTLIB_AVAILABLE

if MATPLOTLIB_AVAILABLE:
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid")
else:
    plt = None
    sns = None

from ..utils import filter_empty_values


class Summarizer(BaseSummarizer):
    display_name = "Bar Chart"

    def summarize(self, variable, type, data, params=None):
        if not MATPLOTLIB_AVAILABLE:
            return {
                "status": "skipped",
                "message": "matplotlib not available - using Plotly in templates instead",
            }

        variable_data = data[variable]

        if not isinstance(variable_data, pd.Series):
            raise ValueError("Input must be a pandas Series.")

        # for a bar chart summary, we need to remove empty values
        variable_data = variable_data.dropna()

        variable_data = filter_empty_values(variable_data)
        if variable_data.dtype.name == "category":
            categories = variable_data.cat.categories
            updated_categories = filter_empty_values(categories)
            variable_data = variable_data.cat.rename_categories(updated_categories)
            variable_data = variable_data[~variable_data.isnull()]

        bar_chart = self.gen_bar_chart(
            variable_data,
            title="Category Counts",
            xlabel="Count",
        )

        return {
            "status": "success",
            "value": bar_chart,
            "value_rendered": {
                "type": "base64_image",
                "data": self.render_plot(bar_chart),
            },
        }

    def gen_bar_chart(self, variable_data, title=None, xlabel=None, ylabel=None):
        value_counts = (
            variable_data.value_counts().rename_axis("value").reset_index(name="count")
        )
        value_counts["value"] = value_counts["value"].astype(str)

        # Limit to top 10 values and aggregate the rest
        top_n = 10
        total_unique = len(value_counts)

        if total_unique > top_n:
            top_values = value_counts.head(top_n)
            remaining = value_counts.iloc[top_n:]
            remaining_count = remaining["count"].sum()
            remaining_unique = len(remaining)
            remaining_pct = (remaining_count / value_counts["count"].sum()) * 100

            # Add "Other" row
            other_row = pd.DataFrame({
                "value": [f"Other ({remaining_unique:,} values)"],
                "count": [remaining_count]
            })
            value_counts_display = pd.concat([top_values, other_row], ignore_index=True)
        else:
            value_counts_display = value_counts
            remaining_unique = 0
            remaining_pct = 0

        fig, ax = plt.subplots(figsize=(8, 6))

        sns.set_color_codes("pastel")
        sns.barplot(
            x="count", y="value", data=value_counts_display, label=title, color="b", ax=ax
        )

        # Add annotations to the bars
        for i, row in value_counts_display.iterrows():
            ax.text(
                x=row["count"] + 0.2,
                y=i,
                s=f"{row['count']:,}",
                va="center",
                ha="left",
                fontsize=10,
                color="black",
            )

        # Add summary text if there are remaining values
        if remaining_unique > 0:
            summary_text = f"Showing top {top_n} most common values. " \
                          f"'{value_counts_display.iloc[-1]['value']}' represents {remaining_pct:.1f}% of all data."
            fig.text(0.5, 0.02, summary_text, ha='center', fontsize=9,
                    style='italic', wrap=True, color='#666666')

        ax.legend(ncol=2, loc="lower right", frameon=True)
        ax.set(xlim=(0, value_counts_display["count"].max() + 5), ylabel=ylabel, xlabel=xlabel)
        sns.despine(left=True, bottom=True)

        return fig
