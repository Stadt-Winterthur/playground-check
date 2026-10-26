"""PostgreSQL write operations for defect records.

The caller owns the connection and transaction. This module never commits,
allocates Oracle FIDs, or opens a connection. A new defect gets only a TID.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def insert_defect(db, body: Mapping[str, Any], user: Mapping[str, Any],
                  date_done: Any, responsible: int, responsible_body: Any,
                  assigned_at: datetime | None):
    """Insert using the legacy exclusive table lock and MAX(tid)+1."""
    db.execute('LOCK TABLE "wgr_sp_insp_mangel" IN EXCLUSIVE MODE')
    row = db.execute('''INSERT INTO "wgr_sp_insp_mangel"
                (tid, fid_spielgeraet, datum, id_dringlichkeit, beschrieb, bemerkunng,
                 datum_erledigung, fid_erledigung, id_zustaendig_behebung,
                 fid_zustaendig_kontrolleur, auftrag_status, datum_auftrag_zugewiesen, bemerkung_auftrag,
                 fid_erfassung)
                VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_insp_mangel"),
                 %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING tid''',
                (body.get("playdeviceFid"), body.get("priority"), body.get("defectDescription") or "",
                 body.get("defectComment") or "", date_done, user["fid"] if date_done else None,
                 responsible_body,
                 responsible if responsible > 0 else None, "zugewiesen" if responsible > 0 else None,
                 assigned_at, (body.get("assignmentComment") or "").strip() or None,
                 user["fid"]),
            ).fetchone()
    return row


def current_responsible(db, tid: Any):
    """Read existing assignment in the caller's transaction."""
    return db.execute(
                'SELECT fid_zustaendig_kontrolleur AS responsible_user_fid FROM "wgr_sp_insp_mangel" WHERE tid=%s',
                (tid,),
            ).fetchone()


def update_defect(db, body: Mapping[str, Any], date_done: Any,
                  responsible_body: Any, new_responsible: Any,
                  assignment_status_value: Any, assignment_created_value: Any,
                  assignment_comment_value: Any, completed_by_fid: Any):
    """Update by existing TID, retaining all legacy assignment reset SQL."""
    db.execute('''UPDATE "wgr_sp_insp_mangel" SET
                id_dringlichkeit=%s, beschrieb=%s, bemerkunng=%s, datum_erledigung=%s,
                id_zustaendig_behebung=%s, fid_zustaendig_kontrolleur=%s,
                auftrag_status=%s, datum_auftrag_zugewiesen=%s, bemerkung_auftrag=%s,
                datum_auftrag_angenommen=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE datum_auftrag_angenommen END,
                datum_auftrag_abgelehnt=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE datum_auftrag_abgelehnt END,
                infomail_gesendet_am=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE infomail_gesendet_am END,
                infomail_empfaenger=CASE WHEN fid_zustaendig_kontrolleur IS DISTINCT FROM %s THEN NULL ELSE infomail_empfaenger END,
                fid_erledigung=%s WHERE tid=%s''',
                (body.get("priority"), body.get("defectDescription") or "", body.get("defectComment") or "", date_done,
                 responsible_body,
                 new_responsible, assignment_status_value, assignment_created_value, assignment_comment_value,
                 new_responsible, new_responsible, new_responsible, new_responsible,
                 completed_by_fid, body.get("tid")),
            )
