"""Django-owned SPA, static files, Swagger and unknown-path responses.

The API's legacy method/response fallback remains a separate compatibility concern.
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
from pathlib import Path

from django.http import HttpResponse

from playground_check import __version__
from playground_check.config import settings
from playground_check.openapi import build_openapi_document, swagger_ui_html

_PACKAGE = Path(__file__).resolve().parent.parent
_STATIC = _PACKAGE / "static"
_INDEX = _PACKAGE / "templates" / "index.html"
_API_PREFIXES = frozenset({
    "account", "inspection", "collections", "playground", "playdevice",
    "defect", "document", "pushsubscription", "swagger", "api",
})


def frontend(request, path: str = ""):
    """Serve original browser contracts without dispatching through server.Application."""
    route = "/" + path.lstrip("/")
    if route in ("/swagger", "/swagger/"):
        response = HttpResponse(status=302)
        response["Location"] = (settings.base_path or "") + "/swagger/index.html"
        return response
    if route == "/swagger/index.html":
        return HttpResponse(swagger_ui_html(settings.base_path), content_type="text/html; charset=utf-8")
    if route == "/swagger/v1/swagger.json":
        return HttpResponse(json.dumps(build_openapi_document(), ensure_ascii=False, separators=(",", ":")),
                            content_type="application/json; charset=utf-8")
    if route.startswith("/static/"):
        target = (_STATIC / route[len("/static/"):]).resolve()
        if _STATIC.resolve() not in target.parents or not target.is_file():
            return HttpResponse("Not found", status=404, content_type="text/plain; charset=utf-8")
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        response = HttpResponse(target.read_bytes(), content_type=content_type)
        if route == "/static/sw.js":
            response["Service-Worker-Allowed"] = (settings.base_path or "") + "/"
        return response
    defect_link = re.fullmatch(r"/defect/\d+/\d+/?", route, re.IGNORECASE)
    if route.lstrip("/").split("/", 1)[0].casefold() in _API_PREFIXES and not defect_link:
        return HttpResponse("Not found", status=404, content_type="text/plain; charset=utf-8")
    if request.method != "GET":
        return HttpResponse("Not found", status=404, content_type="text/plain; charset=utf-8")
    app_config = json.dumps({
        "tokenKey": settings.playground_user_token_key,
        "playgroundKey": settings.playground_token_key,
        "hideInfoCookieName": settings.hide_info_cookie_name,
        "basePath": settings.base_path,
        "wmsUrl": settings.wms_url,
        "features": {"pushNotifications": settings.push_notifications},
        "vapidPublicKey": settings.vapid_public_key,
    }, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    nonce = secrets.token_urlsafe(18)
    html = (_INDEX.read_text(encoding="utf-8")
            .replace("{{APP_TITLE}}", settings.title)
            .replace("{{APP_SHORT_TITLE}}", settings.short_title)
            .replace("{{APP_BASE_PATH}}", settings.base_path)
            .replace("{{APP_VERSION}}", __version__)
            .replace("{{APP_CONFIG}}", app_config)
            .replace("{{SERVICE_WORKER_ENABLED}}", "true" if settings.service_worker_enabled else "false")
            .replace("{{CSP_NONCE}}", nonce))
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https: http:; "
        "connect-src 'self' https: http:; worker-src 'self' blob:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    return response
