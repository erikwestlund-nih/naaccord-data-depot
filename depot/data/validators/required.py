from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Value Required"
    default_failure_message = "Value is required."
    render_empty = True

    def validate(self, idx, variable_name, value, row, params):
        """
        Ensures that a value is required based on certain conditions.

        Args:
            idx (int): The index of the row being validated.
            variable_name (str): The name of the variable being validated.
            value (any): The value to validate.
            row (dict): The full row of data being validated.
            params (dict): Parameters for validation, including:
                - `optional_when`: The value is only required if this variable is missing or falsy.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """

        # If params is explicitly `False`, always pass validation
        if params is False:
            return {
                "status": "success",
                "message": None,
            }

        # Default message
        message = self.default_failure_message

        # If params is `True`, value is strictly required
        if params is True or "optional_when" not in params:
            return {
                "status": "success" if bool(value) else "fail",
                "message": None if value else message,
            }

        # Handle `optional_when`
        optional_when = params.get("optional_when")

        if optional_when not in row:
            return {
                "status": "fail",
                "message": f"Optional when variable `{optional_when}` is not present in the dataframe.",
            }

        # Value is required only when `optional_when` is falsy (None, "", False, etc.)
        passes = bool(row[optional_when]) or bool(value)

        return {
            "status": "success" if passes else "fail",
            "message": (
                None
                if passes
                else f"Value is required when `{optional_when}` is absent."
            ),
        }
