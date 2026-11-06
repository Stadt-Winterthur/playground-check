"""Shared playground reads and device composition, independent of HTTP routing.

Adapters bind connection providers and the selected detail-building strategy.
"""
from typing import Any, Mapping
from psycopg import Connection
from . import playground_repository, remaining_reads_repository, inspection_defect_repository, inspection_defect_service
from .domain_values import _bool, DOTNET_MIN_DATE
from .playground_reads import inspection_suspended as _suspended
from .playground_detail_serializers import criterion_dict as _criterion_dict, report_dict as _report_dict, playdevice_feature


def playground_only_names_data(user: Mapping[str, Any] | None, query: Mapping[str, str], *, connect_db) -> list[dict[str, Any]]:
    """Existing filtered playground list without any HTTP framework dependencies."""
    inspection_type = query.get("inspectiontype", query.get("inspectionType", ""))
    with connect_db() as db:
        rows = remaining_reads_repository.playground_name_rows(db, user, inspection_type)
    result = []
    for row in rows:
        suspended = _suspended(row)
        if inspection_type != "Keine Inspektion" and suspended:
            continue
        result.append({
            "id": 0, "name": row["name"], "address": "",
            "dateOfLastInspection": row["date_of_last_inspection"] or DOTNET_MIN_DATE,
            "suspendInspectionFrom": row["suspend_from"], "suspendInspectionTo": row["suspend_to"],
            "inspectionSuspended": suspended, "hasOpenDeviceDefects": bool(row["has_open"]),
            "playdevices": [], "defectPriorityOptions": [], "inspectionTypeOptions": [],
            "renovationTypeOptions": [], "defectsResponsibleBodyOptions": [],
            "documentsOfAcceptanceFids": [], "certificateDocumentsFids": [],
        })
    return result


def _playdevice_rows(db: Connection, playground_id: int) -> list[Mapping[str, Any]]:
    return playground_repository.playdevice_rows(db, playground_id)


def _criteria(db: Connection, view: str, type_column: str, fid: int, inspection_type: str) -> list[dict[str, Any]]:
    # View and column names are fixed constants originating in the C# service.
    return [_criterion_dict(row) for row in inspection_defect_repository.criteria_rows(db, view, type_column, fid, inspection_type)]


def _inspection_history(db: Connection, fid: int, inspection_types: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return inspection_defect_service.inspection_history(
        db, fid, inspection_types,
        load_reports=inspection_defect_repository.inspection_report_rows,
        serialize_report=_report_dict,
    )


def _playdevice(db: Connection, row: Mapping[str, Any], inspection_type: str, with_defects: bool, with_inspections: bool, *, load_criteria, load_history, serialize_defect) -> dict[str, Any]:
    base_type = inspection_type[:-5] if inspection_type and len(inspection_type) > 5 else inspection_type
    general: list[dict[str, Any]] = []
    main: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    last: list[dict[str, Any]] = []
    previous: list[dict[str, Any]] = []
    if with_inspections:
        general = load_criteria(db, "wgr_v_sp_ger_insp_krit", "inspektionsart", row["fid"], base_type)
        main = load_criteria(db, "wgr_v_sp_hfall_insp_krit", "insektionsart", row["fid"], base_type)
        secondary = load_criteria(db, "wgr_v_sp_nfall_insp_krit", "insektionsart", row["fid"], base_type)
        types = remaining_reads_repository.inspection_type_rows(db)
        last, previous = load_history(db, row["fid"], [f"{x['value']} ({x['short_value']})" for x in types])
    defects = None
    if with_defects:
        defects = [serialize_defect(db, item, False) for item in inspection_defect_repository.open_device_defects(db, row["fid"])]
    return playdevice_feature(
        row, general=general, main=main, secondary=secondary, last=last,
        previous=previous, defects=defects, min_date=DOTNET_MIN_DATE,
    )


def playground_by_name_data(query: Mapping[str, str], *, connect_db, build_result) -> dict[str, Any]:
    """Return the established detail payload independently of the HTTP framework."""
    with connect_db() as db:
        row = playground_repository.playground_by_name(db, query.get("name", ""))
        if not row:
            raise LookupError("Sequence contains no elements")
        inspection = query.get("inspectiontype", query.get("inspectionType", ""))
        result = build_result(db, row, inspection, _bool(query.get("withdefects")), _bool(query.get("withinspections")))
    return result


def playground_by_id_data(fid: int, query: Mapping[str, str], *, connect_db, build_result) -> dict[str, Any] | None:
    """Build the established ID detail payload without legacy HTTP handlers."""
    with connect_db() as db:
        row = remaining_reads_repository.playground_by_fid(db, fid)
        if row is None:
            return None
        return build_result(
            db, row, query.get("inspectiontype", ""),
            _bool(query.get("withdefects")), _bool(query.get("withinspections")),
        )


def playground_by_device_data(fid: int, *, connect_db, load_devices, build_device) -> dict[str, Any]:
    """Read-only device lookup shared by legacy WSGI and DRF."""
    if fid <= 0:
        return {"id": 0, "name": "", "address": "", "playdevices": []}
    with connect_db() as db:
        row = playground_repository.playground_by_device(db, fid)
        if not row:
            return {"id": 0, "name": "", "address": "", "playdevices": []}
        devices = [build_device(db, item, "", False, False) for item in load_devices(db, row["id"]) if item["fid"] == fid]
    return {
        "id": row["id"], "name": row.get("name") or "", "address": row.get("address") or "",
        "dateOfLastInspection": DOTNET_MIN_DATE, "suspendInspectionFrom": None, "suspendInspectionTo": None,
        "inspectionSuspended": False, "hasOpenDeviceDefects": False, "playdevices": devices,
        "defectPriorityOptions": [], "inspectionTypeOptions": [], "renovationTypeOptions": [],
        "defectsResponsibleBodyOptions": [], "chosenTypeOfInspection": "",
        "documentsOfAcceptanceFids": [], "certificateDocumentsFids": [],
    }
