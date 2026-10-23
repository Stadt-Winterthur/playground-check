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
        "/Inspection/renovationtypes/",
        "/Collections/Playgrounds/Items/",
    )
    relative_path = path[len(base):] if base and path.startswith(base + "/") else path
    route = relative_path.rstrip("/")
    if environ.get("REQUEST_METHOD", "GET").upper() == "GET" and any(
        route.casefold() == candidate.rstrip("/").casefold() for candidate in migrated
    ):
        # Django receives a path without the external application's PathBase.
        environ = dict(environ)
        if base:
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
        # Normalize case and slash variants to Django's declared canonical URL.
        target = next(item for item in migrated if route.casefold() == item.rstrip("/").casefold())
        environ["PATH_INFO"] = target
        return _django_application(environ, start_response)
    return legacy_application(environ, start_response)
