"""Local UI catalogs and request language selection; no external translation service."""
from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path
from django.utils import translation

LANGUAGES = (('de', 'Deutsch'), ('fr', 'Français'), ('it', 'Italiano'),
             ('rm', 'Rumantsch'), ('en', 'English'))
CODES = frozenset(code for code, _ in LANGUAGES)
COOKIE = 'spk_ui_language'

@lru_cache(maxsize=1)
def catalogs():
    return json.loads(Path(__file__).with_name('translations.json').read_text(encoding='utf-8'))

def browser_language(header):
    candidates = []
    for position, entry in enumerate(str(header or '')[:4096].split(',')):
        pieces = entry.strip().lower().split(';')
        code = pieces[0].split('-')[0]
        quality = 1.0
        try:
            for parameter in pieces[1:]:
                if parameter.strip().startswith('q='):
                    quality = float(parameter.strip()[2:])
        except ValueError:
            continue
        if code in CODES and 0 < quality <= 1:
            candidates.append((-quality, position, code))
    return min(candidates)[2] if candidates else 'de'

def language_for_request(request, user=None):
    browser = browser_language(request.headers.get('Accept-Language', ''))
    if isinstance(user, dict):
        # NULL is an explicit browser default, including when another account
        # previously chose a language in this browser.
        preferred = user.get('uiLanguage')
        return preferred if preferred in CODES else browser
    public_choice = request.get_signed_cookie(COOKIE, default='', salt=COOKIE, max_age=31536000)
    return public_choice if public_choice in CODES else browser

def tr(value, language=None):
    if value is None:
        return ''
    source = str(value)
    source = {"administrator": "Administrator", "inspector": "Kontrolleur", "maintenance": "Unterhalt"}.get(source, source)
    code = (language or translation.get_language() or 'de').split('-')[0]
    if code == 'de':
        return source
    table = catalogs().get(code, {})
    if source in table:
        return table[source]
    # Type labels from the database keep their wire-format abbreviation.
    match = re.fullmatch(r'(.+) (\([^()]+\))', source)
    if match and match[1] in table:
        return table[match[1]] + ' ' + match[2]
    return source

class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with translation.override(language_for_request(request)):
            response = self.get_response(request)
        return response


def csrf_failure(request, reason=""):
    from .python_ui import _render
    return _render(request, 'error.html', {
        'message': 'Formularschutz fehlgeschlagen. Bitte laden Sie die Seite neu und versuchen Sie es erneut.'
    }, status=403)


def page_not_found(request, exception=None):
    from .python_ui import _render
    return _render(request, 'error.html', {'message': 'Die angeforderte Seite wurde nicht gefunden.'}, status=404)


def server_error(request):
    from .python_ui import _render
    return _render(request, 'error.html', {'message': 'Ein technischer Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.'}, status=500)


def app_manifest(request):
    from django.http import JsonResponse, HttpResponseNotAllowed
    from django.utils.cache import patch_vary_headers
    from .python_ui import _prefix
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    language = language_for_request(request)
    manifest = json.loads((Path(__file__).resolve().parents[1] / 'static/manifest.webmanifest').read_text())
    manifest['name'] = tr('Spielplatzkontrolle', language)
    manifest['lang'] = language
    prefix = _prefix(request)
    manifest['scope'] = manifest['start_url'] = prefix + '/'
    for icon in manifest['icons']:
        icon['src'] = prefix + '/static/' + icon['src']
    response = JsonResponse(manifest, content_type='application/manifest+json')
    response['Content-Language'] = language
    response['Cache-Control'] = 'no-store'
    patch_vary_headers(response, ('Cookie', 'Accept-Language'))
    return response
