"""Public registration and password recovery, with mandatory admin approval.

Opaque, short-lived, single-use tokens. No Django auth schema or login session is
created by these flows. All account writes use the existing PostgreSQL identity.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from email.message import EmailMessage
from urllib.parse import urlsplit

from django.http import HttpResponseRedirect
from django.views.decorators.http import require_http_methods

from playground_check import auth, user_repository, user_write_repository
from playground_check.config import settings
from playground_check.db import connect
from playground_check.mail_service import deliver
from . import python_ui as ui

LOG = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PURPOSES = frozenset({'register', 'reset'})
GENERIC = 'Falls die Angaben zu einem Konto passen, erhalten Sie eine E-Mail mit den nächsten Schritten.'


def _response(request, mode, *, error='', message='', email='', token='', status=200):
    response = ui._render(request, 'account_recovery.html', {
        'mode': mode, 'error': error, 'message': message, 'email': email,
        'token': token, 'recovery_public': True,
    }, status=status)
    if mode == 'set':
        response['Referrer-Policy'] = 'no-referrer'
    return response


def _post_ok(request):
    try:
        size = int(request.META.get('CONTENT_LENGTH') or 0)
    except (ValueError, TypeError):
        return False
    return (request.content_type == 'application/x-www-form-urlencoded'
            and 0 <= size <= 12000)


def _canonical_email(value):
    email = str(value or '').strip().lower()
    return email if len(email) <= 80 and EMAIL_RE.fullmatch(email) else None


def _hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def _ip_fingerprint(request):
    # Never trust client-controlled X-Forwarded-For for security throttling.
    address = str(request.META.get('REMOTE_ADDR') or 'unknown')[:128]
    return hmac.new(settings.security_key.encode(), address.encode(), hashlib.sha256).hexdigest()


def _origin():
    # Do not build reset links from the untrusted HTTP Host header.
    value = (os.getenv('PLAYGROUND_ACCOUNT_LINK_BASE_URL') or '').rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.hostname in {'localhost', '127.0.0.1'}):
        raise ValueError('PLAYGROUND_ACCOUNT_LINK_BASE_URL must be the public HTTPS app URL')
    return value


def _send(email, purpose, token):
    url = f'{_origin()}/password/set/{token}/'
    mail = EmailMessage()
    mail['From'] = (os.getenv('SMTP_FROM') or '').strip()
    mail['To'] = email
    mail['Subject'] = ('Spielplatzkontrolle: Registrierung abschliessen' if purpose == 'register'
                       else 'Spielplatzkontrolle: Passwort zurücksetzen')
    mail.set_content(
        'Guten Tag\n\n'
        + ('Bitte bestätigen Sie Ihre Registrierung und legen Sie Ihr Passwort fest:\n'
           if purpose == 'register' else 'Bitte legen Sie über diesen Link ein neues Passwort fest:\n')
        + url + '\n\nDer Link ist 30 Minuten gültig und nur einmal verwendbar. '
        'Falls Sie dies nicht beantragt haben, ignorieren Sie die Nachricht.\n'
    )
    deliver(mail, email)


def _issue(db, email, purpose, ip_hash):
    # One transaction-level lock for rate check and token issuance per account.
    db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('account-recovery:' + email,))
    email_count = db.execute(
        '''SELECT count(*) AS n FROM "wgr_sp_account_token"
           WHERE e_mail=%s AND created_at > now() - interval '30 minutes' ''',
        (email,),
    ).fetchone()['n']
    ip_count = db.execute(
        '''SELECT count(*) AS n FROM "wgr_sp_account_token"
           WHERE request_ip_hash=%s AND created_at > now() - interval '1 hour' ''',
        (ip_hash,),
    ).fetchone()['n']
    if email_count >= 3 or ip_count >= 10:
        return None
    raw = secrets.token_urlsafe(32)
    db.execute(
        '''INSERT INTO "wgr_sp_account_token"
            (token_hash, e_mail, purpose, expires_at, request_ip_hash)
            VALUES (%s, %s, %s, now() + interval '30 minutes', %s)''',
        (_hash(raw), email, purpose, ip_hash),
    )
    return raw


def _request_link(request, purpose):
    mode = 'register' if purpose == 'register' else 'forgot'
    if request.method == 'GET':
        return _response(request, mode)
    if not _post_ok(request):
        return _response(request, mode, error='Ungültige Anfrage.', status=400)
    email = _canonical_email(request.POST.get('email'))
    if not email:
        return _response(request, mode, error='Bitte eine gültige E-Mail-Adresse eingeben.', status=400)
    first = str(request.POST.get('first_name') or '').strip()
    last = str(request.POST.get('last_name') or '').strip()
    if purpose == 'register' and (not first or not last or len(first) > 80 or len(last) > 80):
        return _response(request, mode, error='Bitte Vorname und Nachname angeben (max. 80 Zeichen).', email=email, status=400)
    token = None
    try:
        with connect() as db:
            # Shared advisory lock serializes registration for an email address.
            db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('account:' + email,))
            matches = user_repository.users_by_email(db, email)
            if purpose == 'register':
                if not matches:
                    token = _issue(db, email, purpose, _ip_fingerprint(request))
                    if token is not None:
                        db.execute('''INSERT INTO "wgr_sp_kontrolleur"
                            (nachname, vorname, e_mail, pwd, rolle, aktiv, is_new)
                            VALUES (%s, %s, %s, NULL, 'inspector', false, true)''',
                            (last, first, email))
                elif len(matches) == 1 and not matches[0].get('active') and not matches[0].get('pwd'):
                    token = _issue(db, email, purpose, _ip_fingerprint(request))
            elif len(matches) == 1 and matches[0].get('pwd'):
                token = _issue(db, email, purpose, _ip_fingerprint(request))
    except Exception:
        LOG.exception('Account recovery request failed')
        return _response(request, mode, error='Dienst momentan nicht verfügbar.', status=503)
    if token is not None:
        try:
            _send(email, purpose, token)
        except Exception:
            LOG.exception('Account recovery email delivery failed')
            # Avoid account enumeration in HTTP response or status.
    return _response(request, mode, message=GENERIC)


@require_http_methods(['GET', 'POST'])
def register(request):
    return _request_link(request, 'register')


@require_http_methods(['GET', 'POST'])
def forgot(request):
    return _request_link(request, 'reset')


@require_http_methods(['GET', 'POST'])
def set_password(request, token):
    if not TOKEN_RE.fullmatch(token):
        return _response(request, 'set', error='Link ungültig oder abgelaufen.')
    # Referrer policy prevents leaking the bearer token through outbound links.
    if request.method == 'GET':
        response = _response(request, 'set', token=token)
        response['Referrer-Policy'] = 'no-referrer'
        return response
    if not _post_ok(request):
        return _response(request, 'set', error='Ungültige Anfrage.', token=token, status=400)
    password = request.POST.get('password') or ''
    confirm = request.POST.get('confirm') or ''
    if len(password) < 12 or len(password) > 1024 or password != confirm:
        return _response(request, 'set', error='Passwörter müssen übereinstimmen und mindestens 12 Zeichen enthalten.', token=token, status=400)
    try:
        with connect() as db:
            record = db.execute(
                '''SELECT e_mail, purpose FROM "wgr_sp_account_token"
                   WHERE token_hash=%s AND used_at IS NULL AND expires_at > now()
                   FOR UPDATE''', (_hash(token),),
            ).fetchone()
            if record is None or record['purpose'] not in PURPOSES:
                return _response(request, 'set', error='Link ungültig oder abgelaufen.')
            email = record['e_mail']
            user = user_repository.user_by_email(db, email, for_update=True)
            if user is None:
                return _response(request, 'set', error='Link ungültig oder abgelaufen.')
            if record['purpose'] == 'register' and (user.get('active') or user.get('pwd')):
                return _response(request, 'set', error='Link ungültig oder abgelaufen.')
            if record['purpose'] == 'reset' and not user.get('pwd'):
                return _response(request, 'set', error='Link ungültig oder abgelaufen.')
            changed = user_write_repository.update_password(db, email, auth.hash_passphrase(password, email))
            if changed != 1:
                raise RuntimeError('Unexpected password update count')
            db.execute('''UPDATE "wgr_sp_account_token" SET used_at=now()
                          WHERE token_hash=%s''', (_hash(token),))
            db.execute('''UPDATE "wgr_sp_account_token" SET used_at=now()
                          WHERE e_mail=%s AND used_at IS NULL''', (email,))
            # Explicitly DO NOT activate the user. Only admin/users/ can do so.
    except Exception:
        LOG.exception('Account password confirmation failed')
        return _response(request, 'set', error='Dienst momentan nicht verfügbar.', token=token, status=503)
    response = _response(request, 'done', message=(
        'Passwort gesetzt. Ihr Konto wartet weiterhin auf die Freischaltung durch einen Administrator.'
        if record['purpose'] == 'register' else 'Passwort aktualisiert. Sie können sich anmelden.'
    ))
    response['Referrer-Policy'] = 'no-referrer'
    return response
