"""Database writes for inspections and their reports.

The caller owns the connection and the transaction. No connection is opened,
no commit is issued, and Oracle FIDs are never generated here. Inspection and
report records receive transfer IDs (TIDs) only.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Callable


def lock_inspection_tables(db: Any) -> None:
    """Keep the legacy exclusive lock across duplicate check and all inserts."""
    db.execute('LOCK TABLE "wgr_sp_inspektion", "wgr_sp_insp_bericht" IN EXCLUSIVE MODE')


def insert_inspection(db: Any, type_id: int, playground_fid: int,
                      service_date: date, inspector_fid: int,
                      target: date | None) -> int:
    """Insert the parent inspection with a new TID (not a FID)."""
    row = db.execute('''INSERT INTO "wgr_sp_inspektion"
                (tid, id_inspektionsart, fid_spielplatz, datum_inspektion, fid_kontrolleur, datum_soll_inspektion)
                VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_inspektion"),
                        %s, %s, %s, %s, %s) RETURNING tid''',
                (type_id, playground_fid, service_date, inspector_fid, target),
            ).fetchone()
    return row["tid"]


def insert_report(db: Any, inspection_tid: int, fid: int,
                  report: Mapping[str, Any], inspection_type: str,
                  service_date: date, inspector_name: str,
                  bool_value: Callable[[Any], bool]) -> None:
    """Insert a child report referencing the parent TID and existing device FID."""
    db.execute('''INSERT INTO "wgr_sp_insp_bericht"
                    (tid, tid_inspektion, fid_spielgeraet, fid_geraet_detail, inspektionsart,
                     datum_inspektion, kontrolleur, pruefung_text, pruefung_erledigt,
                     pruefung_kommentar, wartung_text, wartung_erledigung, wartung_kommentar, fallschutz)
                    VALUES ((SELECT CASE WHEN max(tid) IS NULL THEN 1 ELSE max(tid)+1 END FROM "wgr_sp_insp_bericht"),
                     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (inspection_tid, fid, report.get("playdeviceDetailFid") or None, inspection_type, service_date,
                     inspector_name, report.get("inspectionText") or "",
                     1 if bool_value(report.get("inspectionDone")) else 0, report.get("inspectionComment") or "",
                     report.get("maintenanceText") or "", 1 if bool_value(report.get("maintenanceDone")) else 0,
                     report.get("maintenanceComment") or "", report.get("fallProtectionType") or ""),
                )
