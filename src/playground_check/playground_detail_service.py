"""Read-only orchestration for detailed playground responses.

The caller owns the database connection and transaction. This module does not
create FIDs or TIDs, initiate writes, or know about HTTP/DRF.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .playground_reads import inspection_suspended


def build_playground_detail(
    db: Any,
    row: Mapping[str, Any],
    inspection_type: str,
    with_defects: bool,
    with_inspections: bool,
    *,
    load_devices: Callable[[Any, int], list[Mapping[str, Any]]],
    build_device: Callable[[Any, Mapping[str, Any], str, bool, bool], dict[str, Any]],
    document_name: Callable[[Any, str], str],
    compatibility_bugs: bool,
    min_date: str,
) -> dict[str, Any]:
    """Construct the existing API payload using the caller's DB connection."""
    devices = [
        build_device(db, item, inspection_type, with_defects, with_inspections)
        for item in load_devices(db, row["id"])
        if not item.get("not_to_be_checked")
    ]
    priorities = db.execute('SELECT id, short_value, value FROM "wgr_sp_dringlichkeit_tbd"').fetchall()
    priority_options = []
    for item in priorities:
        short = (item.get("short_value") or "").strip()
        long = (item.get("value") or "").strip()
        final = short + (f" ({long})" if short and long else long)
        if final:
            priority_options.append(final)
    type_rows = db.execute('SELECT short_value, value FROM "wgr_sp_inspektionsart_tbd"').fetchall()
    type_options = [f"{item['value']} ({item['short_value']})" for item in type_rows]
    renovations = [{"id": item["id"], "value": item["value"]} for item in db.execute(
        'SELECT id, value FROM "wgr_sp_sanierungsart_tbd"'
    ).fetchall()]
    if compatibility_bugs and renovations:
        renovations = [dict(renovations[-1]) for _ in renovations]
    bodies = [{"id": item["id"], "value": item["value"]} for item in db.execute(
        'SELECT id, value FROM "wgr_sp_zust_mangelbeheb_tbd"'
    ).fetchall()]
    acceptance_rows = db.execute(
        'SELECT fid, substring(abnahmedokument from greatest(octet_length(abnahmedokument)-1023,1)) AS meta_tail '
        'FROM "wgr_sp_abnahmen" WHERE fid_spielplatz=%s AND abnahmedokument IS NOT NULL ORDER BY fid', (row["id"],)
    ).fetchall()
    certificate_rows = db.execute(
        'SELECT fid, substring(zertifikatsdokument from greatest(octet_length(zertifikatsdokument)-1023,1)) AS meta_tail '
        'FROM "wgr_sp_zertifikat" WHERE fid_spielplatz=%s AND zertifikatsdokument IS NOT NULL ORDER BY fid', (row["id"],)
    ).fetchall()
    acceptance = [item["fid"] for item in acceptance_rows]
    certificates = [item["fid"] for item in certificate_rows]
    acceptance_documents = [
        {"fid": item["fid"], "name": document_name(item.get("meta_tail"), str(item["fid"]))}
        for item in acceptance_rows
    ]
    certificate_documents = [
        {"fid": item["fid"], "name": document_name(item.get("meta_tail"), str(item["fid"]))}
        for item in certificate_rows
    ]
    return {
        "id": row["id"], "name": row.get("name") or "", "address": row.get("address") or "",
        "dateOfLastInspection": row.get("date_of_last_inspection") or min_date,
        "suspendInspectionFrom": row.get("suspend_from"), "suspendInspectionTo": row.get("suspend_to"),
        "inspectionSuspended": inspection_suspended(row), "hasOpenDeviceDefects": False,
        "playdevices": devices, "defectPriorityOptions": priority_options,
        "inspectionTypeOptions": type_options, "renovationTypeOptions": renovations,
        "defectsResponsibleBodyOptions": bodies, "chosenTypeOfInspection": "",
        "documentsOfAcceptanceFids": acceptance, "certificateDocumentsFids": certificates,
        "documentsOfAcceptance": acceptance_documents, "certificateDocuments": certificate_documents,
    }
