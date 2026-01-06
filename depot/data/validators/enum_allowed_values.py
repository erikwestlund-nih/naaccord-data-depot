from .base_validator import BaseValidator


class Validator(BaseValidator):
    display_name = "Legal Enum Values"
    default_failure_message = "Value falls outside the allowed set."

    def validate(self, idx, variable_name, value, row, params):
        """
        Validates if a value is among the allowed enumeration values.
        """
        # If value is empty, validation passes
        if not value:
            return {
                "status": "success",
                "message": None,
            }

        value_dictionary = self.get_allowed_values(params)
        allowed_values = [x["value"] for x in value_dictionary]

        if value in allowed_values:
            return {
                "status": "success",
                "message": None,
            }

        failure_message = self.get_message(value_dictionary)

        return {
            "status": "fail",
            "message": failure_message,
        }

    def get_allowed_values(self, params):
        """
        Processes parameters into a list of allowed values with descriptions.
        """
        return [self.process_value(value) for value in params]

    def process_value(self, value):
        """
        Ensures each allowed value is stored in a consistent format.
        """
        if isinstance(value, dict) and "value" in value and "description" in value:
            return {
                "value": value["value"],
                "description": value["description"],
            }

        return {
            "value": value,
            "description": value,
        }

    def get_message(self, value_dictionary):
        """
        Constructs an error message listing the allowed values.
        """
        param_string = ", ".join(
            [self.get_message_string(value) for value in value_dictionary]
        )
        return f"Value falls outside the allowed set: [{param_string}]."

    def get_message_string(self, value):
        """
        Formats the allowed value and its description for error messaging.
        """
        if value["value"] != value["description"]:
            return f"`{value['value']}` ({value['description']})"
        return f"`{value['value']}`"
