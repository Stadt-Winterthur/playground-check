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


MAX_DEFECT_PHOTOS = 3


class DefectPhotoLimitError(ValueError):
    """The defect already has three photographs in the selected category."""


class DefectPhotoTargetError(ValueError):
    """The requested replacement does not belong to this defect/category."""


def save_defect_picture(db: Any, defect_tid: int, picture: str, thumbnail: str,
                        after_fixing: bool, replace_tid: int | None = None) -> Any:
    """Atomically enforce three photos per category or replace an existing photo.

    The exclusive table lock serializes concurrent API uploads. Photos are not
    deleted when a defect is marked complete or reopened.
    """
    db.execute('LOCK TABLE "wgr_sp_insp_mangel_foto" IN EXCLUSIVE MODE')
    if replace_tid is not None:
        row = db.execute(
            'SELECT tid FROM "wgr_sp_insp_mangel_foto" '
            'WHERE tid=%s AND tid_maengel=%s AND zeitpunkt=%s',
            (replace_tid, defect_tid, after_fixing),
        ).fetchone()
        if row is None:
            raise DefectPhotoTargetError('Foto gehört nicht zum angegebenen Mangel oder Bereich.')
        return db.execute(
            'UPDATE "wgr_sp_insp_mangel_foto" '
            'SET picture_base64=%s, picture_base64_thumb=%s '
            'WHERE tid=%s AND tid_maengel=%s RETURNING tid',
            (picture, thumbnail, replace_tid, defect_tid),
        ).fetchone()
    count = db.execute(
        'SELECT COUNT(*) AS amount FROM "wgr_sp_insp_mangel_foto" WHERE tid_maengel=%s AND zeitpunkt=%s',
        (defect_tid, after_fixing),
    ).fetchone()
    if int(count['amount']) >= MAX_DEFECT_PHOTOS:
        raise DefectPhotoLimitError('Pro Mangel und Kategorie sind maximal drei Fotos erlaubt.')
    return db.execute("""INSERT INTO "wgr_sp_insp_mangel_foto"
        (tid, tid_maengel, picture_base64, picture_base64_thumb, zeitpunkt)
        VALUES ((SELECT COALESCE(MAX(tid),0)+1 FROM "wgr_sp_insp_mangel_foto"), %s, %s, %s, %s)
        RETURNING tid""", (defect_tid, picture, thumbnail, after_fixing)).fetchone()


def delete_defect_picture(db: Any, defect_tid: int, photo_tid: int, after_fixing: bool) -> bool:
    """Remove one explicitly identified photo, not any other defect or category."""
    db.execute('LOCK TABLE "wgr_sp_insp_mangel_foto" IN EXCLUSIVE MODE')
    deleted = db.execute(
        'DELETE FROM "wgr_sp_insp_mangel_foto" '
        'WHERE tid=%s AND tid_maengel=%s AND zeitpunkt=%s RETURNING tid',
        (photo_tid, defect_tid, after_fixing),
    ).fetchone()
    return deleted is not None
