"""Pure validation and assignment rules for defect writes.

FID allocation is deliberately absent: only Oracle may allocate new FIDs.
The existing PostgreSQL write paths remain responsible for transfer IDs (TIDs).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def priority_two_fields_complete(body: Mapping[str, Any]) -> bool:
    try:
        priority = int(body.get("priority") or 0)
        responsible_body = int(body.get("defectsResponsibleBodyId") or -1)
        responsible_user = int(body.get("responsibleUserFid") or -1)
    except (TypeError, ValueError):
        return False
    return priority != 2 or (responsible_body > 0 and responsible_user > 0)


def responsible_user_fid(body: Mapping[str, Any]) -> int:
    """Return the legacy sentinel (-1) for an absent responsibility."""
    return int(body.get("responsibleUserFid") or -1)


def responsible_body_id(body: Mapping[str, Any]) -> Any:
    """Keep the original value type when the identifier is positive."""
    value = body.get("defectsResponsibleBodyId")
    return value if int(value or -1) > 0 else None


def update_assignment_fields(
    body: Mapping[str, Any], previous_user_fid: Any, *, now: datetime | None = None,
    parse_date,
) -> tuple[Any, bool, Any, Any, Any]:
    """Calculate assignment columns without performing database writes.

    The caller supplies its legacy date parser to preserve accepted formats.
    """
    responsible = responsible_user_fid(body)
    new_responsible = responsible if responsible > 0 else None
    changed = previous_user_fid != new_responsible
    current_time = now if now is not None else datetime.now()
    status = (
        "zugewiesen" if new_responsible and changed
        else (body.get("assignmentStatus") or "zugewiesen") if new_responsible else None
    )
    created = (
        current_time if new_responsible and changed
        else (parse_date(body.get("dateAssignmentCreated")) or current_time) if new_responsible else None
    )
    comment = None if changed else (body.get("assignmentComment") or "").strip() or None
    return new_responsible, changed, status, created, comment
