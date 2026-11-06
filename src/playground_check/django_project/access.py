"""Compatibility boundary between DRF requests and the legacy authentication.

The existing token verification and database revalidation remain authoritative
until the authentication subsystem is migrated separately.
"""

from django.http import HttpResponse

from playground_check.http import Request as LegacyRequest


def authenticated_legacy_user(request, require_user):
    """Return (legacy user, Django error response or None).

    `require_user` is injected so existing API contract tests can mock it.
    Preserve the legacy status, body and content-type exactly, including
    plain-text 401 responses; DRF's default errors differ from that contract.
    """
    django_request = getattr(request, "_request", request)
    cached = getattr(django_request, "_legacy_auth_result", None)
    user, error = cached if cached is not None else require_user(LegacyRequest(django_request.META))
    if error is not None:
        return user, HttpResponse(
            error.body, status=error.status, content_type=error.content_type
        )
    return user, None
