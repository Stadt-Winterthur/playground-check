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
    user, error = require_user(LegacyRequest(request._request.META))
    if error is not None:
        return user, HttpResponse(
            error.body, status=error.status, content_type=error.content_type
        )
    return user, None
