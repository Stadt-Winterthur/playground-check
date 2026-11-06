"""Inspection UI application cases; rendering and external calls are explicit ports."""
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

from playground_check.playdevice_service import DeviceWriteError
from .inspection_forms import InspectionFormError, inspection_devices, bind_inspection_values, inspection_reports
from .localization import tr, language_for_request

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InspectionServices:
    assignments: Callable
    playground: Callable
    save_checkability: Callable
    submit_reports: Callable


def _load_context(request, user, services):
    source = request.POST if request.method == 'POST' else request.GET
    name = (source.get('name') or '').strip()[:200]
    kind = (source.get('inspectiontype') or '').strip()[:100]
    if not name or not kind:
        raise InspectionFormError('Spielplatz und Inspektionsart erforderlich.')
    try:
        permitted = services.assignments(user, {'inspectiontype': kind})
        if not any(x.get('name') == name and not x.get('inspectionSuspended') for x in permitted):
            raise InspectionFormError('Inspektion für diesen Spielplatz nicht freigegeben.', 403)
        payload = services.playground({'name': name, 'inspectiontype': kind,
                                      'withdefects': 'true', 'withinspections': 'true'})
    except InspectionFormError:
        raise
    except Exception as exc:
        LOGGER.exception('Failed to prepare inspection editor')
        raise InspectionFormError('Inspektion derzeit nicht verfügbar.', 503) from exc
    if payload.get('inspectionSuspended'):
        raise InspectionFormError('Inspektionen sind ausgesetzt.', 403)
    if kind not in (payload.get('inspectionTypeOptions') or []):
        raise InspectionFormError('Unbekannte Inspektionsart.')
    devices = inspection_devices(payload, kind, tr('Spielgerät', language_for_request(request, user)))
    selected = _selected_device(source, request.method)
    if selected and selected not in {str(d['fid']) for d in devices}:
        raise InspectionFormError('Spielgerät nicht gefunden.', 404)
    return {'name': name, 'kind': kind, 'devices': devices, 'private': True, 'user': user, 'selected_device': selected,
            'server_values': request.method == 'POST'}


def _selected_device(source, method):
    if method == 'POST':
        for field in ('save_checkability', 'navigation_device'):
            if field in source:
                return source.get(field, '')[:24]
    return (source.get('selected_device') or '')[:24]


def edit_inspection(request, user, services, render):
    if user.get('role') not in {'inspector', 'administrator'}:
        return render('error.html', {'message': 'Keine Berechtigung für Inspektionen.', 'private': True}, status=403)
    try:
        context = _load_context(request, user, services)
    except InspectionFormError as exc:
        return render('error.html', {'message': str(exc), 'private': True, 'user': user}, status=exc.status)
    if request.method == 'GET':
        return render('inspection_editor.html', context)
    bind_inspection_values(context['devices'], request.POST)
    if 'save_checkability' in request.POST:
        return _save_checkability(request.POST, context, services, render)
    if 'navigation_device' in request.POST:
        return render('inspection_editor.html', context)
    return _finish_inspection(request, context, services, render)


def _save_checkability(form, context, services, render):
    device = next((d for d in context['devices'] if str(d['fid']) == context['selected_device']), None)
    if not device or device['not_to_be_checked']:
        return render('error.html', {'message': 'Keine Berechtigung für Inspektionen.', 'private': True}, status=403)
    checked = form.get(f'cannotBeChecked_{device["fid"]}') == '1'
    reason = (form.get(f'cannotBeCheckedReason_{device["fid"]}') or '').strip()
    try:
        services.save_checkability({'fid': device['fid'], 'cannotBeChecked': checked, 'cannotBeCheckedReason': reason})
    except DeviceWriteError as exc:
        context['checkability_error'] = str(exc)
        device['cannot_be_checked'], device['cannot_reason'] = checked, reason
        return render('inspection_editor.html', context, status=exc.status)
    except Exception:
        LOGGER.exception('Could not save device checkability')
        context['checkability_error'] = 'Speichern fehlgeschlagen.'
        return render('inspection_editor.html', context, status=503)
    device['cannot_be_checked'], device['cannot_reason'] = checked, reason if checked else ''
    context['checkability_message'] = 'Prüfbarkeit gespeichert.'
    return render('inspection_editor.html', context)


def _finish_inspection(request, context, services, render):
    def failure(message):
        return render('inspection_editor.html', {**context, 'form_error': message})
    if os.environ.get('PLAYGROUND_UI_INSPECTION_WRITE_ENABLED', '').lower() != 'true':
        return failure('Die Übermittlung ist für diese Umgebung noch nicht freigeschaltet. Bitte die Administration kontaktieren.')
    if request.content_type != 'application/x-www-form-urlencoded':
        return failure('Das Formularformat wird nicht unterstützt. Bitte die Seite neu laden.')
    if int(request.META.get('CONTENT_LENGTH') or 0) > 2_000_000:
        return failure('Der Inspektionsbericht ist zu gross.')
    try:
        reports = inspection_reports(context['devices'], request.POST, context['kind'])
    except InspectionFormError as exc:
        return failure(str(exc))
    result = services.submit_reports(reports)
    try:
        data = json.loads(result.content)
    except (TypeError, ValueError):
        data = {}
    if result.status_code == 200 and isinstance(data, dict) and data.get('errorMessage') == '':
        return render('inspection_success.html', {'name': context['name'], 'kind': context['kind'], 'private': True})
    LOGGER.warning('Inspection was rejected with status %s', result.status_code)
    return failure(_submission_message(data))


def _submission_message(data):
    messages = {'SPK-2': 'Für diesen Spielplatz wurde heute bereits eine Inspektion dieser Art erfasst.',
                'SPK-11': 'Sie sind für diese Inspektion nicht berechtigt. Bitte die Zuweisung überprüfen.',
                'SPK-12': 'Ein Spielgerät konnte dem Spielplatz nicht zugeordnet werden.',
                'SPK-13': 'Geräte oder Prüfkriterien haben sich geändert oder sind unvollständig. Bitte den Bericht prüfen.',
                'SPK-3': 'Beim Speichern ist ein Server- oder Datenbankfehler aufgetreten. Bitte später erneut versuchen.'}
    code = data.get('errorMessage') if isinstance(data, dict) else None
    return messages.get(code, 'Der Inspektionsbericht konnte nicht gespeichert werden. Bitte die Angaben prüfen und erneut versuchen.')
