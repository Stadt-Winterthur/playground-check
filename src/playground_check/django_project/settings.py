"""Minimal Django configuration for the incremental migration.

No Django-managed database or authentication tables are introduced here.
The existing application continues to own all legacy endpoints.
"""

import os
from urllib.parse import urlsplit

from playground_check.config import settings as legacy_settings

SECRET_KEY = legacy_settings.security_key
DEBUG = False
ALLOWED_HOSTS = ["*"]  # Transitional only: host filtering remains at the reverse proxy.
ROOT_URLCONF = "playground_check.django_project.urls"
INSTALLED_APPS = ["rest_framework"]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "playground_check.django_project.permissions.legacy_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
MIDDLEWARE = []
DATABASES = {}
USE_TZ = True
DEFAULT_CHARSET = "utf-8"

# Server-side templates for the opt-in Python-first application.
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": False,
    "OPTIONS": {"loaders": ["django.template.loaders.filesystem.Loader"]},
}]


# Deployment-specific CSRF and TLS settings belong in environment variables.
# Never infer trusted origins from untrusted HTTP Host / Forwarded headers.
def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError(f"{name} must be a boolean")
    return value in {"true", "1", "yes", "on"}


def _trusted_origins() -> list[str]:
    raw = os.getenv("PLAYGROUND_CSRF_TRUSTED_ORIGINS", "")
    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment):
            raise ValueError("PLAYGROUND_CSRF_TRUSTED_ORIGINS must contain complete origins only")
    return origins


CSRF_TRUSTED_ORIGINS = _trusted_origins()
CSRF_COOKIE_SECURE = _env_bool("PLAYGROUND_CSRF_COOKIE_SECURE", False)

# Enable only where the last trusted reverse proxy overwrites X-Forwarded-Proto.
# Never enable when clients can supply this header directly to Django.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if _env_bool("PLAYGROUND_TRUST_PROXY_HTTPS", False)
    else None
)
