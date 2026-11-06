"""Shared device-write rules for HTML, DRF and compatibility entry points.

The caller owns authorization and the transaction. Existing Oracle FIDs are
required; this module never generates identifiers or commits independently.
"""
from collections.abc import Mapping

from .business_time import local_today
from . import playdevice_write_repository as repository

RENOVATION = {
    'recommendedYearOfRenovation': 'recommended_year',
    'renovationType': 'renovation_type',
    'commentRecommendedYearOfRenovation': 'renovation_comment',
}
CHECKABILITY = {
    'cannotBeChecked': 'cannot_be_checked',
    'cannotBeCheckedReason': 'cannot_be_checked_reason',
}


class DeviceWriteError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _integer(value, *, optional=False):
    if optional and value in (None, '', 0, '0') and not isinstance(value, bool):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DeviceWriteError('Ungültige Eingabe.')
    try:
        return int(value)
    except ValueError as exc:
        raise DeviceWriteError('Ungültige Eingabe.') from exc


def _text(value, limit):
    if value is None:
        return ''
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise DeviceWriteError('Kommentar zu lang.' if isinstance(value, str) else 'Ungültige Eingabe.')
    return value.strip()


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {'true', 'false', '1', '0'}:
        return value.strip().lower() in {'true', '1'}
    raise DeviceWriteError('Ungültige Eingabe.')


def save_device(db, properties):
    """Validate all requested changes before writing; preserve omitted fields.

    A row lock protects merges and the exemption check against concurrent saves.
    Partial renovation changes never implicitly reset checkability (or vice versa).
    """
    if not isinstance(properties, Mapping):
        raise DeviceWriteError('Ungültige Eingabe.')
    fid = _integer(properties.get('fid'))
    if not 0 < fid < 2**31:
        raise DeviceWriteError('Spielgeraet fehlt.')
    renovation = any(key in properties for key in RENOVATION)
    checkability = any(key in properties for key in CHECKABILITY)
    if not renovation and not checkability:
        raise DeviceWriteError('Ungültige Eingabe.')
    current = repository.device_for_update(db, fid)
    if current is None:
        raise DeviceWriteError('Spielgerät nicht gefunden.', 404)
    values = {'fid': fid}
    for api_key, column in {**RENOVATION, **CHECKABILITY}.items():
        values[api_key] = properties[api_key] if api_key in properties else current.get(column)

    if renovation:
        year = _integer(values['recommendedYearOfRenovation'], optional=True)
        if ('recommendedYearOfRenovation' in properties and year is not None
                and not local_today().year <= year <= 2200):
            raise DeviceWriteError('Ungueltiges Sanierungsjahr oder Sanierungsart.')
        kind = _integer(values['renovationType'], optional=True)
        if kind is not None and (kind <= 0 or not repository.renovation_type_exists(db, kind)):
            raise DeviceWriteError('Unbekannte Sanierungsart.')
        comment = _text(values['commentRecommendedYearOfRenovation'], 2000)
        values.update(recommendedYearOfRenovation=year, renovationType=kind,
                      commentRecommendedYearOfRenovation=comment)

    if checkability:
        if current.get('not_to_be_checked'):
            raise DeviceWriteError('Dieses Spielgerät ist von der Kontrolle ausgenommen.', 403)
        checked = _boolean(values['cannotBeChecked'] if values['cannotBeChecked'] is not None else False)
        reason = values['cannotBeCheckedReason'] or ''
        if checked and (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 255):
            raise DeviceWriteError('Begründung erforderlich (max. 255 Zeichen).')
        values.update(cannotBeChecked=checked, cannotBeCheckedReason=reason.strip() if checked else '')

    if renovation and checkability:
        affected = repository.update_playdevice(db, year, kind, comment or None,
                                                checked, values['cannotBeCheckedReason'], fid)
    elif renovation:
        affected = repository.update_renovation_only(db, year, kind, comment or None, fid)
    else:
        affected = repository.update_checkability_only(db, checked, values['cannotBeCheckedReason'], fid)
    if affected != 1:
        raise DeviceWriteError('Speichern fehlgeschlagen.', 409)
    return values
