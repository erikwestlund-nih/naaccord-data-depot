import json
import socket
import urllib
from typing import Any

from django.conf import settings
from django_components import register, Component
from django_components.component import DataType
from depot.components.base_component import BaseComponent


@register("layout.app")
class LayoutComponent(BaseComponent):
    template_name = "app.html"

    def get_vite_js_path(self, asset_name):
        """Reads the Vite manifest.json from the static/.vite/ directory and returns the hashed asset file path."""
        manifest_path = settings.BASE_DIR / "static/.vite/manifest.json"

        try:
            with open(manifest_path) as manifest_file:
                manifest = json.load(manifest_file)
            return manifest[asset_name]["file"]
        except (FileNotFoundError, KeyError):
            return None

    def get_vite_css_paths(self, asset_name):
        """Reads the Vite manifest.json from the static/.vite/ directory and returns ALL hashed CSS file paths."""
        manifest_path = settings.BASE_DIR / "static/.vite/manifest.json"
        try:
            with open(manifest_path) as manifest_file:
                manifest = json.load(manifest_file)

            return manifest[asset_name].get("css", [])
        except (FileNotFoundError, KeyError):
            return []

    def vite_running(self, url="http://localhost:3000/@vite/client"):
        """Check if the Vite dev server is running by making an HTTP request."""
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False

    def get_context_data(self, *args: Any, **kwargs: Any) -> DataType:

        return {
            "debug": settings.DEBUG,
            "app_css_files": self.get_vite_css_paths("resources/js/app.js"),
            "app_js": self.get_vite_js_path("resources/js/app.js"),
            "vite_running": self.vite_running(),
            "title": kwargs.get("title"),
        }
