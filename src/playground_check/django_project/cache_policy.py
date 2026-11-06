"""F05: centrally prevent storage of private responses, including errors.

New dynamic routes default to private. Only explicitly public, successful GET
responses and genuine static resources retain their existing cache policy.
"""
from django.utils.cache import patch_vary_headers


PUBLIC_VIEW_NAMES = frozenset({
    "api-health", "django-health", "public-playgrounds",
    "public-playground-detail", "playground-map-image",
})


class PrivateResponseCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        public_view = match is not None and match.url_name in PUBLIC_VIEW_NAMES
        static_resource = (
            match is not None and match.url_name == "frontend-fallback"
            and match.kwargs.get("path", "").startswith("static/")
        )
        if (request.method in {"GET", "HEAD"}
                and response.status_code in {200, 304}
                and not response.cookies and not response.has_header("Set-Cookie")
                and (public_view or static_resource)):
            return response

        # Replace rather than merge: a view must not retain public/s-maxage or
        # stale-while-revalidate directives on an authenticated response.
        response["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
        response["Expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        patch_vary_headers(response, ("Cookie", "Authorization"))
        return response
