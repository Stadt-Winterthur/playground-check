"""DRF-facing inspection and playdevice commands using existing repositories.

Legacy request/response conversion is retained for wire-level compatibility,
not for routing into legacy service HTTP handlers.
"""
from __future__ import annotations

from datetime import date

from playground_check import service
from playground_check.http import Response

from .legacy_adapter import to_http_response, to_legacy_request


def _respond(result):
    return to_http_response(result)


def create_inspection(request):
    legacy = to_legacy_request(request)
    user = service.current_user(legacy, dry_run=service._bool(legacy.query.get("dryRun")))
    if not user:
        return _respond(Response.text("Unauthorized", 401))
    if user.get("role") == "maintenance":
        return _respond(Response.text("Benutzer der Rolle Wartung dürfen keine Kontrollen durchführen.", 403))
    reports = legacy.json()
    if not isinstance(reports, list) or not reports:
        return _respond(Response.json({"errorMessage": "SPK-0"}))
    inspection_type = reports[0].get("inspectionType") or ""
    if not inspection_type or any(report.get("inspectionType") != inspection_type for report in reports):
        return _respond(Response.json({"errorMessage": "SPK-6"}))
    base_type = inspection_type[:-5] if len(inspection_type) > 4 else inspection_type
    service_date = date.today()
    try:
        with service.connect() as db:
            inspector = service.inspection_validation_repository.inspector(db, user["mailAddress"])
            type_row = service.inspection_validation_repository.inspection_type(db, base_type)
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
            for report in reports:
                fid = int(report.get("playdeviceFid") or 0)
                if not fid:
                    return _respond(Response.json({"errorMessage": "SPK-12"}))
                device_playground = service.inspection_validation_repository.device_playground(db, fid)
                if not device_playground or device_playground["fid_spielplatz"] != playground_fid:
                    return _respond(Response.json({"errorMessage": "SPK-12"}))
            service.inspection_write_repository.lock_inspection_tables(db)
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
                device = service.inspection_validation_repository.device_check_state(db, fid)
                if not device or device.get("nicht_zu_pruefen") or device.get("nicht_pruefbar"):
                    continue
                service.inspection_write_repository.insert_report(
                    db, inspection_tid, fid, report, inspection_type, service_date,
                    f"{user['firstName']} {user['lastName']}", service._bool,
                )
        return _respond(Response.json({"errorMessage": ""}))
    except Exception:
        return _respond(Response.json({"errorMessage": "SPK-3"}))


def save_playdevice(request):
    legacy = to_legacy_request(request)
    _, error = service.require_user(legacy)
    if error:
        return _respond(error)
    body = legacy.json()
    props = (body or {}).get("properties", {})
    if not props:
        return _respond(Response.json({"errorMessage": "SPK-5"}))
    try:
        with service.connect() as db:
            service.playdevice_write_repository.update_playdevice(
                db,
                props.get("recommendedYearOfRenovation") if int(props.get("recommendedYearOfRenovation") or 0) > 0 else None,
                props.get("renovationType") if int(props.get("renovationType") or 0) != 0 else None,
                props.get("commentRecommendedYearOfRenovation") or None,
                service._bool(props.get("cannotBeChecked")),
                props.get("cannotBeCheckedReason") or "",
                int(props.get("fid") or 0),
            )
        return _respond(Response.json({"errorMessage": ""}))
    except Exception:
        return _respond(Response.json({"errorMessage": "SPK-3"}))


def get_playdevice_picture(request, fid: int):
    legacy = to_legacy_request(request, fid=fid)
    if service._bool(legacy.query.get("dryRun")):
        return _respond(Response(b"", 200, "application/json; charset=utf-8"))
    _, error = service.require_user(legacy)
    if error:
        return _respond(error)
    with service.connect() as db:
        row = service.remaining_reads_repository.playdevice_picture(db, fid)
    if not row or row["picture"] is None:
        return _respond(Response.text("Kein Bild vorhanden.", 404))
    data, mime = service._decode_image(row["picture"])
    return _respond(Response.file(data, mime) if data else Response.text("Kein Bild vorhanden.", 404))


def exchange_playdevice_picture(request):
    legacy = to_legacy_request(request)
    _, error = service.require_user(legacy)
    if error:
        return _respond(error)
    fid = int(legacy.query.get("fid") or 0)
    if fid < 1:
        return _respond(Response.json({"errorMessage": "SPK-7"}))
    if service._image_request_too_large(legacy):
        return _respond(Response.text("Bild-Upload ist zu gross.", 413))
    body = legacy.json() or {}
    data = body.get("data") if "data" in body else body.get("Data")
    data = data.strip() if isinstance(data, str) else data
    if not data:
        return _respond(Response.json({"errorMessage": "SPK-6"}))
    image_error = service._image_upload_error(data)
    if image_error:
        return _respond(Response.text(image_error, 400))
    if not service._bool(legacy.query.get("dryRun")):
        with service.connect() as db:
            service.picture_write_repository.update_playdevice_picture(db, fid, str(data).encode("ascii", "replace"))
    return _respond(Response.json({"errorMessage": ""}))


def put_playdevice_picture(request, fid: int):
    legacy = to_legacy_request(request, fid=fid)
    _, error = service.require_user(legacy)
    if error:
        return _respond(error)
    if service._bool(legacy.query.get("dryRun")):
        return _respond(Response(b"", 200, "application/json; charset=utf-8"))
    if service._image_request_too_large(legacy):
        return _respond(Response.text("Bild-Upload ist zu gross.", 413))
    body = legacy.json() or {}
    data = body.get("data") if "data" in body else body.get("Data")
    image_error = service._image_upload_error(data)
    if image_error:
        return _respond(Response.text(image_error, 400))
    with service.connect() as db:
        service.picture_write_repository.update_playdevice_picture(db, fid, data)
    return _respond(Response(b"", 200, "application/json; charset=utf-8"))
