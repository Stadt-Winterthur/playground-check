"""Pure, database-independent serializers for playground inspection and devices.

These are deliberately regular Python functions, not DRF serializers: they preserve
the legacy payload exactly while the HTTP/API migration is still in progress.
"""

from __future__ import annotations

from typing import Any, Mapping


def report_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tid": row.get("tid", -1), "inspectionType": row.get("inspection_type") or "",
        "dateOfService": row.get("inspection_date"), "inspector": row.get("inspector") or "",
        "inspectionText": row.get("inspection_text") or "", "inspectionDone": bool(row.get("inspection_done")),
        "inspectionComment": row.get("inspection_comment") or "", "maintenanceText": row.get("maintenance_text") or "",
        "maintenanceDone": bool(row.get("maintenance_done")), "maintenanceComment": row.get("maintenance_comment") or "",
        "fallProtectionType": row.get("fall_protection") or "", "playdeviceFid": row.get("playdevice_fid") or 0,
        "playdeviceDetailFid": row.get("playdevice_detail_fid") or 0,
        "tidInspection": row.get("inspection_tid") if row.get("inspection_tid") is not None else -1,
    }


def criterion_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "realm": row.get("realm") or "", "designation": "", "check": row.get("check_text") or "",
        "checkShortText": row.get("check_short_text") or "", "maintenance": row.get("maintenance") or "",
        "beforeOpening": False, "weekly": False, "monthly": False, "yearly": False,
        "inspectionType": row.get("inspection_type") or "",
        "currentInspectionReport": {
            "tid": 0, "inspectionType": "", "inspector": "", "inspectionText": "", "inspectionDone": False,
            "inspectionComment": "", "maintenanceText": "", "maintenanceDone": False,
            "maintenanceComment": "", "fallProtectionType": "", "playdeviceFid": 0, "playdeviceDetailFid": 0,
        },
    }

def playdevice_feature(
    row: Mapping[str, Any], *, general: list[dict[str, Any]], main: list[dict[str, Any]],
    secondary: list[dict[str, Any]], last: list[dict[str, Any]], previous: list[dict[str, Any]],
    defects: list[dict[str, Any]] | None, min_date: str,
) -> dict[str, Any]:
    """Build a device response from data already fetched by the repository layer."""
    return {
        "type": "Feature",
        "properties": {
            "fid": row["fid"], "supplier": row.get("supplier") or "", "material": "", "lebensdauer": 0,
            "comment": row.get("comment") or "",
            "type": {"name": row.get("type_name") or "", "description": row.get("type_description") or "", "standard": row.get("standard") or ""},
            "dateOfService": min_date, "constructionDate": row.get("construction_date") or min_date,
            "generalInspectionCriteria": general, "mainFallProtectionInspectionCriteria": main,
            "secondaryFallProtectionInspectionCriteria": secondary,
            "recommendedYearOfRenovation": row.get("recommended_year") or 0,
            "renovationType": row.get("renovation_type") or 0,
            "commentRecommendedYearOfRenovation": row.get("renovation_comment") or "",
            "notToBeChecked": bool(row.get("not_to_be_checked")), "cannotBeChecked": bool(row.get("cannot_be_checked")),
            "cannotBeCheckedReason": row.get("cannot_be_checked_reason") or "",
            "hasOpenDefects": bool(row.get("has_open_defects")), "defects": defects,
            "lastInspectionReports": last, "nextToLastInspectionReports": previous,
            "pictureBase64String": "", "mapImageBase64String": "",
        },
        "geometry": {"type": "Point", "coordinates": [row.get("x"), row.get("y")]},
    }
