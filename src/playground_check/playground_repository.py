"""Read-only PostgreSQL queries for playground detail endpoints.

The repository owns SQL and uses a caller-provided connection.  It does not
create identifiers, commit transactions, authenticate users, or format HTTP.
"""

from __future__ import annotations

from typing import Any, Mapping
from psycopg import Connection


def playdevice_rows(db: Connection, playground_id: int) -> list[Mapping[str, Any]]:
    return db.execute('''SELECT spg.fid, spg.bemerkungen AS comment,
        ST_X(spg.geom) AS x, ST_Y(spg.geom) AS y,
        gart.short_value AS type_name, gart.value AS type_description,
        spg.norm AS standard, lief.name AS supplier,
        spg.empfohlenes_sanierungsjahr AS recommended_year,
        spg.bemerkung_empf_sanierung AS renovation_comment,
        spg.nicht_zu_pruefen AS not_to_be_checked,
        spg.nicht_pruefbar AS cannot_be_checked,
        spg.grund_nicht_pruefbar AS cannot_be_checked_reason,
        spg.bau_dat AS construction_date, spg.id_sanierungsart AS renovation_type,
        EXISTS (
            SELECT 1 FROM "wgr_sp_insp_mangel" mangel
            WHERE mangel.fid_spielgeraet=spg.fid AND mangel.fid_erledigung IS NULL
        ) AS has_open_defects
        FROM "gr_v_spielgeraete" spg
        LEFT JOIN "wgr_sp_spielgeraeteart_tbd" gart ON spg.id_geraeteart=gart.id
        LEFT JOIN "wgr_sp_lieferant" lief ON spg.id_lieferant=lief.fid
        WHERE spg.fid_spielplatz=%s''', (playground_id,)).fetchall()


def playground_by_name(db: Connection, name: str) -> Mapping[str, Any] | None:
    return db.execute('''SELECT sp.fid AS id, sp.name,
            sp.inspektion_aussetzen_von AS suspend_from,
            sp.inspektion_aussetzen_bis AS suspend_to,
            insp.datum_inspektion AS date_of_last_inspection, '' AS address
            FROM "wgr_sp_spielplatz" sp
            LEFT JOIN (SELECT fid_spielplatz, MAX(datum_inspektion) AS max_datum
                       FROM "wgr_sp_inspektion" GROUP BY fid_spielplatz) insp_max
              ON insp_max.fid_spielplatz=sp.fid
            LEFT JOIN "wgr_sp_inspektion" insp
              ON insp.fid_spielplatz=insp_max.fid_spielplatz AND insp.datum_inspektion=insp_max.max_datum
            WHERE sp.name=%s LIMIT 1''', (name,)).fetchone()


def playground_by_device(db: Connection, fid: int) -> Mapping[str, Any] | None:
    return db.execute('''SELECT sp.fid AS id, sp.name,
        TRIM(CONCAT(COALESCE(sp.strassenname,''), ' ', COALESCE(sp.hausnummer,''))) AS address,
        sp.inspektion_aussetzen_von AS suspend_from, sp.inspektion_aussetzen_bis AS suspend_to,
        NULL::date AS date_of_last_inspection
        FROM "gr_v_spielgeraete" geraet JOIN "wgr_sp_spielplatz" sp ON sp.fid=geraet.fid_spielplatz
        WHERE geraet.fid=%s''', (fid,)).fetchone()
