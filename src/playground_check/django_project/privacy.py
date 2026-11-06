"""Public legal information with optional validated session context."""
import os
from datetime import date

from django.core.validators import validate_email
from django.views.decorators.http import require_GET

from .python_ui import _render
from . import python_ui


def _session_context(request):
    # Reuse normal session/account validation; legal pages never require login.
    # A database outage must not prevent access to the public information.
    try:
        user, error = python_ui._identity(request)
    except Exception:
        python_ui.LOGGER.warning('Session validation unavailable on legal page')
        user, error = None, True
    if error or not user:
        return {'private': False, 'user': None}
    request._ui_user = user
    return {'private': True, 'user': user}


def _public_contact():
    # Read only explicitly public configuration, never the request identity,
    # database connection strings, subscription keys or logging configuration.
    contact = os.getenv('PLAYGROUND_PRIVACY_CONTACT_EMAIL', '').strip() or 'stadtgruen@win.ch'
    validate_email(contact)
    return {
        'contact_name': os.getenv('PLAYGROUND_PRIVACY_CONTACT_NAME', '').strip()
                        or 'Stadt Winterthur, Stadtgrün Winterthur',
        'contact_email': contact,
    }


@require_GET
def privacy_notice(request):
    updated = date.fromisoformat(os.getenv('PLAYGROUND_PRIVACY_NOTICE_DATE', '').strip() or '2026-11-06')
    return _render(request, 'privacy.html', {
        **_session_context(request),
        **_public_contact(), 'page_title': 'Datenschutz – Spielplatzkontrolle', 'legal_page': True,
        'retention_text': os.getenv('PLAYGROUND_PRIVACY_RETENTION_TEXT', '').strip(),
        'operators_text': os.getenv('PLAYGROUND_PRIVACY_OPERATORS_TEXT', '').strip(),
        'notice_date': updated.strftime('%d.%m.%Y'),
    })


@require_GET
def imprint(request):
    return _render(request, 'imprint.html', {
        **_session_context(request),
        **_public_contact(), 'page_title': 'Impressum – Spielplatzkontrolle', 'legal_page': True,
    })
