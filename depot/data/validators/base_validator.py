from django_sonar.utils import sonar


class BaseValidator:
    display_name = None
    variable_name = None
    data = None
    default_failure_message = ""
    render_empty = False

    def __init__(self):
        pass

    def verify_input(self, data, variable_name):
        if variable_name not in data.columns:
            raise ValueError(f"Variable '{variable_name}' is not present in data.")

    def handle(self, variable_name, data, params=None):
        self.variable_name = variable_name
        self.data = data
        failed_values = []
        failure_messages = set()  # Using a set to ensure uniqueness
        warning_messages = set()  # Collects warning messages separately

        if params is None:
            params = {}

        self.verify_input(data, variable_name)

        validation_results = []

        # Run specific validation logic for each row
        for idx, row in data.iterrows():
            if variable_name not in row:
                raise KeyError(f"Variable '{variable_name}' not found in row {idx + 1}")

            value = row[variable_name]
            validation_result = self.validate(idx, variable_name, value, row, params)

            # Convert boolean results to dictionary format
            if isinstance(validation_result, bool):
                validation_result = {
                    "status": "fail" if not validation_result else "success",
                    "message": None,
                }

            validation_results.append(validation_result)

            # Handle Failures
            if validation_result["status"] == "fail":
                failed_values.append({"row": idx + 1, "value": value})
                message = (
                    validation_result["message"]
                    or getattr(self, "default_failure_message", None)
                    or f"Validation failed for row {idx + 1}."
                )
                failure_messages.add(message)

            # Handle Warnings
            elif validation_result["status"] == "warn":
                message = validation_result["message"] or f"Warning for row {idx + 1}."
                warning_messages.add(message)

        # Determine if validation passes (warnings don't cause failure)
        validation_passes = all(
            result["status"] != "fail" for result in validation_results
        )
        errors = [] if validation_passes else self.format_errors(failed_values)

        return {
            "pass": validation_passes,
            "failure_messages": list(failure_messages),
            "warnings": list(warning_messages),
            "errors": errors,
            "render_empty": self.render_empty,
        }

    def validate(self, idx, variable_name, value, row, params):
        """
        Implement specific validate logic in each validator subclass.

        idx:    The index of the row being validated
        variable_name:  The name of the variable being validated
        value:  The value to validate
        row:    The full row data
        params: Additional parameters to pass to the validator. For example, if doing a range check, params could be
                a tuple of (min, max) values. The specific validator should document the expected params and verify
                they are present.
        """
        raise NotImplementedError("Subclasses must implement the validate method.")

    def format_errors(self, failed_values):
        """
        Groups errors by unique values while capturing all associated records.
        """
        error_summary = {}

        for failure in failed_values:
            value = failure["value"]
            context = {"row": failure["row"]}

            if value not in error_summary:
                error_summary[value] = {"value": value, "records": []}

            error_summary[value]["records"].append(context)

        return list(error_summary.values())
