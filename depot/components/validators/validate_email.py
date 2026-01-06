from depot.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


def validate(field, value, form_data, params, message=None):
    errors = []
    message = message or "This email is not valid."

    try:
        EmailValidator()(value)
    except ValidationError as e:
        errors.append(message)

    return {"valid": not errors, "error_messages": errors}
