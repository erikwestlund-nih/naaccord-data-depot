import importlib

try:
    from django_sonar.utils import sonar
except ImportError:  # pragma: no cover - optional debugging dependency
    def sonar(*_args, **_kwargs):
        return None


class Summarizer:

    def handle(self, data_table_definition, df):
        summaries = {}

        for definition in data_table_definition.definition:
            var = definition["name"]

            summarizers = self.construct_variable_summarizers(definition)

            summaries[var] = {
                "status": "success",
                "type": definition["type"],
                "description": (
                    definition["description"] if "description" in definition else None
                ),
                "results": [],
            }  # Initialize

            if var not in df.columns:
                continue

            for summarizer_item in summarizers:
                summarizer_data = self.resolve(summarizer_item)
                summarizer_name = summarizer_data.get("name", "(unknown)")

                if summarizer_data["status"] == "error":
                    summaries[var]["results"].append(
                        {
                            "name": summarizer_name,
                            "status": "error",
                            "message": summarizer_data["message"],
                        }
                    )
                    continue

                summarizer = summarizer_data["summarizer"]
                params = summarizer_data["params"]

                summaries[var]["results"].append(
                    {
                        "name": summarizer_name,
                        "display_name": (
                            summarizer.display_name
                            if hasattr(summarizer, "display_name")
                            else summarizer_name
                        ),
                        "report": summarizer.handle(
                            var, definition["type"], df, params
                        ),
                    }
                )

        # sonar(summaries)

        return summaries

    def construct_variable_summarizers(self, definition):
        # Universal summarizers
        summarizers = ["count", "unique", "empty", "present", "empty_pct", "examples"]

        # Summarizers applied to all variables depending on type
        id_summarizers = []

        numeric_summarizers = [
            "mean",
            "median",
            "sd",
            "min",
            "max",
            "range",
            "outliers",
            "histogram",
            "box_plot",
        ]

        categorical_summarizers = [
            "mode",
            "bar_chart",
        ]

        boolean_summarizers = [
            "bar_chart",
        ]

        year_summarizers = [
            "mean" "median",
            "min",
            "max",
            "date_range",
            "date_histogram",
        ]

        date_summarizers = [
            "min",
            "max",
            "date_range",
            "date_histogram",
        ]

        type_summarizers = {
            "id": id_summarizers,
            "number": numeric_summarizers,
            "int": numeric_summarizers,
            "float": numeric_summarizers,
            "year": year_summarizers,
            "enum": categorical_summarizers,
            "boolean": boolean_summarizers,
            "date": date_summarizers,
        }

        summarizers = summarizers + type_summarizers.get(definition["type"], [])

        # Custom summarizers from the patient definition
        if "summarizers" in definition:
            summarizers += [
                self.process_summarizer(v) for v in definition["summarizers"]
            ]

        # In the case of duplicates, remove them
        summarizers = list(dict.fromkeys(summarizers))

        return summarizers

    def process_summarizer(self, summarizer):

        if isinstance(summarizer, str):
            summarizer = summarizer  # possible later to account for params here to do things let set axes

        return summarizer

    def resolve(self, summarizer):

        if isinstance(summarizer, str):
            summarizer = {
                "name": summarizer,
                "params": None,
            }

        if "name" not in summarizer:
            return {
                "status": "error",
                "message": "Summarizer name not found.",
            }

        # Dictionary format requires params, even if set to  None.
        if "params" not in summarizer:
            params = None

        try:
            module = importlib.import_module(
                f"depot.data.summarizers.{summarizer['name']}"
            )
            params = summarizer["params"]
        except ImportError:
            return {
                "status": "error",
                "name": summarizer["name"],
                "message": f"Summarizer `{summarizer['name']}` not found.",
            }

        return {
            "status": "success",
            "name": summarizer["name"],
            "summarizer": getattr(module, "Summarizer")(),
            "params": params,
        }
