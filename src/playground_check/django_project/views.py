"""First native DRF endpoints; legacy endpoint contracts take precedence."""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from .access import authenticated_legacy_user
from .authentication import LegacyTokenAuthentication

from playground_check.service import require_user, playground_only_names_data, playground_by_device_data

from playground_check import __version__
from playground_check.db import connect
from playground_check.service import _public_feature, playground_by_name_data


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
    _, error = authenticated_legacy_user(request, require_user)
    return error


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([])
def inspection_types(request):
    error = _legacy_access_error(request)
    if error is not None:
        return error
    with connect() as db:
        rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    return Response([f"{row['value']} ({row['short_value']})" for row in rows])


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([])
def renovation_types(request):
    error = _legacy_access_error(request)
    if error is not None:
        return error
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
@permission_classes([])
def playground_by_name(request):
    """Use shared business/data logic, retaining legacy auth and response keys."""
    error = _legacy_access_error(request)
    if error is not None:
        return error
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(playground_by_name_data(query))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([])
def playground_only_names(request):
    # The returned user is needed for the inspector-specific SQL filter.
    user, error = authenticated_legacy_user(request, require_user)
    if error is not None:
        return error
    query = {key: values[-1] for key, values in request.query_params.lists()}
    return Response(playground_only_names_data(user, query))


@api_view(["GET"])
@authentication_classes([LegacyTokenAuthentication])
@permission_classes([])
def playground_by_device(request, fid: int):
    error = _legacy_access_error(request)
    if error is not None:
        return error
    return Response(playground_by_device_data(fid))
