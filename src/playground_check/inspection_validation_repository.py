"""Read-only SQL used to validate and assemble new inspections."""
from __future__ import annotations
from typing import Any


def inspector(db: Any, email: str):
    return db.execute('SELECT fid FROM "wgr_sp_kontrolleur" WHERE trim(lower(e_mail))=%s',
                                       (email,)).fetchone()


def inspection_type(db: Any, base_type: str):
    return db.execute('SELECT id FROM "wgr_sp_inspektionsart_tbd" WHERE value=%s',
                                      (base_type,)).fetchone()


def is_authorized(db: Any, inspector_fid: int, playground_fid: int, type_id: int):
    return db.execute(
                    '''SELECT 1 FROM "wgr_sp_inspart_kontr"
                       WHERE fid_kontrolleur=%s AND fid_spielplatz=%s AND id_inspektionsart=%s
                       LIMIT 1''',
                    (inspector_fid, playground_fid, type_id),
                ).fetchone()


def device_playground(db: Any, fid: int):
    return db.execute(
                        'SELECT fid_spielplatz FROM "gr_v_spielgeraete" WHERE fid=%s', (fid,)
                    ).fetchone()


def duplicate_inspection(db: Any, playground_fid: int, type_id: int, service_date: Any):
    return db.execute(
                    '''SELECT 1 FROM "wgr_sp_inspektion"
                       WHERE fid_spielplatz=%s AND id_inspektionsart=%s AND datum_inspektion::date=%s
                       LIMIT 1''',
                    (playground_fid, type_id, service_date),
                ).fetchone()


def target_date_row(db: Any, playground_fid: int, target_column: str):
    if target_column not in {"dat_naech_visu_insp", "dat_naech_oper_insp", "dat_naech_haupt_insp"}:
        raise ValueError("Unknown target date column")
    return db.execute(
                        f'SELECT ({target_column})::date AS target FROM "wgr_sp_spielplatz" WHERE fid=%s',
                        (playground_fid,),
                    ).fetchone()


def device_check_state(db: Any, fid: int):
    return db.execute(
                        'SELECT nicht_zu_pruefen, nicht_pruefbar FROM "gr_v_spielgeraete" WHERE fid=%s', (fid,)
                    ).fetchone()
