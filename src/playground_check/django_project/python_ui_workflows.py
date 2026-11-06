"""Native server-rendered GUI workflows. No extra SQL write layer.

All mutations are delegated to established domain commands, with identity
rechecked on every request. This module does not weaken API authorization.
"""
from __future__ import annotations

import base64
import json
import logging
from http.cookies import CookieError, SimpleCookie
from functools import wraps

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from . import python_ui as ui
from playground_check.config import settings
from playground_check.business_time import local_today
from playground_check.playdevice_service import save_device, DeviceWriteError
from playground_check.remaining_reads_repository import renovation_options
from . import account_commands, defect_commands, inspection_device_commands, document_commands

LOG = logging.getLogger(__name__)
from .ui_command_adapter import invoke, invoke_upload
from playground_check.upload_limits import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES, UPLOAD_REQUEST_MAX_BYTES


def _page(request, title, fields, *, action, values=None, info='', status=200):
    return ui._render(request, 'workflow.html', {
        'title': title, 'fields': fields, 'action': ui._prefix(request) + action,
        'values': values or {}, 'info': info, 'private': True, 'user': getattr(request, '_ui_user', None),
            }, status=status)


def _guard(request, role=None):
    user, failure = ui._private(request)
    if failure is not None: return None, failure
    if role and user.get('role') not in role:
        return None, ui._render(request, 'error.html', {'message': 'Keine Berechtigung.', 'private': True}, status=403)
    return user, None


def _check_post(request, max_size=400000):
    # Form parsing may have consumed multipart form data. Accessing
    # request.body then raises RawPostDataException; use the HTTP length instead.
    try:
        length = int(request.META.get('CONTENT_LENGTH') or 0)
    except (TypeError, ValueError):
        length = -1
    if (request.content_type not in ('application/x-www-form-urlencoded', 'multipart/form-data')
            or length < 0 or length > max_size):
        return ui._render(request, 'error.html', {'message': 'Ungültige oder zu grosse Eingabe.', 'private': True}, status=400)
    return None


def _native(request, fn, payload, *, method='post', url='/', kwargs=None):
    return invoke(request, fn, payload, method=method, url=url, kwargs=kwargs)


def _outcome(request, response, success):
    try:
        data = json.loads(response.content)
    except (ValueError, TypeError):
        data = {}
    if response.status_code != 200 or (isinstance(data, dict) and data.get('errorMessage')):
        LOG.warning('GUI command rejected (HTTP %s)', response.status_code)
        return ui._render(request, 'error.html', {'message': 'Speichern nicht möglich. Bitte Eingaben und Berechtigung prüfen.', 'private': True}, status=413 if response.status_code == 413 else 400)
    return ui._render(request, 'workflow_success.html', {'message': success, 'private': True})


def _detail_redirect(request, name, kind='', *, notice='', error=''):
    params = {'name': (name or '')[:200], 'tab': 'documents'}
    if kind:
        params['inspectiontype'] = kind[:100]
    if notice:
        params['notice'] = notice[:180]
    if error:
        params['error'] = error[:180]
    response = HttpResponse(status=303)
    response['Location'] = ui._prefix(request) + '/detail/?' + urlencode(params) + '#documents'
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['GET','POST'])
def login(request):
    # Login intentionally public; all other GUI pages are strictly private.
    if request.method == 'GET':
        return ui._render(request, 'gui_login.html', {})
    failed = _check_post(request, 12000)
    if failed: return failed
    email = (request.POST.get('email') or '').strip()[:255]
    password = request.POST.get('password') or ''
    if not email or not password or len(password) > 1024:
        return ui._render(request, 'gui_login.html', {'error': 'Ungültige Anmeldedaten.', 'email': email}, status=400)
    answer = _native(request, account_commands.login, {'mailAddress': email, 'passPhrase': password}, url='/Account/Login/')
    if answer.status_code != 200:
        return ui._render(request, 'gui_login.html', {'error': 'Anmeldung fehlgeschlagen.', 'email': email}, status=401)
    next_url = ui._prefix(request) + '/'
    result = HttpResponseRedirect(next_url)
    # The existing account command returns Set-Cookie as an HTTP header.
    # Django's HttpResponse.cookies is NOT populated by response['Set-Cookie'].
    # Copy only the expected auth cookie; never forward unrelated headers/cookies.
    cookie_name = account_commands.service.settings.auth_cookie_name
    cookie = answer.cookies.get(cookie_name)
    if cookie is None:
        try:
            parsed = SimpleCookie()
            parsed.load(answer.get('Set-Cookie', ''))
            cookie = parsed.get(cookie_name)
        except CookieError:
            cookie = None
    if cookie is None or not cookie.value:
        LOG.error('Successful native login did not provide an auth cookie')
        return ui._render(request, 'error.html', {
            'message': 'Anmeldung technisch fehlgeschlagen. Bitte Administrator kontaktieren.',
        }, status=502)
    result.cookies[cookie_name] = cookie
    result['Cache-Control'] = 'no-store'
    return result


@require_http_methods(['POST'])
def logout(request):
    from playground_check.domain_support import _auth_cookie, revoke_request_session
    from playground_check.http import Request as LegacyRequest
    try:
        revoke_request_session(LegacyRequest(dict(request.META)))
    except Exception:
        return ui._render(request, 'error.html', {
            'message': 'Abmeldung derzeit nicht möglich. Bitte erneut versuchen.',
            'private': True,
        }, status=503)
    result = HttpResponseRedirect(ui._prefix(request) + '/login/')
    name, header = _auth_cookie('', clear=True)
    parsed = SimpleCookie()
    parsed.load(header)
    result.cookies[settings.auth_cookie_name] = parsed[settings.auth_cookie_name]
    from .localization import COOKIE
    result.delete_cookie(COOKIE, path=ui._prefix(request) + '/', samesite='Lax')
    result['Cache-Control'] = 'no-store'
    return result


@require_http_methods(['GET', 'POST'])
def defect_editor(request):
    """Create a defect in a validated device context, using named choices."""
    from playground_check import user_repository
    from playground_check.db import connect
    from playground_check.domain_support import playground_by_device_data

    user, error = _guard(request)
    if error is not None:
        return error
    source = request.POST if request.method == 'POST' else request.GET
    if source.get('tid'):
        try:
            tid = int(source['tid'])
            if tid <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return ui._render(request, 'error.html', {'message': 'Ungültige Mangelnummer.', 'private': True}, status=400)
        return HttpResponseRedirect(ui._prefix(request) + '/defect/?' + urlencode({'tid': tid}))
    try:
        fid = int(source.get('playdeviceFid') or 0)
        if not 0 < fid < 2**31:
            raise ValueError()
        playground = playground_by_device_data(fid)
        devices = playground.get('playdevices') or []
        device = next(d for d in devices if int((d.get('properties') or {}).get('fid') or d.get('fid') or 0) == fid)
        with connect() as db:
            users = [dict(row) for row in user_repository.assignable_users(db)]
    except (ValueError, TypeError, StopIteration, LookupError):
        return ui._render(request, 'error.html', {'message': 'Bitte ein gültiges Spielgerät auswählen.', 'private': True, 'user': user}, status=400)
    except Exception:
        LOG.exception('Defect device context unavailable')
        return ui._render(request, 'error.html', {'message': 'Gerätedaten derzeit nicht verfügbar.', 'private': True, 'user': user}, status=503)
    values = {key: source.get(key, '') for key in ('defectDescription', 'priority', 'defectsResponsibleBodyId', 'responsibleUserFid')}
    context = {'private': True, 'user': user, 'fid': fid, 'playground': playground,
               'device': device.get('properties') or {}, 'users': users, 'values': values}

    def form_error(message, status=400):
        return ui._render(request, 'defect_create.html', {**context, 'form_error': message}, status=status)

    if request.method == 'GET':
        return ui._render(request, 'defect_create.html', context)
    failed = _check_post(request, 20000)
    if failed is not None:
        return failed
    description = (source.get('defectDescription') or '').strip()
    try:
        priority = int(source.get('priority') or 0)
        body_id = int(source.get('defectsResponsibleBodyId') or -1)
        person_id = int(source.get('responsibleUserFid') or -1)
    except (ValueError, TypeError):
        return form_error('Bitte gültige Auswahlwerte verwenden.')
    if not description or len(description) > 255:
        return form_error('Beschreibung erforderlich (maximal 255 Zeichen).')
    if priority not in {0, 1, 2, 3} or body_id not in {-1, 1, 2, 3}:
        return form_error('Bitte Dringlichkeit und Zuständigkeit prüfen.')
    if person_id != -1 and not any(row['fid'] == person_id for row in users):
        return form_error('Die ausgewählte Person ist nicht zuweisbar.')
    if priority == 2 and (body_id < 1 or person_id < 1):
        return form_error('Bei Dringlichkeit B sind Zuständigkeit und Person erforderlich.')
    payload = {'playdeviceFid': fid, 'defectDescription': description, 'priority': priority,
               'defectsResponsibleBodyId': body_id, 'responsibleUserFid': person_id}
    response = _native(request, defect_commands.create_defect, payload, method='put', url='/Defect/')
    try:
        answer = json.loads(response.content)
    except (ValueError, TypeError):
        answer = {}
    if response.status_code != 200 or answer.get('errorMessage') or not answer.get('tid'):
        return form_error('Mangel konnte nicht gespeichert werden. Bitte Angaben prüfen.', 409)
    result = HttpResponse(status=303)
    result['Location'] = ui._prefix(request) + '/defect/?' + urlencode({'tid': answer['tid'], 'saved': 'save'})
    result['Cache-Control'] = 'no-store'
    return result


def _renovation_form(request, user, fid, props, *, saved=False, form_error="", status=200):
    from playground_check.db import connect
    try:
        with connect() as db:
            options = [dict(row) for row in renovation_options(db)]
    except Exception:
        LOG.exception('Could not load renovation options')
        return ui._render(request, 'error.html', {'message': 'Sanierungsarten derzeit nicht verfuegbar.', 'private': True}, status=503)
    return ui._render(request, 'device_renovation.html', {
        'fid': fid, 'properties': props, 'renovation_options': options, 'private': True, 'user': user,
        'minimum_year': local_today().year, 'saved': saved, 'form_error': form_error,
            }, status=status)


@require_http_methods(['GET', 'POST'])
def device_editor(request):
    """Edit only renovation fields; never touch inspection checkability columns."""
    user, error = _guard(request, {'inspector', 'administrator'})
    if error is not None: return error
    source = request.GET if request.method == 'GET' else request.POST
    try: fid = int(source.get('fid') or 0)
    except (ValueError, TypeError): fid = 0
    if not 0 < fid < 2**31:
        return ui._render(request, 'error.html', {'message': 'Spielgeraet fehlt.', 'private': True}, status=400)
    if request.method == 'GET':
        from playground_check.domain_support import playground_by_device_data
        try:
            result = playground_by_device_data(fid)
            features = result.get('playdevices') or []
            if not features:
                raise LookupError(fid)
            props = features[0].get('properties') or {}
        except Exception:
            LOG.exception('Could not load device renovation values')
            return ui._render(request, 'error.html', {'message': 'Spielgeraet nicht verfuegbar.', 'private': True}, status=404)
        return _renovation_form(request, user, fid, props)
    failed = _check_post(request)
    if failed is not None: return failed
    from playground_check.db import connect
    try:
        with connect() as db:
            values = save_device(db, {
                'fid': fid,
                'recommendedYearOfRenovation': (source.get('recommendedYearOfRenovation') or '').strip(),
                'renovationType': (source.get('renovationType') or '').strip(),
                'commentRecommendedYearOfRenovation': source.get('commentRecommendedYearOfRenovation') or '',
            })
    except DeviceWriteError as exc:
        # Keep user-editable fields in the original form, not on an error page.
        submitted = {key: source.get(key) or '' for key in
                     ('recommendedYearOfRenovation', 'renovationType', 'commentRecommendedYearOfRenovation')}
        return _renovation_form(request, user, fid, submitted, form_error=str(exc), status=exc.status)
    except Exception:
        LOG.exception('Renovation update failed')
        submitted = {key: source.get(key) or '' for key in
                     ('recommendedYearOfRenovation', 'renovationType', 'commentRecommendedYearOfRenovation')}
        return _renovation_form(request, user, fid, submitted,
                                form_error='Speichern fehlgeschlagen.', status=503)

    return _renovation_form(request, user, fid, values, saved=True)


@require_http_methods(['GET', 'POST'])
def device_checkability(request):
    """Inspection-context editor, updating only checkability fields."""
    user, error = _guard(request, {'inspector', 'administrator'})
    if error is not None: return error
    source = request.GET if request.method == 'GET' else request.POST
    try: fid = int(source.get('fid') or 0)
    except (ValueError, TypeError): fid = 0
    if not 0 < fid < 2**31:
        return ui._render(request, 'error.html', {'message': 'Spielgeraet fehlt.', 'private': True}, status=400)
    if request.method == 'GET':
        from playground_check.domain_support import playground_by_device_data
        try:
            result = playground_by_device_data(fid)
            features = result.get('playdevices') or []
            if not features:
                raise LookupError(fid)
            props = features[0].get('properties') or {}
        except Exception:
            LOG.exception('Could not load device checkability values')
            return ui._render(request, 'error.html', {'message': 'Spielgeraet nicht verfuegbar.', 'private': True}, status=404)
        return ui._render(request, 'device_checkability.html', {
            'fid': fid, 'properties': props, 'private': True, 'user': user,
                        'name': (source.get('name') or '')[:200],
            'kind': (source.get('inspectiontype') or '')[:100],
        })
    failed = _check_post(request)
    if failed is not None: return failed
    checked = request.POST.get('cannotBeChecked') == '1'
    reason = (request.POST.get('cannotBeCheckedReason') or '').strip()
    from playground_check.db import connect
    try:
        with connect() as db:
            save_device(db, {'fid': fid, 'cannotBeChecked': checked, 'cannotBeCheckedReason': reason})
    except Exception as exc:
        if not isinstance(exc, DeviceWriteError):
            LOG.exception('Checkability update failed')
        message = str(exc) if isinstance(exc, DeviceWriteError) else 'Speichern fehlgeschlagen.'
        status = exc.status if isinstance(exc, DeviceWriteError) else 503
        return ui._render(request, 'device_checkability.html', {
            'fid': fid, 'properties': {'cannotBeChecked': checked, 'cannotBeCheckedReason': reason},
            'private': True, 'user': user, 'form_error': message,
            'server_failure': status >= 500,
            'name': (source.get('name') or '')[:200],
            'kind': (source.get('inspectiontype') or '')[:100],
        }, status=status)
    name = (source.get('name') or '').strip()[:200]
    kind = (source.get('inspectiontype') or '').strip()[:100]
    if name and kind:
        result = HttpResponse(status=303)
        result['Location'] = ui._prefix(request) + '/inspection/?' + urlencode({'name': name, 'inspectiontype': kind, 'selected_device': fid})
        result['Cache-Control'] = 'no-store'
        return result
    return ui._render(request, 'workflow_success.html', {'message': 'Prüfbarkeit gespeichert.', 'private': True, 'user': user})


@require_http_methods(['GET','POST'])
def document_editor(request):
    user, error = _guard(request, {'administrator'})
    if error is not None: return error
    fields = [('playgroundId','Spielplatz-FID','number'),('type','Dokumenttyp (Abnahme / Zertifikat)','text'),
              ('name','Dokumentname','text'),('document','PDF-Datei','file')]
    if request.method == 'GET': return _page(request, 'PDF hochladen', fields, action='/document/upload/')
    failed = _check_post(request, UPLOAD_REQUEST_MAX_BYTES)
    if failed: return failed
    uploaded = request.FILES.get('document')
    try: playground_id = int(request.POST.get('playgroundId') or 0)
    except ValueError: playground_id = 0
    payload = {'playgroundId': playground_id, 'type': request.POST.get('type', '')[:50],
               'name': request.POST.get('name', '')[:255]}
    response = invoke_upload(request, document_commands.create_document, payload,
                             {'document': uploaded}, url='/Document/')
    try:
        outcome = json.loads(response.content)
    except (ValueError, TypeError):
        outcome = {}
    if response.status_code != 200 or (isinstance(outcome, dict) and outcome.get('errorMessage')):
        LOG.warning('Document GUI upload failed: http_status=%s', response.status_code)
        return _page(request, 'PDF hochladen', fields, action='/document/upload/',
                     values={key: request.POST.get(key, '') for key in ('playgroundId', 'type', 'name')},
                     info='Dokument konnte nicht hochgeladen werden. Bitte Angaben prüfen und Datei erneut auswählen.',
                     status=response.status_code if response.status_code in (400, 409, 413, 503) else 400)
    return _outcome(request, response, 'Dokument hochgeladen.')


@require_http_methods(['POST'])
def playground_document_action(request):
    user, error = _guard(request, {'administrator'})
    if error is not None: return error
    failed = _check_post(request, UPLOAD_REQUEST_MAX_BYTES)
    if failed is not None: return failed
    name = (request.POST.get('name') or '').strip()[:200]
    kind = (request.POST.get('inspectiontype') or '').strip()[:100]
    if not name:
        return ui._render(request, 'error.html', {'message': 'Spielplatzname fehlt.', 'private': True}, status=400)
    action = (request.POST.get('action') or '').strip().lower()
    document_type = (request.POST.get('documentType') or '').strip().lower()
    if document_type not in {'abnahme', 'zertifikat'}:
        return _detail_redirect(request, name, kind, error='Ungültiger Dokumenttyp.')
    if action == 'upload':
        uploaded = request.FILES.get('document')
        if uploaded is None:
            return _detail_redirect(request, name, kind, error='PDF fehlt oder ist zu gross.')
        if uploaded.size > DOCUMENT_MAX_BYTES:
            return ui._render(request, 'error.html', {'message': 'PDF fehlt oder ist zu gross.', 'private': True}, status=413)
        try:
            playground_id = int(request.POST.get('playgroundId') or 0)
        except ValueError:
            playground_id = 0
        doc_name = (request.POST.get('documentName') or '').strip()[:255]
        if not doc_name:
            doc_name = (uploaded.name or 'Dokument').rsplit('.', 1)[0][:255]
        payload = {
            'playgroundId': playground_id,
            'type': document_type,
            'name': doc_name,
        }
        response = invoke_upload(request, document_commands.create_document, payload,
                                 {'document': uploaded}, url='/Document/')
        if response.status_code == 413:
            return ui._render(request, 'error.html', {'message': 'PDF fehlt oder ist zu gross.', 'private': True}, status=413)
        try:
            data = json.loads(response.content)
        except (ValueError, TypeError):
            data = {}
        if response.status_code != 200 or (isinstance(data, dict) and data.get('errorMessage')):
            return _detail_redirect(request, name, kind, error=(data.get('errorMessage') if isinstance(data, dict) else '') or 'Dokument konnte nicht gespeichert werden.')
        return _detail_redirect(request, name, kind, notice='Dokument erfolgreich hochgeladen.')
    try:
        document_fid = int(request.POST.get('documentFid') or 0)
    except ValueError:
        document_fid = 0
    if document_fid <= 0:
        return _detail_redirect(request, name, kind, error='Ungültige Dokument-ID.')
    if action == 'rename':
        doc_name = (request.POST.get('documentName') or '').strip()[:255]
        response = _native(request, document_commands.rename_document,
                           {'name': doc_name}, url=f'/Document/{document_fid}/Name/?type={document_type}',
                           kwargs={'fid': document_fid})
        try:
            data = json.loads(response.content)
        except (ValueError, TypeError):
            data = {}
        if response.status_code != 200 or (isinstance(data, dict) and data.get('errorMessage')):
            return _detail_redirect(request, name, kind, error=(data.get('errorMessage') if isinstance(data, dict) else '') or 'Dokumentname konnte nicht gespeichert werden.')
        return _detail_redirect(request, name, kind, notice='Dokumentname gespeichert.')
    if action == 'delete':
        response = _native(request, document_commands.delete_document, {}, method='delete',
                           url=f'/Document/{document_fid}/?type={document_type}', kwargs={'fid': document_fid})
        try:
            data = json.loads(response.content)
        except (ValueError, TypeError):
            data = {}
        if response.status_code != 200 or (isinstance(data, dict) and data.get('errorMessage')):
            return _detail_redirect(request, name, kind, error=(data.get('errorMessage') if isinstance(data, dict) else '') or 'Dokument konnte nicht gelöscht werden.')
        return _detail_redirect(request, name, kind, notice='Dokument gelöscht.')
    return _detail_redirect(request, name, kind, error='Unbekannte Dokumentaktion.')


@require_http_methods(['GET', 'POST'])
def admin_users(request):
    """Administrator-only native user overview and edit flow."""
    from playground_check.db import connect
    from playground_check import user_repository, domain_support

    user, error = _guard(request, {'administrator'})
    if error is not None:
        return error
    prefix = ui._prefix(request)
    email = ((request.POST if request.method == 'POST' else request.GET).get('email') or '').strip().lower()[:255]
    show_inactive = request.GET.get('inactive') == '1'
    query = (request.GET.get('q') or '').strip()[:100]
    message = ''
    form_error = ''
    status = 200

    if request.method == 'POST':
        failed = _check_post(request, 20000)
        if failed is not None:
            return failed
        if not email or '@' not in email or len(email) > 255:
            form_error = 'Bitte eine gültige E-Mail-Adresse wählen.'
        else:
            role = (request.POST.get('role') or '').strip()
            responsibility = (request.POST.get('responsibility') or '').strip()
            first_name = (request.POST.get('firstName') or '').strip()[:100]
            last_name = (request.POST.get('lastName') or '').strip()[:100]
            if (role not in domain_support.VALID_ROLES
                    or responsibility and responsibility not in domain_support.VALID_RESPONSIBILITIES
                    or not first_name or not last_name):
                form_error = 'Bitte Name, Rolle und Zuständigkeit prüfen.'
            else:
                payload = {
                    'mailAddress': email, 'firstName': first_name, 'lastName': last_name,
                    'role': role, 'responsibility': responsibility,
                    'active': request.POST.get('active') == 'on',
                    'isNew': request.POST.get('isNew') == '1',
                }
                answer = _native(request, account_commands.update_user, payload,
                                 method='put', url='/Account/Users/')
                try:
                    outcome = json.loads(answer.content)
                except (ValueError, TypeError):
                    outcome = {}
                if (answer.status_code != 200 or not isinstance(outcome, dict)
                        or outcome.get('errorMessage')):
                    form_error = 'Benutzer konnte nicht gespeichert werden. Berechtigungen und Eingaben prüfen.'
                else:
                    return HttpResponseRedirect(prefix + '/admin/users/?saved=1')
        status = 400 if form_error else 200

    try:
        with connect() as db:
            records = [dict(row) for row in user_repository.users(db)]
    except Exception:
        LOG.exception('User administration list unavailable')
        return ui._render(request, 'error.html', {
            'message': 'Benutzeradministration vorübergehend nicht verfügbar.',
            'private': True, 'user': user}, status=503)

    selected = next((row for row in records if row.get('email') == email), None) if email else None
    if email and selected is None:
        form_error = 'Benutzer wurde nicht gefunden.'
        status = 404
    visible = [row for row in records
               if (show_inactive or row.get('active'))
               and (not query or query.casefold() in ' '.join(str(row.get(k) or '') for k in
                    ('first_name', 'last_name', 'email', 'role', 'responsibility')).casefold())]
    roles = [('administrator', 'Administrator'), ('inspector', 'Kontrolleur'),
             ('maintenance', 'Unterhalt')]
    return ui._render(request, 'admin_users.html', {
        'private': True, 'user': user, 'rows': visible, 'selected': selected,
        'edit_email': email, 'show_inactive': show_inactive, 'query': query,
        'roles': roles, 'responsibilities': sorted(domain_support.VALID_RESPONSIBILITIES),
        'form_error': form_error,
        'saved': request.GET.get('saved') == '1', 'total': len(records),
    }, status=status)


@require_http_methods(['GET', 'POST'])
def playdevice_photo(request):
    """Upload a device image through the validated native picture command."""
    user, error = _guard(request, {'inspector', 'administrator'})
    if error is not None: return error
    source = request.GET if request.method == 'GET' else request.POST
    try: selected_fid = int(source.get('fid') or 0)
    except (ValueError, TypeError): selected_fid = 0
    if not 0 < selected_fid < 2**31:
        return ui._render(request, 'error.html', {'message': 'Kein Spielgeraet ausgewaehlt.', 'private': True}, status=400)
    if request.method == 'GET':
        return ui._render(request, 'device_photo.html', {
            'fid': selected_fid, 'private': True, 'user': user,
                        'name': (source.get('name') or '').strip()[:200],
            'kind': (source.get('inspectiontype') or '').strip()[:100],
        })
    failure = _check_post(request, UPLOAD_REQUEST_MAX_BYTES)
    if failure is not None: return failure
    try: fid = int(request.POST.get('fid') or '0')
    except ValueError: fid = 0
    if not 0 < fid < 2**31:
        return ui._render(request, 'error.html', {'message': 'Ungültige FID.', 'private': True}, status=400)
    uploaded = request.FILES.get('picture')
    if not uploaded:
        return ui._render(request, 'error.html', {'message': 'Bild fehlt oder ist zu gross.', 'private': True}, status=400)
    if uploaded.size > IMAGE_MAX_BYTES:
        return ui._render(request, 'error.html', {'message': 'Bild fehlt oder ist zu gross.', 'private': True}, status=413)
    signature = uploaded.read(16)
    uploaded.seek(0)
    if not signature.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
        return ui._render(request, 'error.html', {'message': 'Nur PNG- und JPEG-Bilder erlaubt.', 'private': True}, status=400)
    response = invoke_upload(request, inspection_device_commands.exchange_playdevice_picture,
                             {}, {'picture': uploaded}, method='PUT', url=f'/Playdevice/?fid={fid}')
    # Native picture command reads fid from the query string.
    try:
        answer = json.loads(response.content)
    except (ValueError, TypeError):
        answer = {}
    if response.status_code != 200 or (isinstance(answer, dict) and answer.get('errorMessage')):
        return _outcome(request, response, 'Bild aktualisiert.')
    # Post/Redirect/Get: refreshing the picture editor never repeats a photo upload.
    name = (request.POST.get('name') or '').strip()[:200]
    kind = (request.POST.get('inspectiontype') or '').strip()[:100]
    target = '/detail/' if name else '/assigned/'
    query = ('?' + urlencode({'name': name, 'inspectiontype': kind})) if name else ''
    redirect = HttpResponse(status=303)
    redirect['Location'] = ui._prefix(request) + target + query
    redirect['Cache-Control'] = 'no-store'
    return redirect


@require_http_methods(['GET'])
def playdevice_map(request):
    user, error = _guard(request)
    if error is not None: return error
    try:
        x, y = float(request.GET.get('x') or 0), float(request.GET.get('y') or 0)
        if not (2_400_000 <= x <= 2_900_000 and 1_000_000 <= y <= 1_400_000):
            return HttpResponse('Ungueltige Koordinaten.', status=400)
    except (TypeError, ValueError):
        return HttpResponse('Ungueltige Koordinaten.', status=400)
    try:
        from playground_check.map_image_queries import map_image_base64
        # The TEST WMS often responds with 403 HTML. Prefer the configured service,
        # but retry once against the established Stadtplan WMS when it fails.
        # This changes no API endpoint or frontend framework.
        canonical = 'https://stadtplan.winterthur.ch/wms/Spielplatzkarte'
        endpoints = [None]
        if settings.wms_url.rstrip('/').lower() != canonical.lower():
            endpoints.append(canonical)
        last_error = None
        for endpoint in endpoints:
            try:
                kwargs = {'endpoint_override': endpoint} if endpoint else {}
                decoded = base64.b64decode(map_image_base64({'x': str(x), 'y': str(y)}, **kwargs), validate=True)
                if len(decoded) > 5_000_000:
                    raise ValueError('oversized upstream image')
                if decoded.startswith(b'\x89PNG\r\n\x1a\n'):
                    mime = 'image/png'
                elif decoded.startswith(b'\xff\xd8\xff'):
                    mime = 'image/jpeg'
                else:
                    raise ValueError('non-image upstream response (WMS error or access denied)')
                break
            except Exception as exc:
                last_error = exc
                LOG.warning('WMS request failed for %s: %s', endpoint or 'configured endpoint', type(exc).__name__)
        else:
            raise ValueError('No usable WMS image received') from last_error
    except Exception:
        LOG.warning('WMS upstream failed (check PLAYGROUND_WMS_URL and WMS access)', exc_info=True)
        return HttpResponse('Kartendienst derzeit nicht verfuegbar.', status=502)
    response = HttpResponse(decoded, content_type=mime)
    response['Cache-Control'] = 'private, max-age=120'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
