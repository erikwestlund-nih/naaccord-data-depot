def get_form_data(form, fields=None):
    fields = fields or form.fields.keys()
    return {
        key: (
            str(form.data.get(key))
            if form.data.get(key) not in [None, ""]
            else str(form.initial.get(key) or "")
        )
        for key in fields
    }


def get_form_options(self, field_name):
    return [
        {"value": choice[0], "label": choice[1]}
        for choice in self.fields[field_name].choices
    ]


def extract_form_errors(form, fields=None):
    """
    Extracts plain text errors from a Django form, optionally for a subset of fields.

    Args:
        form (forms.Form): The Django form instance.
        fields (list[str], optional): If provided, limits returned errors to these fields.

    Returns:
        dict[str, list[str]]: Field -> list of error strings
    """
    error_dict = {
        field: [str(error) for error in errors] for field, errors in form.errors.items()
    }

    if fields is not None:
        error_dict = {
            field: error_dict[field] for field in fields if field in error_dict
        }

    return error_dict
