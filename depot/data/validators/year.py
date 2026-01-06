from datetime import datetime
from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Is Year"
    default_failure_message = "Value is not a valid year."

    def validate(self, idx, variable_name, value, row, params):
        """
        Validates whether a given value represents a valid year.

        Rules:
        - The user can set `min_year` and `max_year` in `params`.
        - If not provided, `min_year` defaults to 1000.
        - If not provided, `max_year` defaults to (current year + 10).

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """
        if value in [None, ""]:  # Ignore empty values
            return {
                "status": "success",
                "message": None,
            }

        try:
            year = int(value)
        except (ValueError, TypeError):
            return {
                "status": "fail",
                "message": f"Value '{value}' is not a valid numeric year.",
            }

        # Get dynamic limits from params (or use defaults)
        min_year = params.get("min_year", 1000)  # Default: 1000
        max_year = params.get(
            "max_year", datetime.now().year + 10
        )  # Default: 10 years into the future

        if min_year <= year <= max_year:
            return {
                "status": "success",
                "message": None,
            }

        return {
            "status": "fail",
            "message": f"Year must be between {min_year} and {max_year}.",
        }
