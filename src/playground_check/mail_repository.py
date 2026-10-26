"""Database reads and sent-status update for defect info mail.

Callers manage transactions; the SMTP call happens outside all DB contexts.
"""
from __future__ import annotations
from typing import Any
from .inspection_defect_repository import DEFECT_SELECT


def defect(db: Any, tid: int):
    return db.execute(DEFECT_SELECT + " WHERE tid=%s", (tid,)).fetchone()


def recipient(db: Any, responsible_fid: Any):
    return db.execute('''SELECT fid, TRIM(CONCAT(vorname, ' ', nachname)) AS name,
                TRIM(LOWER(e_mail)) AS email, aktiv AS active
                FROM "wgr_sp_kontrolleur" WHERE fid=%s''', (responsible_fid,)).fetchone()


def device(db: Any, device_fid: Any):
    return db.execute('''SELECT sp.name AS playground_name,
                TRIM(CONCAT(COALESCE(sp.strassenname,''), ' ', COALESCE(sp.hausnummer,''))) AS address,
                gart.value AS device_type, lief.name AS supplier, geraet.bau_dat AS construction_date,
                geraet.bemerkungen AS device_comment
                FROM "gr_v_spielgeraete" geraet
                JOIN "wgr_sp_spielplatz" sp ON sp.fid=geraet.fid_spielplatz
                LEFT JOIN "wgr_sp_spielgeraeteart_tbd" gart ON geraet.id_geraeteart=gart.id
                LEFT JOIN "wgr_sp_lieferant" lief ON geraet.id_lieferant=lief.fid
                WHERE geraet.fid=%s''', (device_fid,)).fetchone()


def pictures(db: Any, defect_tid: int):
    return db.execute('''SELECT tid, picture_base64 AS picture
                FROM "wgr_sp_insp_mangel_foto" WHERE tid_maengel=%s ORDER BY tid''', (defect_tid,)).fetchall()


def mark_sent(db: Any, tid: int, recipient_name: str, recipient_fid: int):
    db.execute('''UPDATE "wgr_sp_insp_mangel" SET
                infomail_gesendet_am=CURRENT_TIMESTAMP, infomail_empfaenger=%s
                WHERE tid=%s AND fid_zustaendig_kontrolleur=%s''',
                (recipient_name, tid, recipient_fid))
