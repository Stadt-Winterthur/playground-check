"""Native DRF-facing defect reads and assignment transitions.

Use existing repositories and service serialization helpers; no legacy HTTP
handler is called. Preserve original wire format and SQL authorization.
"""
from __future__ import annotations

from playground_check import domain_support as service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request


def _authorized(request):
    legacy = to_legacy_request(request)
    user, error = service.require_user(legacy)
    return legacy, user, to_http_response(error) if error is not None else None


def get_defect(request):
    legacy, _, denied = _authorized(request)
    if denied is not None:
        return denied
    with service.connect() as db:
        row = service.inspection_defect_repository.defect_by_tid(
            db, int(legacy.query.get("tid", "0"))
        )
        result = service._defect_dict(db, row) if row else None
    return to_http_response(Response.json(result))


def get_defect_overview(request):
    _, _, denied = _authorized(request)
    if denied is not None:
        return denied
    with service.connect() as db:
        rows = service.remaining_reads_repository.defect_overview_rows(db)
    result = []
    for row in rows:
        result.append({
            "tid": row["tid"],
            "playdeviceFid": row.get("playdevice_fid") or 0,
            "playgroundName": row.get("playground_name") or "",
            "playdeviceType": row.get("playdevice_type") or "",
            "standard": row.get("standard") or "",
            "priority": row.get("priority") if row.get("priority") is not None else -1,
            "defectDescription": row.get("description") or "",
            "defectComment": row.get("comment") or "",
            "dateCreation": row.get("date_creation"),
            "dateDone": row.get("date_done"),
            "done": row.get("done_by") is not None,
            "defectsResponsibleBodyId": row.get("responsible_body_id") or -1,
            "responsibleUserFid": row.get("responsible_user_fid") or -1,
            "responsibleUserName": row.get("responsible_user_name") or "",
            "assignmentOverdue": bool(row.get("assignment_overdue")),
        })
    return to_http_response(Response.json(result))


def assignment_status(request, tid: int, *, accepted: bool):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = legacy.json() or {}
    comment = (body.get("assignmentComment") or "").strip() or None
    with service.connect() as db:
        affected = service.assignment_repository.update_assignment_status(
            db, tid, user["fid"], user["mailAddress"], comment, accepted,
        )
    return to_http_response(Response.json({"errorMessage": "" if affected == 1 else "SPK-3"}))
