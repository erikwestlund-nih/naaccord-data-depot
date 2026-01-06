from depot.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


def validate(field, value, form_data, params, message=None):
    errors = []

    field_display = field.replace("_", " ").capitalize()

    message = message or field_display + " is required."

    if not value:
        errors.append(message)

    return {"valid": not errors, "error_messages": errors}
