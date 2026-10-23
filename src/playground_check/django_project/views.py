"""First native DRF endpoints; legacy endpoint contracts take precedence."""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

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
