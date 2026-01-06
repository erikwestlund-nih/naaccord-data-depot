from .base_validator import BaseValidator
import pandas as pd


class Validator(BaseValidator):
    display_name = "Is Date"
    default_failure_message = "Value is not a valid date."

    def validate(self, idx, variable_name, value, row, params):
        """
        Validates if a value is a date using either 'pd_format' or 'date_format'.
        Prioritizes 'pd_format' if both are provided.

        Args:
            idx (int): The index of the row being validated.
            variable_name (str): The name of the variable being validated.
            value (str): The value to validate.
            row (dict): The full row of data being validated.
            params (dict): Parameters for validation. Can include:
                - 'pd_format': Full pandas-compatible format string.
                - 'date_format': Custom string format, defaults to 'YYYY-MM-DD'.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """
        if value in [None, ""]:  # Ignore empty values
            return {
                "status": "success",
                "message": None,
            }

        pd_format = params.get("pd_format")
        date_format = params.get("date_format", "%Y-%m-%d")  # Default format

        if (
            date_format == "YYYY-MM-DD"
        ):  # Convert string representation to pandas format
            date_format = "%Y-%m-%d"

        if not isinstance(value, str):  # Ensure it's a string before processing
            return {
                "status": "fail",
                "message": f"Value '{value}' is not a valid string and cannot be parsed as a date.",
            }

        try:
            if pd_format:
                parsed_date = pd.to_datetime(value, format=pd_format, exact=True)
            else:
                parsed_date = pd.to_datetime(value, format=date_format, exact=True)

            # Ensure the parsed date matches the original string
            if parsed_date.strftime(date_format) == value:
                return {
                    "status": "success",
                    "message": None,
                }
        except (ValueError, TypeError):
            format_used = params.get("date_format", params.get("pd_format", None))
            failure_message = (
                f"Value '{value}' is not a valid date in format '{format_used}'."
                if format_used
                else f"Value '{value}' is not a valid date."
            )

            return {
                "status": "fail",
                "message": failure_message,
            }

        # If no exception but parsing failed
        return {
            "status": "fail",
            "message": self.default_failure_message,
        }
