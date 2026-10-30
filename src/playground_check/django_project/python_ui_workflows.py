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
from django.middleware.csrf import get_token
from django.test import RequestFactory
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from . import python_ui as ui
from playground_check.config import settings
from . import account_commands, defect_commands, inspection_device_commands, document_commands

LOG = logging.getLogger(__name__)
RF = RequestFactory()


def _page(request, title, fields, *, action, values=None, info='', status=200):
    return ui._render(request, 'workflow.html', {
        'title': title, 'fields': fields, 'action': ui._prefix(request) + action,
        'values': values or {}, 'info': info, 'private': True,
        'csrf_token_value': get_token(request),
    }, status=status)


def _guard(request, role=None):
    user, failure = ui._private(request)
    if failure is not None: return None, failure
    if role and user.get('role') not in role:
        return None, ui._render(request, 'error.html', {'message': 'Keine Berechtigung.', 'private': True}, status=403)
    return user, None


def _check_post(request, max_size=400000):
    if request.content_type not in ('application/x-www-form-urlencoded', 'multipart/form-data') or len(request.body) > max_size:
        return ui._render(request, 'error.html', {'message': 'Ungültige oder zu grosse Eingabe.', 'private': True}, status=400)
    return None


def _native(request, fn, payload, *, method='post', url='/', kwargs=None):
    headers = {k: v for k,v in request.META.items() if k.startswith('HTTP_') and k not in ('HTTP_CONTENT_LENGTH','HTTP_CONTENT_TYPE','HTTP_X_CSRFTOKEN')}
    downstream = getattr(RF, method.lower())(url, data=json.dumps(payload), content_type='application/json', **headers)
    return fn(downstream, **(kwargs or {}))


def _outcome(request, response, success):
    try:
        data = json.loads(response.content)
    except (ValueError, TypeError):
        data = {}
    if response.status_code != 200 or (isinstance(data, dict) and data.get('errorMessage')):
        LOG.warning('GUI command rejected (HTTP %s)', response.status_code)
        return ui._render(request, 'error.html', {'message': 'Speichern nicht möglich. Bitte Eingaben und Berechtigung prüfen.', 'private': True}, status=400)
    return ui._render(request, 'workflow_success.html', {'message': success, 'private': True})


@csrf_protect
@require_http_methods(['GET','POST'])
def login(request):
    # Login intentionally public; all other GUI pages are strictly private.
    if request.method == 'GET':
        return ui._render(request, 'gui_login.html', {'csrf_token_value': get_token(request)})
    failed = _check_post(request, 12000)
    if failed: return failed
    email = (request.POST.get('email') or '').strip()[:255]
    password = request.POST.get('password') or ''
    if not email or not password or len(password) > 1024:
        return ui._render(request, 'gui_login.html', {'csrf_token_value': get_token(request), 'error': 'Ungültige Anmeldedaten.'}, status=400)
    answer = _native(request, account_commands.login, {'mailAddress': email, 'passPhrase': password}, url='/Account/Login/')
    if answer.status_code != 200:
        return ui._render(request, 'gui_login.html', {'csrf_token_value': get_token(request), 'error': 'Anmeldung fehlgeschlagen.'}, status=401)
    next_url = ui._prefix(request) + '/__ui/workspace/'
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


@csrf_protect
@require_http_methods(['GET','POST'])
def defect_editor(request):
    user, error = _guard(request)
    if error is not None: return error
    fields = [('tid','Mangel-TID (bei bestehendem Mangel)','number'),('playdeviceFid','Spielgerät-FID','number'),
              ('defectDescription','Beschreibung','textarea'), ('priority','Priorität','number'),
              ('responsibleBody','Zuständige Stelle (ID)','number'), ('responsibleUser','Zuständige Person (FID)','number')]
    if request.method == 'GET': return _page(request, 'Mangel erfassen / bearbeiten', fields, action='/__ui/defect/edit/')
    failed = _check_post(request)
    if failed: return failed
    description = (request.POST.get('defectDescription') or '').strip()
    if not description or len(description) > 4000:
        return _page(request, 'Mangel erfassen / bearbeiten', fields, action='/__ui/defect/edit/', info='Beschreibung erforderlich (max. 4000 Zeichen).', status=400)
    payload = {'defectDescription': description}
    for key in ('tid','playdeviceFid','priority','responsibleBody','responsibleUser'):
        value = request.POST.get(key)
        if value:
            try: payload[key] = int(value)
            except ValueError: return ui._render(request, 'error.html', {'message':'Ungültiger Zahlenwert.', 'private':True}, status=400)
    if payload.get('tid'):
        result = _native(request, defect_commands.update_defect, payload, url='/Defect/')
    else:
        if not payload.get('playdeviceFid'):
            return ui._render(request, 'error.html', {'message':'Spielgerät-FID fehlt.', 'private':True}, status=400)
        result = _native(request, defect_commands.create_defect, payload, method='put', url='/Defect/')
    return _outcome(request, result, 'Mangel verarbeitet.')


@csrf_protect
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
            from playground_check.db import connect
            with connect() as db:
                renovation_options = [dict(row) for row in db.execute(
                    'SELECT id, value FROM "wgr_sp_sanierungsart_tbd" ORDER BY value').fetchall()]
        except Exception:
            LOG.exception('Could not load device renovation values')
            return ui._render(request, 'error.html', {'message': 'Spielgeraet nicht verfuegbar.', 'private': True}, status=404)
        return ui._render(request, 'device_renovation.html', {
            'fid': fid, 'properties': props, 'renovation_options': renovation_options, 'private': True, 'user': user,
            'csrf_token_value': get_token(request),
        })
    failed = _check_post(request)
    if failed is not None: return failed
    try:
        year_text = (request.POST.get('recommendedYearOfRenovation') or '').strip()
        type_text = (request.POST.get('renovationType') or '').strip()
        year = int(year_text) if year_text else None
        renovation_type = int(type_text) if type_text else None
        if year is not None and not 1900 <= year <= 2200: raise ValueError()
        if renovation_type is not None and renovation_type <= 0: raise ValueError()
    except ValueError:
        return ui._render(request, 'error.html', {'message': 'Ungueltiges Sanierungsjahr oder Sanierungsart.', 'private': True}, status=400)
    if renovation_type is not None:
        from playground_check.db import connect
        try:
            with connect() as db:
                known = db.execute('SELECT id FROM "wgr_sp_sanierungsart_tbd" WHERE id=%s',
                                   (renovation_type,)).fetchone()
            if not known:
                return ui._render(request, 'error.html', {'message': 'Unbekannte Sanierungsart.', 'private': True}, status=400)
        except Exception:
            LOG.exception('Renovation type lookup failed')
            return ui._render(request, 'error.html', {'message': 'Sanierungsarten derzeit nicht verfuegbar.', 'private': True}, status=503)
    comment = (request.POST.get('commentRecommendedYearOfRenovation') or '').strip()
    if len(comment) > 2000:
        return ui._render(request, 'error.html', {'message': 'Kommentar zu lang.', 'private': True}, status=400)
    from playground_check.playdevice_write_repository import update_renovation_only
    from playground_check.db import connect
    try:
        with connect() as db:
            update_renovation_only(db, year, renovation_type, comment or None, fid)
    except Exception:
        LOG.exception('Renovation update failed')
        return ui._render(request, 'error.html', {'message': 'Speichern fehlgeschlagen.', 'private': True}, status=503)
    return ui._render(request, 'workflow_success.html', {'message': 'Sanierungsangaben gespeichert; Kontrollstatus unveraendert.', 'private': True})


@csrf_protect
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
            'csrf_token_value': get_token(request),
            'name': (source.get('name') or '')[:200],
            'kind': (source.get('inspectiontype') or '')[:100],
        })
    failed = _check_post(request)
    if failed is not None: return failed
    checked = request.POST.get('cannotBeChecked') == '1'
    reason = (request.POST.get('cannotBeCheckedReason') or '').strip()
    if checked and (not reason or len(reason) > 255):
        return ui._render(request, 'error.html', {'message': 'Begruendung erforderlich (max. 255 Zeichen).', 'private': True}, status=400)
    from playground_check.playdevice_write_repository import update_checkability_only
    from playground_check.db import connect
    try:
        with connect() as db:
            update_checkability_only(db, checked, reason if checked else '', fid)
    except Exception:
        LOG.exception('Checkability update failed')
        return ui._render(request, 'error.html', {'message': 'Speichern fehlgeschlagen.', 'private': True}, status=503)
    return ui._render(request, 'workflow_success.html', {'message': 'Pruefbarkeit gespeichert; Sanierungsangaben unveraendert.', 'private': True})


@csrf_protect
@require_http_methods(['GET','POST'])
def document_editor(request):
    user, error = _guard(request, {'administrator'})
    if error is not None: return error
    fields = [('playgroundId','Spielplatz-FID','number'),('type','Dokumenttyp (Abnahme / Zertifikat)','text'),
              ('name','Dokumentname','text'),('document','PDF-Datei','file')]
    if request.method == 'GET': return _page(request, 'PDF hochladen', fields, action='/__ui/document/upload/')
    failed = _check_post(request, 22000000)
    if failed: return failed
    uploaded = request.FILES.get('document')
    if not uploaded or uploaded.size > 20_000_000:
        return ui._render(request, 'error.html', {'message':'PDF fehlt oder ist zu gross.', 'private':True}, status=400)
    content = uploaded.read()
    if not content.startswith(b'%PDF-'):
        return ui._render(request, 'error.html', {'message':'Nur PDF-Dateien erlaubt.', 'private':True}, status=400)
    try: playground_id = int(request.POST.get('playgroundId') or 0)
    except ValueError: playground_id = 0
    payload = {'playgroundId':playground_id,'type':request.POST.get('type','')[:50],
               'name':request.POST.get('name','')[:255], 'contentBase64':base64.b64encode(content).decode('ascii')}
    return _outcome(request, _native(request, document_commands.create_document, payload, url='/Document/'), 'Dokument hochgeladen.')


@csrf_protect
@require_http_methods(['GET','POST'])
def admin_users(request):
    user, error = _guard(request, {'administrator'})
    if error is not None: return error
    fields = [('mailAddress','E-Mail-Adresse','email'),('firstName','Vorname','text'),('lastName','Nachname','text'),
              ('role','Rolle','text'),('active','Aktiv (1/0)','number')]
    if request.method == 'GET': return _page(request, 'Benutzer verwalten', fields, action='/__ui/admin/users/')
    failed = _check_post(request)
    if failed: return failed
    email = (request.POST.get('mailAddress') or '').strip().lower()
    if '@' not in email or len(email)>255:
        return ui._render(request, 'error.html', {'message':'Ungültige E-Mail.', 'private':True}, status=400)
    payload = {'mailAddress':email,'firstName':request.POST.get('firstName','')[:100],
               'lastName':request.POST.get('lastName','')[:100],'role':request.POST.get('role','')[:40],
               'active':request.POST.get('active')=='1'}
    return _outcome(request, _native(request, account_commands.update_user, payload, method='put', url='/Account/Users/'), 'Benutzeränderung verarbeitet.')


@csrf_protect
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
            'csrf_token_value': get_token(request),
            'name': (source.get('name') or '').strip()[:200],
            'kind': (source.get('inspectiontype') or '').strip()[:100],
        })
    failure = _check_post(request, 8_000_000)
    if failure is not None: return failure
    try: fid = int(request.POST.get('fid') or '0')
    except ValueError: fid = 0
    if not 0 < fid < 2**31:
        return ui._render(request, 'error.html', {'message': 'Ungültige FID.', 'private': True}, status=400)
    uploaded = request.FILES.get('picture')
    if not uploaded or uploaded.size > 5_000_000:
        return ui._render(request, 'error.html', {'message': 'Bild fehlt oder ist zu gross.', 'private': True}, status=400)
    raw = uploaded.read()
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif raw.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    else:
        return ui._render(request, 'error.html', {'message': 'Nur PNG- und JPEG-Bilder erlaubt.', 'private': True}, status=400)
    image_data = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')
    response = _native(request, inspection_device_commands.exchange_playdevice_picture,
                       {'data': image_data}, method='put', url=f'/Playdevice/?fid={fid}',
                       )
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
    target = '/__ui/detail/' if name else '/__ui/assigned/'
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
