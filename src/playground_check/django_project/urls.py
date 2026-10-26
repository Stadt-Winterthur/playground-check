"""Migrated read-only API routes; all other routes remain on legacy WSGI."""

from django.urls import path

from . import defect_views

from .views import django_health, health, public_playgrounds, inspection_types, renovation_types, public_playground_detail, playground_by_name, playground_only_names, playground_by_device

urlpatterns = [
    path("Defect/", defect_views.defect, name="defect"),
    path("Defect/Overview/", defect_views.defect_overview, name="defect-overview"),
    path("Defect/Picture/<int:tid>/", defect_views.defect_picture, name="defect-picture"),
    path("Defect/<int:tid>/send-mail/", defect_views.defect_send_mail, name="defect-send-mail"),
    path("Defect/<int:tid>/accept/", defect_views.defect_accept, name="defect-accept"),
    path("Defect/<int:tid>/reject/", defect_views.defect_reject, name="defect-reject"),
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
