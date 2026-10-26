"""Pure read-side composition of inspection history and defect API payloads.

No HTTP, SQL, FID/TID allocation or writes. The caller owns DB access.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping


def inspection_history(
    db: Any,
    fid: int,
    inspection_types: list[str],
    *,
    load_reports: Callable[[Any, int, str], list[Mapping[str, Any]]],
    serialize_report: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    last: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    for inspection_type in inspection_types:
        rows = load_reports(db, fid, inspection_type)
        if not rows:
            continue
        first_tid = rows[0].get("inspection_tid")
        previous.append(serialize_report(rows[0]))
        for row in rows[1:]:
            (previous if row.get("inspection_tid") == first_tid else last).append(serialize_report(row))
    return last, previous


def defect_payload(
    row: Mapping[str, Any],
    *,
    picture_rows: list[Mapping[str, Any]],
    done_by_name: str,
    created_by_name: str,
    assignment_history: list[dict[str, Any]],
) -> dict[str, Any]:
    before: list[int] = []
    after: list[int] = []
    for picture in picture_rows:
        (after if picture["after_fixing"] else before).append(picture["tid"])
    return {
        "tid": row["tid"], "playdeviceFid": row.get("playdevice_fid") or 0,
        "priority": row.get("priority") if row.get("priority") is not None else -1,
        "defectPicsTids": before, "defectPicsAfterFixingTids": after,
        "defectDescription": row.get("description") or "", "dateCreation": row.get("date_creation"),
        "dateDone": row.get("date_done"), "done": row.get("done_by") is not None,
        "doneByFid": row.get("done_by") or -1,
        "doneByName": done_by_name,
        "defectComment": row.get("comment") or "",
        "defectsResponsibleBodyId": row.get("responsible_body_id") or -1,
        "responsibleUserFid": row.get("responsible_user_fid") or -1,
        "assignmentStatus": row.get("assignment_status") or "",
        "dateAssignmentCreated": row.get("assignment_created"),
        "dateAssignmentAccepted": row.get("assignment_accepted"),
        "dateAssignmentRejected": row.get("assignment_rejected"),
        "assignmentComment": row.get("assignment_comment") or "",
        "infoMailSentAt": row.get("info_mail_sent_at"),
        "infoMailRecipientName": row.get("info_mail_recipient_name") or "",
        "createdByFid": row.get("created_by_fid") or -1,
        "createdByName": created_by_name,
        "assignmentHistory": assignment_history,
        "errorMessage": "",
    }
