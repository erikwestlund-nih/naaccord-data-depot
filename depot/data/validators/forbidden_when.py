from django_sonar.utils import sonar
from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Value Forbidden"
    default_failure_message = "Value is not allowed."
    render_empty = True

    def validate(self, idx, variable_name, value, row, params):
        """
        Ensures a value is forbidden under certain conditions.

        `params` can include:
        - `absent`: The value is forbidden when another variable is absent or falsy.
        - `present`: The value is forbidden when another variable is present or truthy.

        Only one of `absent` or `present` should be provided.
        """
        absent = params.get("absent")
        present = params.get("present")

        # Ensure only one of `absent` or `present` is provided
        if (not absent and not present) or (absent and present):
            return {
                "status": "fail",
                "message": "Validation configuration error: Exactly one of `absent` or `present` must be provided.",
            }

        if absent:
            return self.validate_forbidden_absent(value, row, absent)

        if present:
            return self.validate_forbidden_present(value, row, present)

        return {
            "status": "success",
            "message": None,
        }

    def validate_forbidden_absent(self, value, row, absent):
        """
        Ensures `value` is forbidden when `absent` is missing or falsy.
        """
        if absent not in row:
            return {
                "status": "fail",
                "message": f"Expected variable `{absent}` to be present in the dataframe.",
            }

        if row[absent]:  # `absent` is present and truthy
            return {
                "status": "success",
                "message": None,
            }

        # If `absent` is missing or falsy, `value` must not exist
        if value:
            return {
                "status": "fail",
                "message": f"Value is not allowed when `{absent}` is absent.",
            }

        return {
            "status": "success",
            "message": None,
        }

    def validate_forbidden_present(self, value, row, present):
        """
        Ensures `value` is forbidden when `present` is truthy.
        """
        if present not in row:
            return {
                "status": "fail",
                "message": f"Expected variable `{present}` to be present in the dataframe.",
            }

        if not row[present]:  # `present` is falsy
            return {
                "status": "success",
                "message": None,
            }

        # If `present` is truthy, `value` must not exist
        if value:
            return {
                "status": "fail",
                "message": f"Value is not allowed when `{present}` is present.",
            }

        return {
            "status": "success",
            "message": None,
        }
