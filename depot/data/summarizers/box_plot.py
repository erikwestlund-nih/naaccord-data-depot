from .base_summarizer import BaseSummarizer, MATPLOTLIB_AVAILABLE

if MATPLOTLIB_AVAILABLE:
    import matplotlib.pyplot as plt
    import seaborn as sns
    sns.set_theme(style="whitegrid")
else:
    plt = None
    sns = None


class Summarizer(BaseSummarizer):
    display_name = "Box Plot"

    def summarize(self, variable, type, data, params=None):
        if not MATPLOTLIB_AVAILABLE:
            return {
                "status": "skipped",
                "message": "matplotlib not available",
            }

        variable_data = data[variable]

        # Ensure the variable is numeric
        if not variable_data.dtype.kind in "iuf":  # iuf = integer, unsigned, float
            return {
                "status": "error",
                "message": f"Variable '{variable}' is not numeric.",
            }

        box_plot = self.gen_boxplot(variable_data)

        return {
            "status": "success",
            "value": box_plot,
            "value_rendered": {
                "type": "base64_image",
                "data": self.render_plot(box_plot),
            },
        }

    def gen_boxplot(self, variable_data, title=None, xlabel=None, ylabel=None):
        fig, ax = plt.subplots(figsize=(8, 6))

        sns.set_color_codes("pastel")

        sns.boxplot(
            x=variable_data,
            ax=ax,
            color="b",
            width=0.5,
        )

        if title:
            ax.set_title(title, fontsize=16, pad=15)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=12, labelpad=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=12, labelpad=10)

        sns.despine(left=True, bottom=True)

        return fig
