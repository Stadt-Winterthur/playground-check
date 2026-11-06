from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from .config import settings


REQUIRED_RELATIONS = (
    "wgr_sp_auth_session",
    "wgr_sp_kontrolleur", "wgr_sp_spielplatz", "gr_v_spielgeraete",
    "wgr_sp_inspektionsart_tbd", "wgr_sp_sanierungsart_tbd",
    "wgr_sp_inspart_kontr", "wgr_sp_inspektion", "wgr_sp_insp_bericht",
    "wgr_sp_insp_mangel", "wgr_sp_insp_mangel_foto",
    "wgr_v_sp_ger_insp_krit", "wgr_v_sp_hfall_insp_krit",
    "wgr_v_sp_nfall_insp_krit", "wgr_sp_dringlichkeit_tbd",
    "wgr_sp_zust_mangelbeheb_tbd", "wgr_sp_abnahmen",
    "wgr_sp_zertifikat", "wgr_sp_push_subscription",
    "wgr_sp_mangel_zuweisung_hist",
)


@contextmanager
def connect(dsn: str | None = None) -> Iterator[Connection]:
    """Open a transaction against the original PostgreSQL/PostGIS database."""
    connection = psycopg.connect(
        dsn if dsn is not None else settings.postgres_dsn,
        row_factory=dict_row,
    )
    try:
        connection.execute("SELECT set_config('TimeZone', 'Europe/Zurich', true)")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_connection() -> None:
    with connect() as connection:
        connection.execute("SELECT PostGIS_Version() AS version").fetchone()
        missing = []
        for relation in REQUIRED_RELATIONS:
            row = connection.execute("SELECT to_regclass(%s) AS relation", (relation,)).fetchone()
            if row["relation"] is None:
                missing.append(relation)
        if missing:
            raise RuntimeError("Fehlende PostgreSQL-Objekte: " + ", ".join(missing))
