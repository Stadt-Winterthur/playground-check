"""Minimal Django configuration for the incremental migration.

No Django-managed database or authentication tables are introduced here.
The existing application continues to own all legacy endpoints.
"""

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
