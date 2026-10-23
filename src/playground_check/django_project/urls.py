"""Only newly migrated URLs belong here."""

from django.http import JsonResponse
from django.urls import path

from playground_check import __version__


def django_health(request):
    return JsonResponse({"status": "ok", "version": __version__, "backend": "django"})


urlpatterns = [
    path("__django/health", django_health, name="django-health"),
]
