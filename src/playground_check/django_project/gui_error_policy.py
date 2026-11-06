"""Presentation policy for browser HTML form errors behind an intercepting proxy.

Only native GUI responses are adjusted. API, JSON, binary responses, permission
failures and redirects retain their HTTP semantics. The original form status is
kept in a diagnostic header and in application logs.
"""
import logging

LOGGER = logging.getLogger(__name__)

# Route names identify UI views, not URL prefixes (which overlap with the API).
GUI_ROUTE_PREFIXES = ("python-ui-",)
# Validation, conflict and transient form errors. Never rewrite access denials.
FORM_STATUSES = frozenset({400, 409, 413, 422})


class BrowserFormErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        route_name = (getattr(match, "url_name", None) or "")
        content_type = response.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if (request.method == "POST"
                and route_name.startswith(GUI_ROUTE_PREFIXES)
                and response.status_code in FORM_STATUSES
                and content_type == "text/html"
                and not response.streaming):
            original = response.status_code
            response.status_code = 200
            response["X-UI-Original-Status"] = str(original)
            response["X-UI-Outcome"] = "error"
            response["Cache-Control"] = "private, no-store"
            LOGGER.warning("Browser form response adapted: route=%s original_status=%s", route_name, original)
        # Preserve the actual HTTP status for technical failures, including GET
        # errors. The outcome header is supplementary diagnostic information,
        # never a replacement for HTTP status monitoring.
        elif (route_name.startswith(GUI_ROUTE_PREFIXES)
              and 500 <= response.status_code <= 599
              and content_type == "text/html"
              and not response.streaming):
            response["X-UI-Outcome"] = "error"
            response["Cache-Control"] = "private, no-store"
        return response
