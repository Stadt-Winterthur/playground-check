"""Compatibility adapter: preserve original request parsing and response bytes.

Service authorization and PostgreSQL transaction boundaries remain in place.
No attempt is made to re-serialize JSON or decode document/image responses.
"""
from __future__ import annotations

from io import BytesIO

from django.http import HttpResponse
from playground_check.http import Request as LegacyRequest


def dispatch(request, handler, **params):
    django_request = getattr(request, "_request", request)
    environ = dict(django_request.META)
    payload = django_request.body
    environ["wsgi.input"] = BytesIO(payload)
    environ["CONTENT_LENGTH"] = str(len(payload))
    legacy_request = LegacyRequest(environ, {key: str(value) for key, value in params.items()})
    result = handler(legacy_request)
    response = HttpResponse(result.body, status=result.status, content_type=result.content_type)
    for name, value in result.headers:
        response[name] = value
    return response
