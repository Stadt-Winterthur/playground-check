"""Opt-in WSGI entry point for the incremental Django migration.

All legacy routes are delegated unchanged to the original WSGI application.
The new Django health endpoint is intentionally separate from /api/health.
"""

import os

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
    if environ.get("REQUEST_METHOD", "GET").upper() == "GET" and (is_public_detail or is_device_lookup or any(
        route.casefold() == candidate.rstrip("/").casefold() for candidate in migrated
    )):
        # Django receives a path without the external application's PathBase.
        environ = dict(environ)
        if base:
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
        # Normalize case and slash variants to Django's declared canonical URL.
        if is_public_detail:
            target = public_detail_prefix + route[len(public_detail_prefix):] + "/"
        elif is_device_lookup:
            target = device_prefix + route[len(device_prefix):] + "/"
        else:
            target = next(item for item in migrated if route.casefold() == item.rstrip("/").casefold())
        environ["PATH_INFO"] = target
        return _django_application(environ, start_response)
    return legacy_application(environ, start_response)
