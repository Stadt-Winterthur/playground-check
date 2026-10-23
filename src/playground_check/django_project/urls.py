"""Migrated read-only API routes; all other routes remain on legacy WSGI."""

from django.urls import path

from .views import django_health, health, public_playgrounds

urlpatterns = [
    path("__django/health", django_health, name="django-health"),
    path("api/health", health, name="api-health"),
    path("Collections/Playgrounds/Items/", public_playgrounds, name="public-playgrounds"),
]
