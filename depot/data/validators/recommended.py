from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Recommended"
    default_failure_message = "It is recommended to provide this value."
    render_empty = True

    def validate(self, idx, variable_name, value, row, params):
        """
        This validator does not fail validation but instead logs a warning message
        recommending the presence of a value if one is not provided.
        """
        if not value:
            return {
                "status": "warn",  # Change from "fail" to "warn"
                "message": params.get("message", self.default_failure_message),
            }

        return {
            "status": "success",
            "message": None,
        }
