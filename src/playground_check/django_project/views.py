"""First native DRF endpoints; legacy endpoint contracts take precedence."""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.http import HttpResponse
from .authentication import LegacyTokenAuthentication
from .permissions import IsLegacyAuthenticated

from playground_check.domain_support import require_user, playground_only_names_data, playground_by_device_data, playground_by_id_data
from playground_check.config import settings as legacy_settings

from playground_check import __version__
from playground_check.db import connect
from playground_check.map_image_queries import map_image_base64
from playground_check.playground_reads import public_feature as _public_feature
from playground_check.domain_support import playground_by_name_data


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


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def inspection_types(request):
    with connect() as db:
        rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    return Response([f"{row['value']} ({row['short_value']})" for row in rows])


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def renovation_types(request):
    with connect() as db:
        rows = db.execute('SELECT value FROM "wgr_sp_sanierungsart_tbd"').fetchall()
    return Response([row["value"] for row in rows])


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def public_playground_detail(request, uuid):
    """Preserve the GeoJSON and error-payload contract of the public UUID lookup."""
    uuid = uuid.strip().lower()
    if not uuid:
        return Response(_public_feature(error="No valid UUID provided."))
    try:
        with connect() as db:
            row = db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y
                FROM "wgr_sp_spielplatz" WHERE uuid::text=%s''', (uuid,)).fetchone()
        if row is None:
            return Response(_public_feature({"uuid": uuid}, "No playground found for given UUID."))
        return Response(_public_feature(row))
    except Exception:
        return Response(_public_feature({"uuid": uuid}, "Unknown critical error."))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def playground_by_name(request):
    """Use shared business/data logic, retaining legacy auth and response keys."""
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(playground_by_name_data(query))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def playground_only_names(request):
    # The returned user is needed for the inspector-specific SQL filter.
    user = dict(request.user)
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(playground_only_names_data(user, query))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def playground_by_device(request, fid: int):
    return Response(playground_by_device_data(fid))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def playground_by_id(request, fid: int):
    """Numeric playground lookup, retaining the optional historic 500 behavior."""
    if legacy_settings.compatibility_bugs:
        return HttpResponse("Index was outside the bounds of the array.", status=500, content_type="text/plain; charset=utf-8")
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(playground_by_id_data(fid, query))


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def playground_map_image(request):
    """Public WMS proxy: JSON base64 string, including upstream HTTP error bytes."""
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(map_image_base64(query))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([IsLegacyAuthenticated])
def playground_invalid_id(request, invalid_id: str):
    """Mirror the ASP.NET invalid-int model binding envelope."""
    return Response({
        "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
        "title": "One or more validation errors occurred.",
        "status": 400,
        "errors": {"id": [f"The value '{invalid_id}' is not valid."]},
    }, status=400)
