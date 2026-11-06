"""SQL access for defect assignment decisions and assignment history.

The caller owns the PostgreSQL connection and transaction. The assignment
UPDATE deliberately retains the existing SQL authorization predicate.
"""
from __future__ import annotations

from typing import Any


def user_name_row(db: Any, fid: Any) -> dict[str, Any] | None:
    row = db.execute(
        'SELECT vorname AS first_name, nachname AS last_name FROM "wgr_sp_kontrolleur" WHERE fid=%s',
        (fid,),
    ).fetchone()
    return row


def assignment_history_rows(db: Any, defect_tid: int) -> list[dict[str, Any]]:
    rows = db.execute(
        '''SELECT id, geaendert_am AS changed_at, geaendert_durch_fid AS changed_by_fid,
            geaendert_durch_name AS changed_by_name, vorher_fid AS previous_fid,
            vorher_name AS previous_name, nachher_fid AS new_fid, nachher_name AS new_name
            FROM "wgr_sp_mangel_zuweisung_hist"
            WHERE tid_mangel=%s ORDER BY geaendert_am DESC, id DESC''',
        (defect_tid,),
    ).fetchall()
    return rows


def record_assignment_change(
    db: Any, defect_tid: int, changed_by_fid: Any, changed_by_name: str | None,
    previous_fid: int | None, previous_name: str | None,
    new_fid: int | None, new_name: str | None,
) -> None:
    db.execute(
        '''INSERT INTO "wgr_sp_mangel_zuweisung_hist"
            (tid_mangel, geaendert_am, geaendert_durch_fid, geaendert_durch_name,
             vorher_fid, vorher_name, nachher_fid, nachher_name)
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s)''',
        (defect_tid, changed_by_fid, changed_by_name,
         previous_fid, previous_name, new_fid, new_name),
    )


def update_assignment_status(
    db: Any, defect_tid: int, user_fid: int, user_email: str,
    comment: str | None, accepted: bool,
) -> int:
    """Only the assigned user may accept/decline, matched by FID or email."""
    assignment_matches_user = '''(
            mangel.fid_zustaendig_kontrolleur=%s OR EXISTS (
                SELECT 1 FROM "wgr_sp_kontrolleur" kontrolleur
                WHERE kontrolleur.fid=mangel.fid_zustaendig_kontrolleur
                AND trim(lower(kontrolleur.e_mail))=%s
            )
        )'''
    params = (comment, defect_tid, user_fid, user_email)
    if accepted:
        cursor = db.execute(f'''UPDATE "wgr_sp_insp_mangel" AS mangel SET auftrag_status='angenommen',
                datum_auftrag_angenommen=CURRENT_TIMESTAMP, datum_auftrag_abgelehnt=NULL,
                bemerkung_auftrag=%s WHERE tid=%s AND {assignment_matches_user}''', params)
    else:
        cursor = db.execute(f'''UPDATE "wgr_sp_insp_mangel" AS mangel SET auftrag_status='abgelehnt',
                datum_auftrag_abgelehnt=CURRENT_TIMESTAMP, datum_auftrag_angenommen=NULL, bemerkung_auftrag=%s
                WHERE tid=%s AND {assignment_matches_user}''', params)
    return cursor.rowcount
