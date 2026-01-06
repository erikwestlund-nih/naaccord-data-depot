from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Range"
    default_failure_message = "Value is not within the specified range."

    def validate(self, idx, variable_name, value, row, params):
        """
        Check if the value is within the specified range.

        Args:
            idx (int): The index of the row being validated
            variable_name (str): The name of the variable being validated
            value (any): The value to validate
            row (dict): The entire row of data being validated
            params (tuple): A tuple (min, max) specifying the valid range.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """

        # Ensure `params` is valid
        if not isinstance(params, (tuple, list)) or len(params) != 2:
            raise ValueError(
                "Range validator requires `params` as a tuple of (min, max) values."
            )

        min_val, max_val = params

        if value in [None, ""]:  # Ignore empty values
            return {
                "status": "success",
                "message": None,
            }

        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            return {
                "status": "fail",
                "message": f"Value '{value}' is not a valid number.",
            }

        if min_val <= numeric_value <= max_val:
            return {
                "status": "success",
                "message": None,
            }

        return {
            "status": "fail",
            "message": self.get_message(min_val, max_val),
        }

    def get_message(self, min_val, max_val):
        """
        Constructs a failure message for out-of-range values.
        """
        return f"Value is not within the specified range: {min_val}-{max_val}."
