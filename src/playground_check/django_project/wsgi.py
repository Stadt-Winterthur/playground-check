"""Django-only WSGI entry point, preserving canonical API URL variants."""
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

from playground_check.config import settings as application_settings

# Retain the historical settings patch point used by compatibility tests.
# This is configuration only; the legacy WSGI application is not imported.
legacy_settings = application_settings
from .route_registry import canonical_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playground_check.django_project.settings")
_django_application = get_wsgi_application()


def application(environ, start_response):
    """Dispatch every request to Django; never invoke the old WSGI server.

    Preserve the configured reverse proxy PathBase and canonicalize known API
    routes without filtering HTTP methods, so Django returns 405 for methods
    unsupported by the view. Unknown API paths are handled by Django's 404.
    """
    path = environ.get("PATH_INFO", "")
    base = legacy_settings.base_path
    prefixed = bool(base and (path == base or path.startswith(base + "/")))
    relative_path = path[len(base):] or "/" if prefixed else path
    migrated_environ = dict(environ)
    if prefixed:
        migrated_environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
    migrated_environ["PATH_INFO"] = canonical_path(relative_path) or relative_path
    return _django_application(migrated_environ, start_response)
