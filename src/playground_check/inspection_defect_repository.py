"""Read-only SQL access for inspections, criteria and defects.

All functions accept the caller's connection. They never commit, create FIDs/TIDs,
or decide about HTTP responses. The identifiers in the criteria queries are
internal constants and must not be supplied from untrusted request data.
"""
from __future__ import annotations

from typing import Any, Mapping
from psycopg import Connection

DEFECT_SELECT = '''SELECT tid, fid_spielgeraet AS playdevice_fid,
    id_dringlichkeit AS priority, beschrieb AS description,
    datum_erledigung AS date_done, fid_erledigung AS done_by,
    bemerkunng AS comment, datum AS date_creation,
    id_zustaendig_behebung AS responsible_body_id,
    fid_zustaendig_kontrolleur AS responsible_user_fid,
    auftrag_status AS assignment_status,
    datum_auftrag_zugewiesen AS assignment_created,
    datum_auftrag_angenommen AS assignment_accepted,
    datum_auftrag_abgelehnt AS assignment_rejected,
    bemerkung_auftrag AS assignment_comment,
    infomail_gesendet_am AS info_mail_sent_at,
    infomail_empfaenger AS info_mail_recipient_name,
    fid_erfassung AS created_by_fid
    FROM "wgr_sp_insp_mangel"'''


def criteria_rows(db: Connection, view: str, type_column: str, fid: int, inspection_type: str) -> list[Mapping[str, Any]]:
    if (view, type_column) not in {
        ("wgr_v_sp_ger_insp_krit", "inspektionsart"),
        ("wgr_v_sp_hfall_insp_krit", "insektionsart"),
        ("wgr_v_sp_nfall_insp_krit", "insektionsart"),
    }:
        raise ValueError("Unknown criteria relation")
    sql = f'''SELECT bereich AS realm, pruefung AS check_text, wartung AS maintenance,
        {type_column} AS inspection_type, pruefung_kurztext AS check_short_text
        FROM "{view}" WHERE fid_spielgeraet=%s AND {type_column}=%s'''
    return db.execute(sql, (fid, inspection_type)).fetchall()


def inspection_report_rows(db: Connection, fid: int, inspection_type: str) -> list[Mapping[str, Any]]:
    return db.execute('''SELECT tid, inspektionsart AS inspection_type,
            datum_inspektion AS inspection_date, kontrolleur AS inspector,
            pruefung_text AS inspection_text, pruefung_erledigt AS inspection_done,
            pruefung_kommentar AS inspection_comment, wartung_text AS maintenance_text,
            wartung_erledigung AS maintenance_done, wartung_kommentar AS maintenance_comment,
            fallschutz AS fall_protection, tid_inspektion AS inspection_tid,
            fid_spielgeraet AS playdevice_fid, fid_geraet_detail AS playdevice_detail_fid
            FROM "wgr_sp_insp_bericht"
            WHERE tid_inspektion IN (
                SELECT tid_inspektion FROM "wgr_sp_insp_bericht"
                WHERE fid_spielgeraet=%s AND inspektionsart=%s
                GROUP BY tid_inspektion, datum_inspektion
                ORDER BY datum_inspektion DESC LIMIT 2)
              AND fid_spielgeraet=%s AND inspektionsart=%s
            ORDER BY datum_inspektion, tid_inspektion DESC''',
        (fid, inspection_type, fid, inspection_type),
    ).fetchall()


def open_device_defects(db: Connection, fid: int) -> list[Mapping[str, Any]]:
    return db.execute(
        DEFECT_SELECT + " WHERE fid_spielgeraet=%s AND datum_erledigung IS NULL", (fid,)
    ).fetchall()


def defect_by_tid(db: Connection, tid: int) -> Mapping[str, Any] | None:
    return db.execute(DEFECT_SELECT + " WHERE tid=%s", (tid,)).fetchone()
