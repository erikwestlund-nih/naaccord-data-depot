from depot.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


def validate(field, value, form_data, params, message=None):
    errors = []

    # split params with = to get the field to check
    split_params = params[0].split("=")
    check_field = split_params[0]
    check_value = split_params[1]

    field_display = field.replace("_", " ").capitalize()

    if len(params) > 1:
        message = params[1]
    else:
        message = (
            message
            or field_display + " is required when " + check_field + " is " + check_value
        )

    if form_data.get(check_field) == check_value and not value:
        errors.append(message)

    return {"valid": not errors, "error_messages": errors}
