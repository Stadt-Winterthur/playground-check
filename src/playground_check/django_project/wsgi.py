"""Opt-in WSGI entry point for the incremental Django migration.

All legacy routes are delegated unchanged to the original WSGI application.
The new Django health endpoint is intentionally separate from /api/health.
"""

import os
import re

from django.core.wsgi import get_wsgi_application

from playground_check.config import settings as legacy_settings
from playground_check.server import application as legacy_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playground_check.django_project.settings")
_django_application = get_wsgi_application()


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    # PATH_INFO can include the configured PathBase in the existing deployment.
    base = legacy_settings.base_path
    # Only these GET routes have moved; POST/PUT/DELETE still use legacy WSGI.
    migrated = (
        "/__django/health",
        "/api/health",
        "/Inspection/types/",
        "/Playground/byname/",
        "/Playground/onlynames/",
        "/Inspection/renovationtypes/",
        "/Collections/Playgrounds/Items/",
    )
    relative_path = path[len(base):] if base and path.startswith(base + "/") else path
    route = relative_path.rstrip("/")
    public_detail_prefix = "/Collections/Playgrounds/Items/"
    device_prefix = "/Playground/byplaydevice/"
    is_device_lookup = route.casefold().startswith(device_prefix.casefold()) and route[len(device_prefix):].isdigit()
    is_public_detail = route.casefold().startswith(public_detail_prefix.casefold()) and (
        len(route) > len(public_detail_prefix) and "/" not in route[len(public_detail_prefix):]
    )
    # Defect endpoints now use Django/DRF for every supported HTTP method.
    # Non-matching paths and methods remain on the legacy router unchanged.
    defect_routes = {
        "/Defect/": {"GET", "POST", "PUT"},
        "/Defect/Overview/": {"GET"},
    }
    defect_dynamic = re.fullmatch(
        r"/Defect/(?:Picture/\d+|\d+/(?:send-mail|accept|reject))/?",
        relative_path, re.IGNORECASE,
    )
    defect_allowed = {"GET", "PUT"} if re.fullmatch(r"/Defect/Picture/\d+/?", relative_path, re.IGNORECASE) else {"POST"}
    defect_target = None
    if relative_path.casefold().rstrip("/") in {"/defect", "/defect/overview"}:
        defect_target = "/Defect/" if relative_path.casefold().rstrip("/") == "/defect" else "/Defect/Overview/"
        defect_allowed = defect_routes[defect_target]
    elif defect_dynamic:
        segments = relative_path.strip("/").split("/")
        if segments[1].casefold() == "picture":
            defect_target = f"/Defect/Picture/{segments[2]}/"
        else:
            defect_target = f"/Defect/{segments[1]}/{segments[2].lower()}/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    is_defect = bool(defect_target and method in defect_allowed)
    if is_defect or (method == "GET" and (is_public_detail or is_device_lookup or any(
        route.casefold() == candidate.rstrip("/").casefold() for candidate in migrated
    ))):
        # Django receives a path without the external application's PathBase.
        environ = dict(environ)
        if base:
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
        # Normalize case and slash variants to Django's declared canonical URL.
        if is_defect:
            target = defect_target
        elif is_public_detail:
            target = public_detail_prefix + route[len(public_detail_prefix):] + "/"
        elif is_device_lookup:
            target = device_prefix + route[len(device_prefix):] + "/"
        else:
            target = next(item for item in migrated if route.casefold() == item.rstrip("/").casefold())
        environ["PATH_INFO"] = target
        return _django_application(environ, start_response)
    return legacy_application(environ, start_response)
