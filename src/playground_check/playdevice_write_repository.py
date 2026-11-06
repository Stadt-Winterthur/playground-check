"""PostgreSQL writes for existing playground devices.

FID values are supplied by the Oracle master and are never generated here.
The caller owns the database connection and transaction.
"""
from __future__ import annotations

from typing import Any


def device_for_update(db: Any, fid: int):
    return db.execute('''SELECT empfohlenes_sanierungsjahr AS recommended_year,
        id_sanierungsart AS renovation_type, bemerkung_empf_sanierung AS renovation_comment,
        nicht_zu_pruefen AS not_to_be_checked, nicht_pruefbar AS cannot_be_checked,
        grund_nicht_pruefbar AS cannot_be_checked_reason
        FROM "gr_v_spielgeraete" WHERE fid=%s FOR UPDATE''', (fid,)).fetchone()


def renovation_type_exists(db: Any, kind: int) -> bool:
    return db.execute('SELECT id FROM "wgr_sp_sanierungsart_tbd" WHERE id=%s', (kind,)).fetchone() is not None


def update_playdevice(
    db: Any,
    recommended_year: Any,
    renovation_type: Any,
    comment: Any,
    cannot_be_checked: bool,
    cannot_be_checked_reason: str,
    fid: int,
) -> int:
    cursor = db.execute('''UPDATE "gr_v_spielgeraete" SET
                empfohlenes_sanierungsjahr=%s, id_sanierungsart=%s,
                bemerkung_empf_sanierung=%s, nicht_pruefbar=%s,
                grund_nicht_pruefbar=%s WHERE fid=%s
                AND COALESCE(nicht_zu_pruefen, false)=false''',
               (recommended_year, renovation_type, comment,
                cannot_be_checked, cannot_be_checked_reason, fid))
    return cursor.rowcount



def update_renovation_only(db: Any, recommended_year: Any, renovation_type: Any,
                           comment: Any, fid: int) -> int:
    """Renovation edits MUST NOT rewrite inspection-specific checkability state."""
    cursor = db.execute("""UPDATE "gr_v_spielgeraete" SET
                  empfohlenes_sanierungsjahr=%s, id_sanierungsart=%s,
                  bemerkung_empf_sanierung=%s WHERE fid=%s""",
               (recommended_year, renovation_type, comment, fid))
    return cursor.rowcount


def update_checkability_only(db: Any, cannot_be_checked: bool,
                              reason: str, fid: int) -> int:
    """Inspection checkability edits MUST NOT rewrite renovation state."""
    cursor = db.execute("""UPDATE "gr_v_spielgeraete" SET
                  nicht_pruefbar=%s, grund_nicht_pruefbar=%s WHERE fid=%s
                  AND COALESCE(nicht_zu_pruefen, false)=false""",
               (cannot_be_checked, reason, fid))

    return cursor.rowcount
