"""Pure inspection form models and report assembly; no HTTP, SQL or writes."""
from playground_check.inspection_submission import MAX_REPORTS
from .inspection_history_ui import history_groups


class InspectionFormError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def inspection_devices(payload, kind, device_label='Spielgerät'):
    devices = []
    options = payload.get("inspectionTypeOptions") or []
    for item in payload.get("playdevices") or []:
        try:
            fid = int((item.get("properties") or {}).get("fid") or item.get("fid") or 0)
        except (TypeError, ValueError):
            continue
        if fid > 0:
            props = item.get("properties") or item
            groups = (("generalInspectionCriteria", ""),
                      ("mainFallProtectionInspectionCriteria", "Hauptfallschutz"),
                      ("secondaryFallProtectionInspectionCriteria", "Nebenfallschutz"))
            checks = []
            for group, fall in groups:
                for criterion in props.get(group) or []:
                    checks.append({"index": len(checks), "group": group, "fall": fall,
                                   "label": criterion.get("checkShortText") or criterion.get("check") or "Prüfung",
                                   "realm": criterion.get("realm") or "",
                                   "check": criterion.get("check") or "",
                                   "maintenance": criterion.get("maintenance") or "",
                                   "comment": "", "maintenance_comment": "",
                                   "inspection_done": False, "maintenance_done": False})
            devices.append({"fid": fid, "name": item.get("name") or props.get("type", {}).get("description") or f"{device_label} {fid}",
                            "checks": checks, "not_to_be_checked": bool(props.get("notToBeChecked")),
                            "cannot_be_checked": bool(props.get("cannotBeChecked")),
                            "cannot_reason": props.get("cannotBeCheckedReason") or "",
                            "type_name": (props.get("type") or {}).get("name") or "",
                            "standard": (props.get("type") or {}).get("standard") or "",
                            "supplier": props.get("supplier") or "",
                            "coordinates": (item.get("geometry") or {}).get("coordinates") or [],
                            "history_last": props.get("lastInspectionReports") or [],
                            "history_previous": props.get("nextToLastInspectionReports") or [],
                            "history_last_groups": history_groups(props.get("lastInspectionReports") or [], options, kind),
                            "history_previous_groups": history_groups(props.get("nextToLastInspectionReports") or [], options, kind)})
    if not devices or len(devices) > 300 or len({d["fid"] for d in devices}) != len(devices):
        raise InspectionFormError("Keine gültige Geräteliste verfügbar.")
    if sum(len(d["checks"]) for d in devices) > MAX_REPORTS:
        raise InspectionFormError("Dieser Spielplatz enthält zu viele Prüfkriterien. Bitte die Administration kontaktieren.")
    return devices


def bind_inspection_values(devices, form):
    """Retain entered values on navigation and validation errors."""
    for device in devices:
        for criterion in device["checks"]:
            key = f'{device["fid"]}_{criterion["index"]}'
            criterion["comment"] = (form.get(f"comment_{key}") or "")[:2000]
            criterion["maintenance_comment"] = (form.get(f"maintenance_comment_{key}") or "")[:2000]
            criterion["inspection_done"] = form.get(f"inspection_done_{key}") == "on"
            criterion["maintenance_done"] = form.get(f"maintenance_done_{key}") == "on"


def inspection_reports(devices, form, kind):
    reports = []
    for device in devices:
        fid = device["fid"]
        if device["not_to_be_checked"]:
            continue
        if device["cannot_be_checked"]:
            if not device["cannot_reason"].strip():
                raise InspectionFormError("Für ein nicht prüfbares Spielgerät muss eine Begründung hinterlegt sein.")
            continue
        for criterion in device["checks"]:
            i = criterion["index"]
            key = f"{fid}_{i}"
            comment = (form.get(f"comment_{key}") or "").strip()
            maintenance_comment = (form.get(f"maintenance_comment_{key}") or "").strip()
            if len(comment) > 2000 or len(maintenance_comment) > 2000:
                raise InspectionFormError("Ein Kommentar ist zu lang (maximal 2000 Zeichen).")
            if form.get(f"inspection_done_{key}") != "on" or form.get(f"maintenance_done_{key}") != "on":
                raise InspectionFormError("Bitte alle Prüf- und Wartungspositionen abschliessen, bevor der Bericht gesendet wird.")
            reports.append({"inspectionType": kind, "playdeviceFid": fid,
                            "inspectionText": criterion["check"],
                            "maintenanceText": criterion["maintenance"],
                            "fallProtectionType": criterion["fall"],
                            "inspectionDone": True, "maintenanceDone": True,
                            "inspectionComment": comment,
                            "maintenanceComment": maintenance_comment})
    if not reports:
        raise InspectionFormError("Keine Prüfkriterien vorhanden.")
    return reports
