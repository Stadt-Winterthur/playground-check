"""Read-only presentation of the two inspection histories, grouped by type."""
from datetime import date, datetime
from zoneinfo import ZoneInfo


def service_date(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return ''
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.astimezone(ZoneInfo('Europe/Zurich'))
    if not isinstance(value, date) or value.year == 1:
        return ''
    return value.strftime('%d.%m.%Y')


def history_groups(reports, inspection_types, current_type):
    # Include historical types even if they have since left the active catalog.
    kinds = list(dict.fromkeys([*inspection_types, *(r.get('inspectionType') or '' for r in reports)]))
    selected = current_type if current_type in kinds else next(iter(kinds), '')
    return [
        {'kind': kind, 'selected': kind == selected,
         'reports': [{**report, 'service_date_display': service_date(report.get('dateOfService'))}
                     for report in reports if (report.get('inspectionType') or '') == kind]}
        for kind in kinds
    ]
