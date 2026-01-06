from django.conf import settings
from django.http import HttpResponse, request
from django.template import RequestContext
from django.urls import reverse

from depot.components.page_component import PageComponent
from depot.components.validators import required


class FormPageComponent(PageComponent):
    endpoint = ""
    props = []
    upload_props = []
    validators = {}
    init_data = {}
    data = {}
    errors = {}
    submitted = False

    def reset(self):
        self.submitted = False
        self.data = self.init_data.copy()
        self.errors = {}

    def build_form(self, request):
        self.reset()
        self.endpoint = request.get_full_path()

    def hydrate(self, request):
        self.set_data(request)

        if request.method == "POST":
            self.validate()

    def post_handle(self, request):
        pass

    def get_response(self, request):
        self.bootstrap(request)
        self.mount(request)
        self.hydrate(request)
        self.build_form(request)

        return self.render_to_response()

    def post_response(self, request):
        self.bootstrap(request)
        self.mount(request)

        # First, set the data from the request and validate it
        self.hydrate(request)

        # If there are errors, render the form with the errors
        if self.errors:
            return self.render_to_response()
        else:
            self.submitted = True

        # If there are no errors, run the post actions
        response_data = self.post_handle(request)

        # If the post handler returns a response, return it
        if response_data:
            return response_data

        # Otherwise, render the form
        return self.render_to_response()

    def preserve_state(self, request):
        self.set_data(request)

    def set_data(self, request):
        data = {}
        for key in self.props:
            data[key] = request.POST.get(key, None)

        for key in self.upload_props:
            data[key] = request.FILES.get(key, None)

        self.data = data

    def validate(self):
        """Validate the form data using the validators. Returns only errors."""
        errors = {}

        for attr, validator in self.validators.items():

            params = (
                []
            )  # May be dynamically updated using string notation such as "required|message"

            # If the validatos is a string, parse the validator. If it's an object already, proceed:
            if isinstance(validator, str):
                # Split by colon. first part is validator, second is params
                validator_parts = validator.split(":")
                validator_name = validator_parts[0]

                # if there is a second part of validator parts, its the params
                # the params get split by a pipe
                if len(validator_parts) > 1:
                    params = validator_parts[1].split("|")
                else:
                    params = []

                validator_func = getattr(
                    __import__(
                        f"depot.components.validators.{validator_name}",
                        fromlist=["validate"],
                    ),
                    "validate",
                )
            else:
                # resolve the validate function from the validator module
                validator_func = getattr(validator, "validate")

            validation_response = validator_func(
                attr, self.data.get(attr), self.data, params
            )

            if "valid" not in validation_response:
                raise ValueError(
                    f"Validator must return a dictionary with a valid key. Provided: {validation_response}"
                )

            if not validation_response["valid"]:
                if attr in errors:
                    errors[attr]["error_messages"].extend(
                        validation_response["error_messages"]
                    )
                else:
                    errors[attr] = validation_response

        self.errors = errors

    def get_context_data(self, **kwargs):
        if self.data is None:
            self.data = self.init_data

        if self.errors is None:
            self.errors = {}

        context = {
            "endpoint": self.endpoint,
            "data": self.data,
            "errors": self.errors,
            "user": self.user,
            "url_name": self.url_name,
            "debug": settings.DEBUG,
        }

        extra_attrs = self.get_class_attrs(ignore_list=context.keys())
        context.update(extra_attrs)

        return context

    def get(self, request):
        return self.get_response(request)

    def post(self, request, *args, **kwargs):
        return self.post_response(request)
