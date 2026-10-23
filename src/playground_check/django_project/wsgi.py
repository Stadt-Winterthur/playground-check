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
    django_path = f"{base}/__django/health"
    if path in {django_path, django_path + "/"}:
        # Django receives a path without the external application's PathBase.
        if base:
            environ = dict(environ)
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base
            environ["PATH_INFO"] = path[len(base):]
        if environ["PATH_INFO"].endswith("/"):
            environ = dict(environ)
            environ["PATH_INFO"] = environ["PATH_INFO"].rstrip("/")
        return _django_application(environ, start_response)
    return legacy_application(environ, start_response)
