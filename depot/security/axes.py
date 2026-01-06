"""Helpers for integrating Django Axes with upstream proxies."""

from __future__ import annotations

from typing import Iterable

from django.http import HttpRequest

_CANDIDATE_HEADERS: Iterable[str] = (
    "HTTP_CF_CONNECTING_IP",
    "HTTP_X_REAL_IP",
    "HTTP_X_FORWARDED_FOR",
    "REMOTE_ADDR",
)


def get_client_ip(request: HttpRequest) -> str:
    """Return the best-guess client IP for Axes.

    Attempts to honour Cloudflare's `CF-Connecting-IP` header first, then
    standard proxy headers before falling back to Django's `REMOTE_ADDR`.
    When multiple addresses are present (e.g. comma-separated X-Forwarded-For),
    the left-most address is used, matching how nginx forwards client IPs.
    """

    for header in _CANDIDATE_HEADERS:
        raw_value = request.META.get(header)
        if not raw_value:
            continue

        # X-Forwarded-For may contain a comma-separated chain; pick the first.
        if header == "HTTP_X_FORWARDED_FOR":
            raw_value = raw_value.split(",")[0].strip()

        candidate = raw_value.strip()
        if candidate:
            return candidate

    return "0.0.0.0"
