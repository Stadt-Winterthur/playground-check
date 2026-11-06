"""DRF-facing inspection and playdevice commands using existing repositories.

Legacy request/response conversion is retained for wire-level compatibility,
not for routing into legacy service HTTP handlers.
"""
from __future__ import annotations

from playground_check.business_time import local_now, local_today

from pathlib import Path
from datetime import date
from playground_check.inspection_submission import validate_reports, MAX_REPORTS, InspectionValidationError
from playground_check.remaining_reads_repository import playground_by_fid
from playground_check.playdevice_service import save_device, DeviceWriteError

from playground_check import domain_support as service
from playground_check.http import Response

from .api_wire import to_http_response, to_legacy_request
from .operation_errors import operation_errors
from .api_input import object_body, list_body, mapping, positive_query_id
from .uploads import is_multipart, multipart_parts, image_file, UploadTooLarge


def _respond(result):
    return to_http_response(result)


@operation_errors()
def create_inspection(request):
    legacy = to_legacy_request(request)
    user = service.current_user(legacy, dry_run=service._bool(legacy.query.get("dryRun")))
    if not user:
        return _respond(Response.text("Unauthorized", 401))
    if user.get("role") not in {"inspector", "administrator"}:
        return _respond(Response.text("Benutzer der Rolle Wartung dürfen keine Kontrollen durchführen.", 403))
    reports = list_body(legacy,
        strings=('inspectionType', 'inspectionText', 'maintenanceText', 'inspectionComment', 'maintenanceComment', 'fallProtectionType'),
        integers=('playdeviceFid', 'playdeviceDetailFid'), booleans=('inspectionDone', 'maintenanceDone'))
    if not isinstance(reports, list) or not reports:
        return _respond(Response.json({"errorMessage": "SPK-0"}))
    if len(reports) > MAX_REPORTS or not all(isinstance(r, dict) for r in reports):
        return _respond(Response.json({"errorMessage": "SPK-6"}, 400))
    inspection_type = reports[0].get("inspectionType") or ""
    if not inspection_type or any(report.get("inspectionType") != inspection_type for report in reports):
        return _respond(Response.json({"errorMessage": "SPK-6"}))
    if not isinstance(inspection_type, str):
        return _respond(Response.json({"errorMessage": "SPK-6"}, 400))
    base_type = inspection_type.rsplit(" (", 1)[0]
    service_date = local_today()
    with service.connect() as db:
        inspector = service.inspection_validation_repository.inspector(db, user["mailAddress"])
        type_row = service.inspection_validation_repository.inspection_type(db, base_type)
        if type_row and inspection_type != f"{type_row['value']} ({type_row['short_value']})":
            return _respond(Response.json({"errorMessage": "SPK-6"}, 400))
        first_fid = int(reports[0].get("playdeviceFid") or 0)
        playground = service.inspection_validation_repository.device_playground(db, first_fid)
        inspector_fid = inspector["fid"] if inspector else None
        type_id = type_row["id"] if type_row else None
        playground_fid = playground["fid_spielplatz"] if playground else None
        if not inspector_fid or not type_id or not playground_fid:
            return _respond(Response.json({"errorMessage": "SPK-11"}))
        authorized = service.inspection_validation_repository.is_authorized(db, inspector_fid, playground_fid, type_id)
        if not authorized:
            return _respond(Response.json({"errorMessage": "SPK-11"}))
        service.inspection_write_repository.lock_inspection_tables(db)
        current_playground = playground_by_fid(db, playground_fid)
        if not current_playground:
            return _respond(Response.json({"errorMessage": "SPK-12"}, 400))
        try:
            reports = validate_reports(db, current_playground, inspection_type, reports)
        except InspectionValidationError:
            return _respond(Response.json({"errorMessage": "SPK-13"}, 400))
        duplicate = service.inspection_validation_repository.duplicate_inspection(db, playground_fid, type_id, service_date)
        if duplicate:
            return _respond(Response.json({"errorMessage": "SPK-2"}))
        target = None
        target_column = {1: "dat_naech_visu_insp", 2: "dat_naech_oper_insp", 3: "dat_naech_haupt_insp"}.get(type_id)
        if target_column and playground_fid:
            target_row = service.inspection_validation_repository.target_date_row(db, playground_fid, target_column)
            target = target_row["target"] if target_row else None
        inspection_tid = service.inspection_write_repository.insert_inspection(
            db, type_id, playground_fid, service_date, inspector_fid, target,
        )
        for report in reports:
            fid = int(report.get("playdeviceFid") or 0)
            if not fid:
                raise ValueError("Missing playdevice fid")
            service.inspection_write_repository.insert_report(
                db, inspection_tid, fid, report, inspection_type, service_date,
                f"{user['firstName']} {user['lastName']}", service._bool,
            )
    return _respond(Response.json({"errorMessage": ""}))


def _require_device_editor(legacy):
    user, error = service.require_user(legacy)
    if error is not None:
        return user, error
    if not user or user.get("role") not in {"inspector", "administrator"}:
        return user, Response.text("Keine Berechtigung für Geräteänderungen.", 403)
    return user, None


@operation_errors()
def save_playdevice(request):
    legacy = to_legacy_request(request)
    _, error = _require_device_editor(legacy)
    if error:
        return _respond(error)
    body = object_body(legacy)
    props = mapping(body.get("properties", {}))
    if not props:
        return _respond(Response.json({"errorMessage": "SPK-5"}))
    try:
        with service.connect() as db:
            save_device(db, props)
        return _respond(Response.json({"errorMessage": ""}))
    except DeviceWriteError as exc:
        return _respond(Response.json({"errorMessage": str(exc)}, exc.status))


@operation_errors()
def get_playdevice_picture(request, fid: int):
    legacy = to_legacy_request(request, fid=fid)
    if service._bool(legacy.query.get("dryRun")):
        return _respond(Response(b"", 200, "application/json; charset=utf-8"))
    _, error = service.require_user(legacy)
    if error:
        return _respond(error)
    with service.connect() as db:
        row = service.remaining_reads_repository.playdevice_picture(db, fid)
    if not row:
        return _respond(Response.text("Spielgerät nicht gefunden.", 404))
    data, mime = service._decode_image(row["picture"]) if row["picture"] else (None, None)
    if not data:
        placeholder = Path(__file__).resolve().parents[1] / 'static/assets/no-device-photo.svg'
        response = _respond(Response.file(placeholder.read_bytes(), "image/svg+xml"))
        response['Cache-Control'] = 'private, no-store'
        return response
    return _respond(Response.file(data, mime))


@operation_errors()
def exchange_playdevice_picture(request):
    legacy = to_legacy_request(request, read_body=not is_multipart(request))
    _, error = _require_device_editor(legacy)
    if error:
        return _respond(error)
    fid = positive_query_id(legacy, "fid")
    if fid < 1:
        return _respond(Response.json({"errorMessage": "SPK-7"}))
    if service._image_request_too_large(legacy):
        return _respond(Response.text("Bild-Upload ist zu gross.", 413))
    if is_multipart(request):
        _, files = multipart_parts(request, {'picture'})
        data = image_file(files.get('picture'))
    else:
        body = object_body(legacy, strings=('data',))
        data = body.get('data')
        image_error = service._image_upload_error(data)
        if image_error:
            if image_error == 'Bild ist zu gross (maximal 10 MiB).':
                raise UploadTooLarge()
            return _respond(Response.text(image_error, 400))
    if not service._bool(legacy.query.get("dryRun")):
        with service.connect() as db:
            service.picture_write_repository.update_playdevice_picture(db, fid, str(data).encode("ascii", "replace"))
    return _respond(Response.json({"errorMessage": ""}))


@operation_errors()
def put_playdevice_picture(request, fid: int):
    legacy = to_legacy_request(request, read_body=not is_multipart(request), fid=fid)
    _, error = _require_device_editor(legacy)
    if error:
        return _respond(error)
    if service._bool(legacy.query.get("dryRun")):
        return _respond(Response(b"", 200, "application/json; charset=utf-8"))
    if service._image_request_too_large(legacy):
        return _respond(Response.text("Bild-Upload ist zu gross.", 413))
    if is_multipart(request):
        _, files = multipart_parts(request, {'picture'})
        data = image_file(files.get('picture'))
    else:
        body = object_body(legacy, strings=('data',))
        data = body.get('data')
        image_error = service._image_upload_error(data)
        if image_error:
            if image_error == 'Bild ist zu gross (maximal 10 MiB).':
                raise UploadTooLarge()
            return _respond(Response.text(image_error, 400))
    with service.connect() as db:
        service.picture_write_repository.update_playdevice_picture(db, fid, data)
    return _respond(Response(b"", 200, "application/json; charset=utf-8"))
