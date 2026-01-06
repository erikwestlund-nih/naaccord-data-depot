from django_sonar.utils import sonar
from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Legal Boolean Values"
    default_failure_message = "Value must be one of the allowed boolean values."
    render_empty = True

    def validate(self, idx, variable_name, value, row, params):
        """
        Ensures the value is one of the allowed boolean values.
        """
        # Required should be used to check for missing values
        # If value is empty, validation passes
        if not value:
            return {
                "status": "success",
                "message": None,
            }

        failure_message = self.get_message(params)
        all_legal_values = self.get_all_legal_values(params)

        passes = str(value) in all_legal_values

        if passes:
            return {
                "status": "success",
                "message": None,
            }

        return {
            "status": "fail",
            "message": failure_message,
        }

    def get_all_legal_values(self, params):
        """
        Retrieves all allowed legal values for boolean validation.
        """
        return (
            self.get_legal_values(params.get("True", []))
            + self.get_legal_values(params.get("False", []))
            + self.get_legal_values(params.get("Unknown", []))
        )

    def get_legal_values(self, vals):
        """
        Converts values to string format to ensure proper validation.
        """
        return [str(x) for x in vals]

    def get_message(self, params):
        """
        Constructs a message listing all allowed boolean values.
        """
        yes_values = [str(x) for x in params.get("True", [])]
        no_values = [str(x) for x in params.get("False", [])]
        unknown_values = [str(x) for x in params.get("Unknown", [])]

        message_parts = []

        if yes_values:
            message_parts.append(f"True: {self.get_list_string(yes_values)}")
        if no_values:
            message_parts.append(f"False: {self.get_list_string(no_values)}")
        if unknown_values:
            message_parts.append(f"Unknown: {self.get_list_string(unknown_values)}")

        message = (
            f"Values fall outside the allowed set: {{ {', '.join(message_parts)} }}."
        )
        return message

    def get_list_string(self, values):
        """
        Formats a list of values into a string representation.
        """
        return "[" + ", ".join(f"`{x}`" for x in values) + "]"
