"""DRF transport boundary preserving deployed request and response contracts.

Domain authorization and PostgreSQL transaction boundaries remain unchanged.
No attempt is made to re-serialize JSON or decode document/image responses.
"""
from __future__ import annotations

from io import BytesIO

from django.http import HttpResponse
from playground_check.http import Request as LegacyRequest


def to_legacy_request(request, **params):
    django_request = getattr(request, "_request", request)
    environ = dict(django_request.META)
    payload = django_request.body
    environ["wsgi.input"] = BytesIO(payload)
    environ["CONTENT_LENGTH"] = str(len(payload))
    return LegacyRequest(environ, {key: str(value) for key, value in params.items()})


def to_http_response(result):
    response = HttpResponse(result.body, status=result.status, content_type=result.content_type)
    for name, value in result.headers:
        response[name] = value
    return response


def dispatch(request, handler, **params):
    return to_http_response(handler(to_legacy_request(request, **params)))
