"""Django entry point with explicit backwards-compatible legacy fallback."""
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

from playground_check.config import settings as legacy_settings
from playground_check.server import application as legacy_application
from .route_registry import migrated_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playground_check.django_project.settings")
_django_application = get_wsgi_application()


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    base = legacy_settings.base_path
    # Strip PathBase only at a path segment boundary, not for similar prefixes.
    relative_path = path[len(base):] if base and path.startswith(base + "/") else path
    target = migrated_path(relative_path, environ.get("REQUEST_METHOD", "GET").upper())
    if target is None:
        return legacy_application(environ, start_response)
    migrated_environ = dict(environ)
    if base and path.startswith(base + "/"):
        migrated_environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
    migrated_environ["PATH_INFO"] = target
    return _django_application(migrated_environ, start_response)
