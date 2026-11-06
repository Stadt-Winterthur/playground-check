"""Django/DRF configuration for the native application.

Existing PostgreSQL repositories own the schema and persistent identities;
Django-managed authentication/database tables are not introduced here."""

import os

from playground_check.config import settings as legacy_settings
from playground_check.upload_limits import UPLOAD_REQUEST_MAX_BYTES, FILE_MEMORY_MAX_BYTES

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
MIDDLEWARE = [
    # Outermost response policy also covers DRF, files and error responses.
    "playground_check.django_project.cache_policy.PrivateResponseCacheMiddleware",
    "playground_check.django_project.gui_error_policy.BrowserFormErrorMiddleware",
    "playground_check.django_project.cross_site_guard.CrossSiteWriteGuard",
    "playground_check.django_project.uploads.UploadLimitMiddleware",
    "playground_check.django_project.localization.LanguageMiddleware",
]
DATABASES = {}
USE_TZ = True
DEFAULT_CHARSET = "utf-8"
LANGUAGE_CODE = "de"
USE_I18N = True
LANGUAGES = [("de", "Deutsch"), ("fr", "Français"), ("it", "Italiano"), ("rm", "Rumantsch"), ("en", "English")]

# Server-side templates for the native application.
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": False,
    "OPTIONS": {"loaders": ["django.template.loaders.filesystem.Loader"],
                "builtins": ["playground_check.django_project.templatetags.ui_language"]},
}]


# Token-based CSRF protection is intentionally not used in this deployment.
# Browser cross-site writes are filtered by CrossSiteWriteGuard below.
def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError(f"{name} must be a boolean")
    return value in {"true", "1", "yes", "on"}


# Enable only where the last trusted reverse proxy overwrites X-Forwarded-Proto.
# Never enable when clients can supply this header directly to Django.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if _env_bool("PLAYGROUND_TRUST_PROXY_HTTPS", False)
    else None
)

# A complete 2000-criterion inspection has up to 8006 form fields.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 9000
# JSON compatibility allows Base64 overhead; multipart files spool to /tmp.
DATA_UPLOAD_MAX_MEMORY_SIZE = UPLOAD_REQUEST_MAX_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = FILE_MEMORY_MAX_BYTES
DATA_UPLOAD_MAX_NUMBER_FILES = 2

TIME_ZONE = "Europe/Zurich"
