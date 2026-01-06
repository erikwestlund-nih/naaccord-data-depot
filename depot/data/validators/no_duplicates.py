from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "No Duplicates"
    default_failure_message = "Duplicate values found."

    def validate(self, idx, variable_name, value, row, params):
        """
        Ensures the value is unique within the column.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """
        if value in [None, ""]:  # Ignore empty values
            return {
                "status": "success",
                "message": None,
            }

        # Ensure the variable exists in the dataset
        if variable_name not in self.data.columns:
            return {
                "status": "fail",
                "message": f"Variable `{variable_name}` not found in the dataset.",
            }

        # Drop the current index to avoid comparing the value to itself
        rest_of_data = self.data[variable_name].drop(index=idx, errors="ignore")
        unique_values = rest_of_data.unique()

        if value in unique_values:
            return {
                "status": "fail",
                "message": self.default_failure_message,
            }

        return {
            "status": "success",
            "message": None,
        }
