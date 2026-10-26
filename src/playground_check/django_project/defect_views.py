"""DRF routing for the complete defect API, retaining established response bytes.

During the transition these views use the existing service handlers so the
PostgreSQL, authorization, SMTP and transfer-ID contracts are not duplicated.
"""
from __future__ import annotations

from io import BytesIO

from django.http import HttpResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes

from playground_check import service
from playground_check.http import Request as LegacyRequest


def _dispatch(request, handler, **params):
    # The original request parser deliberately supports case-insensitive JSON
    # properties and the precise legacy error contract. Preserve its input.
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


@api_view(["GET", "POST", "PUT"])
@authentication_classes([])
@permission_classes([])
def defect(request):
    handlers = {"GET": service.get_defect, "POST": service.update_defect, "PUT": service.create_defect}
    return _dispatch(request, handlers[request.method])


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def defect_overview(request):
    return _dispatch(request, service.get_defect_overview)


@api_view(["GET", "PUT"])
@authentication_classes([])
@permission_classes([])
def defect_picture(request, tid: int):
    handler = service.get_defect_picture if request.method == "GET" else service.put_defect_picture
    return _dispatch(request, handler, tid=tid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_send_mail(request, tid: int):
    return _dispatch(request, service.send_info_mail, tid=tid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_accept(request, tid: int):
    return _dispatch(request, lambda legacy: service.assignment_status(legacy, True), tid=tid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_reject(request, tid: int):
    return _dispatch(request, lambda legacy: service.assignment_status(legacy, False), tid=tid)
