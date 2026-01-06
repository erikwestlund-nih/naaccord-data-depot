from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Is String"
    default_failure_message = "Value is not a valid string."

    def validate(self, idx, variable_name, value, row, params):
        """
        Validates whether a given value is a string.

        Returns:
            dict: { "status": "success" | "fail", "message": str | None }
        """
        if isinstance(value, str):
            return {
                "status": "success",
                "message": None,
            }

        return {
            "status": "fail",
            "message": self.default_failure_message,
        }
