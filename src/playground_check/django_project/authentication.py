"""DRF authentication backed by the existing Oracle-master-aware account model.

Only user identity is resolved here; the legacy authorization contract is
retained while API views are being migrated incrementally.
"""

from rest_framework.authentication import BaseAuthentication

from playground_check.http import Request as LegacyRequest


class LegacyPrincipal(dict):
    """Expose the validated legacy user to DRF without Django auth tables."""

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


class LegacyTokenAuthentication(BaseAuthentication):
    """Validate credentials once using the existing token and database rules.

    A rejected credential is cached for the compatibility error handler so
    existing endpoints still return their original text/plain HTTP 401 body.
    """

    def authenticate(self, request):
        # Resolve this at request time to retain the current view's injected
        # require_user dependency in compatibility tests.
        from . import views

        user, error = views.require_user(LegacyRequest(request._request.META))
        request._request._legacy_auth_result = (user, error)
        if error is not None or user is None:
            return None
        return LegacyPrincipal(user), None
