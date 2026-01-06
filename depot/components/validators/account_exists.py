from depot.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


def validate(field, value, form_data, params, message=None):
    errors = []

    message = message or "This account does not exist."

    if not User.objects.filter(email=value).exists():
        errors.append(message)

    return {"valid": not errors, "error_messages": errors}
