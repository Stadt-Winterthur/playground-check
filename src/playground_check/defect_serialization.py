"""Shared defect response assembly with explicitly supplied name/history lookups."""
from typing import Any, Mapping
from psycopg import Connection
from . import remaining_reads_repository, inspection_defect_service


def _defect_creator_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = remaining_reads_repository.defect_creator_row(db, fid)
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _defect_dict(db: Connection, row: Mapping[str, Any], pictures: bool = True, *, creator_name, history) -> dict[str, Any]:
    picture_rows = (
        remaining_reads_repository.defect_picture_rows(db, row["tid"])
        if pictures else []
    )
    return inspection_defect_service.defect_payload(
        row,
        picture_rows=picture_rows,
        done_by_name=creator_name(db, row.get("done_by")),
        created_by_name=creator_name(db, row.get("created_by_fid")),
        assignment_history=history(db, int(row["tid"])),
    )
