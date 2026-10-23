"""Minimal Django configuration for the incremental migration.

No Django-managed database or authentication tables are introduced here.
The existing application continues to own all legacy endpoints.
"""

from playground_check.config import settings as legacy_settings

SECRET_KEY = legacy_settings.security_key
DEBUG = False
ALLOWED_HOSTS = ["*"]  # Transitional only: host filtering remains at the reverse proxy.
ROOT_URLCONF = "playground_check.django_project.urls"
INSTALLED_APPS = []
MIDDLEWARE = []
DATABASES = {}
USE_TZ = True
DEFAULT_CHARSET = "utf-8"
