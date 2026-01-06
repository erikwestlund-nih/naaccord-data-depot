import io
import base64

# Make matplotlib optional - only needed for chart summarizers
# Templates now use Plotly for rendering, so matplotlib is less critical
try:
    import matplotlib
    matplotlib.use("Agg")  # Use non-GUI backend
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

try:
    from django_sonar.utils import sonar
except ImportError:
    def sonar(*args, **kwargs):
        pass


class BaseSummarizer:
    display_name = None
    variable = None
    data = None
    type = None
    params = None
    message = None

    def __init__(self):
        pass

    def verify_input(self, variable, data):
        if variable not in data.columns:
            raise ValueError(f"Variable '{variable}' is not present in data.")

    def handle(self, variable, type, data, params=None):
        self.variable = variable
        self.data = data
        self.type = type
        self.params = params

        self.verify_input(variable, data)

        return self.summarize(self.variable, self.type, self.data, self.params)

    def summarize(self, variable, data, params):
        """
        Implement specific summarize logic in each summarizer subclass.

        variable:  The name of the variable being summarized
        data:  The dataframe containing the data to summarize
        params: Additional parameters to pass to the summarizer. For example, a plot may have limits for the axes that
        a specific summarizer understands.
        """
        raise NotImplementedError("Subclasses must implement the summarize method.")

    def render_plot(self, plot):
        if not MATPLOTLIB_AVAILABLE:
            return None

        buffer = io.BytesIO()

        # Ensure `fig` is correctly extracted
        fig = plot.get_figure() if hasattr(plot, "get_figure") else plot

        # Save the figure to the buffer
        fig.savefig(buffer, format="png", bbox_inches="tight")
        buffer.seek(0)

        # Encode as Base64
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        buffer.close()

        # Close the figure to free memory
        plt.close(fig)

        return image_base64
