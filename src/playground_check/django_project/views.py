"""First native DRF endpoints; legacy endpoint contracts take precedence."""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.http import HttpResponse

from playground_check.http import Request as LegacyRequest
from playground_check.service import require_user

from playground_check import __version__
from playground_check.db import connect
from playground_check.service import _public_feature


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def health(request):
    return Response({"status": "ok", "version": __version__})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def django_health(request):
    return Response({"status": "ok", "version": __version__, "backend": "django"})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def public_playgrounds(request):
    # Preserve the published GeoJSON shape and legacy fallback on DB failure.
    try:
        with connect() as db:
            rows = db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y FROM "wgr_sp_spielplatz"''').fetchall()
        return Response([_public_feature(row) for row in rows])
    except Exception:
        return Response([_public_feature(error="Unknown critical error.")])


def _legacy_access_error(request):
    """Keep the existing token, dryRun, and database user checks intact."""
    _, error = require_user(LegacyRequest(request._request.META))
    if error is None:
        return None
    return HttpResponse(error.body, status=error.status, content_type=error.content_type)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def inspection_types(request):
    error = _legacy_access_error(request)
    if error is not None:
        return error
    with connect() as db:
        rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    return Response([f"{row['value']} ({row['short_value']})" for row in rows])


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def renovation_types(request):
    error = _legacy_access_error(request)
    if error is not None:
        return error
    with connect() as db:
        rows = db.execute('SELECT value FROM "wgr_sp_sanierungsart_tbd"').fetchall()
    return Response([row["value"] for row in rows])
