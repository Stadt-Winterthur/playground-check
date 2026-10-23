"""Migrated read-only API routes; all other routes remain on legacy WSGI."""

from django.urls import path

from .views import django_health, health, public_playgrounds, inspection_types, renovation_types, public_playground_detail, playground_by_name, playground_only_names, playground_by_device

urlpatterns = [
    path("__django/health", django_health, name="django-health"),
    path("api/health", health, name="api-health"),
    path("Inspection/types/", inspection_types, name="inspection-types"),
    path("Inspection/renovationtypes/", renovation_types, name="renovation-types"),
    path("Collections/Playgrounds/Items/", public_playgrounds, name="public-playgrounds"),
    path("Collections/Playgrounds/Items/<str:uuid>/", public_playground_detail, name="public-playground-detail"),
    path("Playground/byname/", playground_by_name, name="playground-by-name"),
    path("Playground/onlynames/", playground_only_names, name="playground-only-names"),
    path("Playground/byplaydevice/<int:fid>/", playground_by_device, name="playground-by-device"),
]
