from django.conf import settings
from django.http import HttpResponse
from django.template import RequestContext
from django.urls import reverse, resolve
from django_components import Component
from django.middleware.csrf import get_token
from depot.components.base_component import BaseComponent


class PageComponent(BaseComponent):
    user = None
    url_name = None
    debug = False
    csrftoken = None
    title = "NA Accord"

    def bootstrap(self, request):
        self.user = request.user
        self.url_name = resolve(request.path_info).url_name
        self.debug = settings.DEBUG
        self.csrftoken = get_token(request)

    def mount(self, request):
        pass

    def hydrate(self, request):
        pass

    def get_response(self, request):
        self.bootstrap(request)
        self.mount(request)
        self.hydrate(request)
        return self.render_to_response()

    def get_context_data(self, **kwargs):
        context = {
            "user": self.user,
            "url_name": self.url_name,
            "debug": self.debug,
            "title": self.title,
        }

        extra_attrs = self.get_class_attrs(ignore_list=context.keys())
        context.update(extra_attrs)

        return context

    def get_class_attrs(self, ignore_list=None):
        # Default to an empty list if no ignore_list is provided
        if ignore_list is None:
            ignore_list = []

        # Get instance attributes
        instance_attrs = self.__dict__

        # Get class-level attributes and exclude those in the ignore_list
        class_attrs = {
            k: v
            for k, v in self.__class__.__dict__.items()
            if not k.startswith("__") and not callable(v) and k not in ignore_list
        }

        return {**class_attrs, **instance_attrs}

    def get(self, request):
        return self.get_response(request)
