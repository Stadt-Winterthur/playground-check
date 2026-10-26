"""DRF permissions preserving legacy identity and HTTP denial contracts."""

from django.http import HttpResponse
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework.views import exception_handler as drf_exception_handler


class LegacyPermissionDenied(APIException):
    """Carry the original authentication rejection to the HTTP boundary."""

    status_code = 401
    default_detail = "unauthorized"

    def __init__(self, legacy_response):
        self.legacy_response = legacy_response
        super().__init__()


class IsLegacyAuthenticated(BasePermission):
    """Require a successfully revalidated legacy principal for a DRF view."""

    def has_permission(self, request, view):
        django_request = getattr(request, "_request", request)
        result = getattr(django_request, "_legacy_auth_result", None)
        if result is None:
            # The authentication class should always run first on protected views.
            # Fail closed if configuration changes unexpectedly.
            raise LegacyPermissionDenied(HttpResponse(
                "unauthorized", status=401, content_type="text/plain"
            ))
        user, error = result
        if error is not None:
            raise LegacyPermissionDenied(HttpResponse(
                error.body, status=error.status, content_type=error.content_type
            ))
        if user is None:
            raise LegacyPermissionDenied(HttpResponse(
                "unauthorized", status=401, content_type="text/plain"
            ))
        return True


def legacy_exception_handler(exc, context):
    """Avoid DRF converting existing plain-text 401 responses to JSON."""
    if isinstance(exc, LegacyPermissionDenied):
        return exc.legacy_response
    return drf_exception_handler(exc, context)
