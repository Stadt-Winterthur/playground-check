"""Pure transformations for playground read APIs, independent of HTTP and SQL."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping


def _date_value(value: Any) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return date.fromisoformat(text[:10])


def inspection_suspended(row: Mapping[str, Any]) -> bool:
    today = date.today()
    start = _date_value(row.get("suspend_from"))
    end = _date_value(row.get("suspend_to"))
    start_date = start.date() if isinstance(start, datetime) else start
    end_date = end.date() if isinstance(end, datetime) else end
    if start_date is None and end_date is None:
        return False
    if start_date is None:
        return today <= end_date
    if end_date is None:
        return today >= start_date
    return start_date <= today <= end_date



def public_feature(row: Mapping[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    row = row or {}
    coordinates = [] if row.get("x") is None else [row["x"], row["y"]]
    return {
        "type": "Feature",
        "properties": {
            "uuid": str(row.get("uuid") or ""), "nummer": row.get("number") if row.get("number") is not None else -1,
            "name": row.get("name") or "", "streetName": row.get("street_name") or "", "houseNo": row.get("house_no") or "",
        },
        "geometry": {"type": "Point", "coordinates": coordinates},
        "errorMessage": error,
    }


