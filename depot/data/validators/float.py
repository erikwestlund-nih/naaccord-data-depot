from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Is Float"
    default_failure_message = "Value is not a valid float."

    def validate(self, idx, variable_name, value, row, params):
        """
        Validates whether a given value can be converted to a float.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """
        if value in [None, ""]:  # Ignore empty values
            return {
                "status": "success",
                "message": None,
            }

        try:
            float(value)
            return {
                "status": "success",
                "message": None,
            }
        except (ValueError, TypeError):
            return {
                "status": "fail",
                "message": self.default_failure_message,
            }
