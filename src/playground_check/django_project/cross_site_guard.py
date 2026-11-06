"""Token-free browser CSRF mitigation for all unsafe methods.

Modern browsers set Sec-Fetch-Site. Cross-site writes are denied before any
view, regardless of whether it is an HTML form or a JSON API endpoint.
Requests without Fetch Metadata remain supported (e.g. API clients), so the
reverse proxy should also reject untrusted cross-origin writes when possible.
"""
from django.http import HttpResponseForbidden


class CrossSiteWriteGuard:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            if request.META.get("HTTP_SEC_FETCH_SITE", "").lower() == "cross-site":
                return HttpResponseForbidden("Cross-site requests are not permitted.")
        return self.get_response(request)
