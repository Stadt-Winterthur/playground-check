"""Validate a complete inspection against current server-side criteria."""
from collections import Counter
from . import playground_repository
from .playground_reads import inspection_suspended

MAX_REPORTS = 2000
GROUPS = (("wgr_v_sp_ger_insp_krit", "inspektionsart", ""),
          ("wgr_v_sp_hfall_insp_krit", "insektionsart", "Hauptfallschutz"),
          ("wgr_v_sp_nfall_insp_krit", "insektionsart", "Nebenfallschutz"))


class InspectionValidationError(ValueError):
    """Expected rejection of an inspection report against current criteria."""


def report_key(report):
    return (int(report.get("playdeviceFid") or 0), report.get("inspectionText") or "",
            report.get("maintenanceText") or "", report.get("fallProtectionType") or "")


def validate_reports(db, playground, inspection_type, reports):
    """Return canonical reports, or reject before any inspection is inserted.

    Caller has already checked the inspector assignment. All device membership,
    exemption states and criteria are reloaded; client text is never authoritative.
    Duplicate identical criteria are counted rather than silently collapsed.
    """
    if inspection_suspended(playground):
        raise InspectionValidationError("Inspektionen sind ausgesetzt.")
    devices = playground_repository.playdevice_rows(db, playground["id"])
    from .device_detail_batch import criteria_for_devices
    criteria = criteria_for_devices(db, [d["fid"] for d in devices], inspection_type.rsplit(" (", 1)[0]) if devices else {}
    expected = []
    for device in devices:
        if device.get("not_to_be_checked"):
            continue
        if device.get("cannot_be_checked"):
            if not (device.get("cannot_be_checked_reason") or "").strip():
                raise InspectionValidationError("Begründung für nicht prüfbares Gerät fehlt.")
            continue
        for view, column, fall in GROUPS:
            for criterion in criteria.get(view, {}).get(device["fid"], []):
                expected.append({"playdeviceFid": device["fid"], "inspectionType": inspection_type,
                                 "inspectionText": criterion.get("check_text") or "",
                                 "maintenanceText": criterion.get("maintenance") or "",
                                 "fallProtectionType": fall})
    if not expected or len(expected) > MAX_REPORTS or len(reports) != len(expected):
        raise InspectionValidationError("Der Bericht ist unvollständig oder zu gross.")
    if Counter(map(report_key, reports)) != Counter(map(report_key, expected)):
        raise InspectionValidationError("Geräte oder Prüfkriterien haben sich geändert.")
    # Use the server values while preserving only validated completion/comments.
    incoming = {}
    for report in reports:
        if report.get("inspectionDone") is not True or report.get("maintenanceDone") is not True:
            raise InspectionValidationError("Alle Prüf- und Wartungsschritte müssen erledigt sein.")
        for key in ("inspectionComment", "maintenanceComment"):
            if not isinstance(report.get(key, ""), str) or len(report.get(key, "")) > 2000:
                raise InspectionValidationError("Ungültiger Kommentar.")
        incoming.setdefault(report_key(report), []).append(report)
    result = []
    for criterion in expected:
        report = incoming[report_key(criterion)].pop()
        result.append({**criterion, "inspectionDone": True, "maintenanceDone": True,
                       "inspectionComment": report.get("inspectionComment", ""),
                       "maintenanceComment": report.get("maintenanceComment", "")})
    return result
