"""Shared assignment history composition; caller owns the transaction."""
from typing import Any, Mapping
from psycopg import Connection
from . import assignment_repository


def _user_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = assignment_repository.user_name_row(db, fid)
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _record_assignment_change(
    db: Connection, defect_tid: int, changed_by: Mapping[str, Any], previous_fid: Any, new_fid: Any
) -> None:
    previous = int(previous_fid) if previous_fid else None
    new = int(new_fid) if new_fid else None
    if previous == new:
        return
    changed_by_name = f"{changed_by.get('firstName') or ''} {changed_by.get('lastName') or ''}".strip()
    assignment_repository.record_assignment_change(
        db, defect_tid, changed_by.get("fid"), changed_by_name or None,
        previous, _user_name(db, previous) or None, new, _user_name(db, new) or None,
    )


def _assignment_history(db: Connection, defect_tid: int) -> list[dict[str, Any]]:
    rows = assignment_repository.assignment_history_rows(db, defect_tid)
    return [{
        "id": row.get("id"),
        "changedAt": row.get("changed_at"),
        "changedByFid": row.get("changed_by_fid") or -1,
        "changedByName": row.get("changed_by_name") or "",
        "previousUserFid": row.get("previous_fid") or -1,
        "previousUserName": row.get("previous_name") or "",
        "newUserFid": row.get("new_fid") or -1,
        "newUserName": row.get("new_name") or "",
    } for row in rows]
