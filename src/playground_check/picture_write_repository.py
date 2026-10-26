"""Persist pictures using the existing transaction owned by the API handler.

Only defect pictures allocate new transfer IDs (TIDs). Device pictures are
updated using an existing FID; no new FID is generated in the web app.
"""
from __future__ import annotations

from typing import Any


def update_playdevice_picture(db: Any, fid: int, data: bytes | str) -> None:
    db.execute('UPDATE "gr_v_spielgeraete" SET picture_base64=%s WHERE fid=%s',
               (data, fid))


def insert_defect_picture(
    db: Any, defect_tid: int, picture: str, thumbnail: str, after_fixing: bool,
) -> Any:
    db.execute('LOCK TABLE "wgr_sp_insp_mangel_foto" IN EXCLUSIVE MODE')
    return db.execute("""INSERT INTO "wgr_sp_insp_mangel_foto"
        (tid, tid_maengel, picture_base64, picture_base64_thumb, zeitpunkt)
        VALUES ((SELECT COALESCE(MAX(tid),0)+1 FROM "wgr_sp_insp_mangel_foto"), %s, %s, %s, %s)
        RETURNING tid""",
        (defect_tid, picture, thumbnail, after_fixing),
    ).fetchone()
