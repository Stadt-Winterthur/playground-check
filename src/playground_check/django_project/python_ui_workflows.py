"""Native server-rendered GUI workflows. No extra SQL write layer.

All mutations are delegated to established domain commands, with identity
rechecked on every request. This module does not weaken API authorization.
"""
from __future__ import annotations

import base64
import json
import logging
from functools import wraps

from django.http import HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.test import RequestFactory
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from . import python_ui as ui
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
    # Forward only the validated auth cookie set by the existing login command.
    for key, cookie in answer.cookies.items():
        result.cookies[key] = cookie
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
@require_http_methods(['GET','POST'])
def device_editor(request):
    user, error = _guard(request)
    if error is not None: return error
    fields = [('fid','Spielgerät-FID','number'),('recommendedYearOfRenovation','Empfohlenes Sanierungsjahr','number'),
              ('renovationType','Sanierungsart-ID','number'),('commentRecommendedYearOfRenovation','Sanierungsbemerkung','textarea'),
              ('cannotBeChecked','Nicht prüfbar (1/0)','number'),('cannotBeCheckedReason','Begründung','text')]
    if request.method == 'GET': return _page(request, 'Spielgerät bearbeiten', fields, action='/__ui/device/edit/')
    failed = _check_post(request)
    if failed: return failed
    try: fid = int(request.POST.get('fid') or 0)
    except ValueError: fid = 0
    if fid <= 0: return ui._render(request, 'error.html', {'message':'Ungültige Spielgerät-FID.', 'private':True}, status=400)
    props = {'fid':fid, 'recommendedYearOfRenovation':request.POST.get('recommendedYearOfRenovation') or None,
             'renovationType':request.POST.get('renovationType') or None,
             'commentRecommendedYearOfRenovation':(request.POST.get('commentRecommendedYearOfRenovation') or '')[:2000],
             'cannotBeChecked': request.POST.get('cannotBeChecked') == '1',
             'cannotBeCheckedReason':(request.POST.get('cannotBeCheckedReason') or '')[:1000]}
    return _outcome(request, _native(request, inspection_device_commands.save_playdevice, {'properties':props}, url='/Playdevice/'), 'Spielgerät gespeichert.')


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
