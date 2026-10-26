"""Read-only PostgreSQL queries shared by the legacy and DRF handlers.

All queries use the caller's connection; no transaction or API contract is changed.
"""
from __future__ import annotations
from typing import Any, Mapping
from psycopg import Connection

def playground_name_rows(db: Connection, user: Mapping[str, Any] | None, inspection_type: str) -> list[Mapping[str, Any]]:
    params: tuple[Any, ...] = ()
    sql = '''SELECT DISTINCT ON (sp.name)
        sp.name, insp.datum_inspektion AS date_of_last_inspection,
        sp.inspektion_aussetzen_von AS suspend_from,
        sp.inspektion_aussetzen_bis AS suspend_to,
        (SELECT count(*) > 0 FROM "wgr_sp_insp_mangel" mangel
         JOIN "gr_v_spielgeraete" geraete ON mangel.fid_spielgeraet=geraete.fid
         WHERE geraete.fid_spielplatz=sp.fid AND mangel.fid_erledigung IS NULL) AS has_open
        FROM "wgr_sp_spielplatz" sp
        LEFT JOIN "wgr_sp_inspektion" insp ON insp.fid_spielplatz=sp.fid
        ORDER BY sp.name, insp.datum_inspektion DESC'''
    if user and inspection_type and inspection_type != "Keine Inspektion":
        base_type = inspection_type[:-5]
        sql = '''SELECT DISTINCT ON (sp.name)
            sp.name, insp.datum_inspektion AS date_of_last_inspection,
            sp.inspektion_aussetzen_von AS suspend_from,
            sp.inspektion_aussetzen_bis AS suspend_to, false AS has_open
            FROM "wgr_sp_spielplatz" sp
            JOIN "wgr_sp_inspart_kontr" ikt ON sp.fid=ikt.fid_spielplatz
            JOIN "wgr_sp_kontrolleur" kt ON kt.fid=ikt.fid_kontrolleur
            JOIN "wgr_sp_inspektionsart_tbd" ina ON ina.id=ikt.id_inspektionsart
            LEFT JOIN "wgr_sp_inspektion" insp ON insp.fid_spielplatz=sp.fid
            WHERE trim(lower(kt.e_mail))=%s AND ina.value=%s
            ORDER BY sp.name, insp.datum_inspektion DESC'''
        params = (user["mailAddress"], base_type)
    return db.execute(sql, params).fetchall()


def public_playground_rows(db: Connection) -> list[Mapping[str, Any]]:
    return db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y FROM "wgr_sp_spielplatz"'''
            ).fetchall()


def public_playground_by_uuid(db: Connection, uuid: str) -> Mapping[str, Any] | None:
    return db.execute('''SELECT uuid::text AS uuid, nummer AS number, name,
                strassenname AS street_name, hausnummer AS house_no,
                ST_X(geom) AS x, ST_Y(geom) AS y
                FROM "wgr_sp_spielplatz" WHERE uuid::text=%s''', (uuid,)).fetchone()


def inspection_type_rows(db: Connection) -> list[Mapping[str, Any]]:
    return db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()


def renovation_type_rows(db: Connection) -> list[Mapping[str, Any]]:
    return db.execute('SELECT value FROM "wgr_sp_sanierungsart_tbd"').fetchall()


def defect_overview_rows(db: Connection) -> list[Mapping[str, Any]]:
    return db.execute('''SELECT
            mangel.tid, mangel.fid_spielgeraet AS playdevice_fid,
            spielplatz.name AS playground_name,
            COALESCE(geraeteart.value, geraeteart.short_value, '') AS playdevice_type,
            geraet.norm AS standard,
            mangel.id_dringlichkeit AS priority,
            mangel.beschrieb AS description,
            mangel.bemerkunng AS comment,
            mangel.datum AS date_creation,
            mangel.datum_erledigung AS date_done,
            mangel.fid_erledigung AS done_by,
            mangel.id_zustaendig_behebung AS responsible_body_id,
            mangel.fid_zustaendig_kontrolleur AS responsible_user_fid,
            TRIM(CONCAT(COALESCE(kontrolleur.vorname, ''), ' ', COALESCE(kontrolleur.nachname, ''))) AS responsible_user_name,
            (
                mangel.fid_erledigung IS NULL
                AND mangel.id_dringlichkeit = 1
                AND mangel.auftrag_status = 'zugewiesen'
                AND mangel.datum_auftrag_zugewiesen IS NOT NULL
                AND mangel.datum_auftrag_angenommen IS NULL
                AND mangel.datum_auftrag_abgelehnt IS NULL
                AND mangel.datum_auftrag_zugewiesen <= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ) AS assignment_overdue
            FROM "wgr_sp_insp_mangel" mangel
            LEFT JOIN "gr_v_spielgeraete" geraet ON geraet.fid=mangel.fid_spielgeraet
            LEFT JOIN "wgr_sp_spielplatz" spielplatz ON spielplatz.fid=geraet.fid_spielplatz
            LEFT JOIN "wgr_sp_spielgeraeteart_tbd" geraeteart ON geraeteart.id=geraet.id_geraeteart
            LEFT JOIN "wgr_sp_kontrolleur" kontrolleur ON kontrolleur.fid=mangel.fid_zustaendig_kontrolleur
            ORDER BY (mangel.fid_erledigung IS NOT NULL), mangel.datum, spielplatz.name, geraeteart.value
        ''').fetchall()


def playdevice_picture(db: Connection, fid: int) -> Mapping[str, Any] | None:
    return db.execute('SELECT picture_base64 AS picture FROM "gr_v_spielgeraete" WHERE fid=%s', (fid,)).fetchone()


def defect_picture(db: Connection, tid: int, thumbnail: bool = False) -> Mapping[str, Any] | None:
    column = "picture_base64_thumb" if thumbnail else "picture_base64"
    return db.execute(f'SELECT {column} AS value FROM "wgr_sp_insp_mangel_foto" WHERE tid=%s', (tid,)).fetchone()


def document_blob(db: Connection, table: str, column: str, fid: int) -> Mapping[str, Any] | None:
    allowed = {"wgr_sp_abnahmen": "abnahmedokument", "wgr_sp_zertifikat": "zertifikatsdokument"}
    if allowed.get(table) != column:
        raise ValueError("Unknown document relation")
    return db.execute(f'SELECT {column} AS content FROM "{table}" WHERE fid=%s', (fid,)).fetchone()


def playground_by_fid(db: Connection, fid: int) -> Mapping[str, Any] | None:
    return db.execute('''SELECT fid AS id, name,
            inspektion_aussetzen_von AS suspend_from, inspektion_aussetzen_bis AS suspend_to,
            NULL::date AS date_of_last_inspection, '' AS address
            FROM "wgr_sp_spielplatz" WHERE fid=%s''', (fid,)).fetchone()


def defect_creator_row(db: Connection, fid: Any) -> Mapping[str, Any] | None:
    return db.execute(
        'SELECT vorname AS first_name, nachname AS last_name FROM "wgr_sp_kontrolleur" WHERE fid=%s',
        (fid,),
    ).fetchone()


def defect_picture_rows(db: Connection, tid: int) -> list[Mapping[str, Any]]:
    return db.execute(
            'SELECT tid, zeitpunkt AS after_fixing FROM "wgr_sp_insp_mangel_foto" WHERE tid_maengel=%s',
            (tid,),
        ).fetchall()
