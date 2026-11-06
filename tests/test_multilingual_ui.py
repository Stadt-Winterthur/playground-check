"""Language negotiation, account persistence, escaping and catalog coverage."""
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
from django.test import Client, RequestFactory
from django.utils import translation
from playground_check.django_project import python_ui as ui
from playground_check.django_project.localization import (
    CODES, COOKIE, LanguageMiddleware, browser_language, catalogs, language_for_request, tr,
)

ROOT = Path(ui.__file__).resolve().parent
USER = {'fid': 17, 'role': 'inspector', 'mailAddress': 'test@example.org', 'uiLanguage': None}

class MultilingualUITests(unittest.TestCase):
    def test_regional_languages_and_weighted_preferences(self):
        cases = {'fr-CH,fr;q=0.9,de;q=0.8': 'fr', 'it-CH': 'it', 'rm-CH': 'rm',
                 'en-GB': 'en', 'de-CH': 'de', 'es-ES,en;q=0.7': 'en',
                 'it;q=0,fr;q=0.3,en;q=0.9': 'en', 'fr;q=invalid,it;q=0.5': 'it',
                 'xx;q=1,de;q=0.2': 'de', 'es,ja': 'de', '': 'de'}
        for header, expected in cases.items():
            with self.subTest(header=header):
                self.assertEqual(browser_language(header), expected)

    def test_public_pages_headers_and_language(self):
        for code, heading in [('de', 'Datenschutzerklärung'), ('fr', 'Déclaration de protection des données'),
                              ('it', 'Informativa sulla protezione dei dati'),
                              ('rm', 'Decleraziun davart la protecziun da datas'), ('en', 'Privacy notice')]:
            with self.subTest(code=code):
                response = Client().get('/privacy/', HTTP_ACCEPT_LANGUAGE=code + '-CH')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Language'], code)
                self.assertIn('Accept-Language', response['Vary'])
                self.assertIn('lang="' + code + '"', response.content.decode())
                self.assertIn(heading, response.content.decode())

    def test_account_language_overrides_browser(self):
        for code in CODES:
            with self.subTest(code=code), patch.object(ui, 'require_user', return_value=({**USER, 'uiLanguage': code}, None)):
                response = Client().get('/profile/', HTTP_ACCEPT_LANGUAGE='fr-CH')
                self.assertEqual(response['Content-Language'], code)
                self.assertIn('value="' + code + '" selected', response.content.decode())

    def test_browser_default_ignores_cookie_from_another_account(self):
        request = RequestFactory().get('/profile/', HTTP_ACCEPT_LANGUAGE='it-CH')
        self.assertEqual(language_for_request(request, {**USER, 'uiLanguage': None}), 'it')
        with patch.object(ui, 'require_user', return_value=(USER, None)):
            response = Client().get('/profile/', HTTP_ACCEPT_LANGUAGE='rm-CH')
        self.assertEqual(response['Content-Language'], 'rm')
        self.assertIn('<option value="" selected>', response.content.decode())

    def test_setting_and_reset_are_persisted_for_authenticated_user_only(self):
        for choice, stored in [('en', 'en'), ('rm', 'rm'), ('', None)]:
            with self.subTest(choice=choice):
                db = MagicMock()
                db.__enter__.return_value.execute.return_value.rowcount = 1
                client = Client(enforce_csrf_checks=True)
                with patch.object(ui, 'require_user', return_value=(USER, None)), patch.object(ui, 'connect', return_value=db):
                    page = client.get('/profile/')
                    self.assertNotIn('csrfmiddlewaretoken', page.content.decode())
                    response = client.post('/profile/', {'language': choice,
                                                         'fid': 999}, SCRIPT_NAME='/spk')
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], '/spk/profile/?language_saved=1')
                query, params = db.__enter__.return_value.execute.call_args.args
                self.assertEqual(params, (stored, 17))
                self.assertIn('WHERE fid=%s', query)
                self.assertEqual(response.cookies[COOKIE]['path'], '/spk/')
                if choice:
                    self.assertTrue(response.cookies[COOKIE]['httponly'])
                    self.assertEqual(response.cookies[COOKIE]['samesite'], 'Lax')
                else:
                    self.assertEqual(response.cookies[COOKIE]['max-age'], 0)

    def test_language_post_needs_authentication_but_no_csrf_token(self):
        db = MagicMock()
        db.__enter__.return_value.execute.return_value.rowcount = 1
        with patch.object(ui, 'require_user', return_value=(USER, None)), patch.object(ui, 'connect', return_value=db):
            self.assertEqual(Client(enforce_csrf_checks=True).post('/profile/', {'language': 'en'}).status_code, 302)
        db.__enter__.return_value.execute.assert_called_once()
        db.reset_mock()
        with patch.object(ui, 'require_user', return_value=(None, object())), patch.object(ui, 'connect', return_value=db):
            self.assertEqual(Client().post('/profile/', {'language': 'en'}).status_code, 401)
        db.__enter__.return_value.execute.assert_not_called()

    def test_invalid_language_never_writes(self):
        with patch.object(ui, 'require_user', return_value=(USER, None)), patch.object(ui, 'connect') as db:
            response = Client().post('/profile/', {'language': '../../en'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-UI-Original-Status'], '400')
        self.assertIn('role="alert"', response.content.decode())
        self.assertIn('Ungültige Sprachauswahl.', response.content.decode())
        self.assertNotIn('Sprachauswahl gespeichert.', response.content.decode())
        db.assert_not_called()

    def test_database_failure_does_not_claim_preference_was_saved(self):
        with patch.object(ui, 'require_user', return_value=(USER, None)), patch.object(ui, 'connect', side_effect=RuntimeError('offline')):
            response = Client().post('/profile/', {'language': 'en'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-UI-Original-Status'], '400')
        self.assertIn('role="alert"', response.content.decode())
        self.assertIn('Sprachauswahl konnte nicht gespeichert werden.', response.content.decode())
        self.assertNotIn('Sprachauswahl gespeichert.', response.content.decode())
        self.assertNotIn(COOKIE, response.cookies)

    def test_public_language_cookie_is_signed(self):
        client = Client()
        client.cookies[COOKIE] = 'en'
        self.assertEqual(client.get('/privacy/', HTTP_ACCEPT_LANGUAGE='fr')['Content-Language'], 'fr')
        response = ui.HttpResponse()
        response.set_signed_cookie(COOKIE, 'en', salt=COOKIE)
        client.cookies[COOKIE] = response.cookies[COOKIE].value
        self.assertEqual(client.get('/privacy/', HTTP_ACCEPT_LANGUAGE='fr')['Content-Language'], 'en')

    def test_language_context_is_restored_between_requests(self):
        with translation.override('it'):
            middleware = LanguageMiddleware(lambda request: ui.HttpResponse(translation.get_language()))
            response = middleware(RequestFactory().get('/', HTTP_ACCEPT_LANGUAGE='en'))
            self.assertEqual(response.content, b'en')
            self.assertEqual(translation.get_language(), 'it')

    def test_catalogs_cover_templates_and_browser_messages(self):
        required = set(catalogs()['js_keys'])
        for file in (ROOT / 'ui_templates').glob('*.html'):
            text = file.read_text()
            ui.ENGINE.get_template(file.name)
            for match in re.finditer(r'{% tr ("(?:\\.|[^"\\])*") %}', text):
                required.add(json.loads(match[1]))
            for match in re.finditer(r'''\|ui_default:(["'])(.*?)\1''', text):
                required.add(match[2])
        for code in CODES - {'de'}:
            self.assertFalse(required - catalogs()[code].keys(), (code, sorted(required - catalogs()[code].keys())))
            for source in required:
                target = catalogs()[code][source]
                self.assertTrue(target)
                self.assertEqual(set(re.findall(r'\{\w+\}', source)), set(re.findall(r'\{\w+\}', target)))

    def test_user_data_is_not_translated_or_interpreted_as_html(self):
        request = RequestFactory().get('/assigned/', HTTP_ACCEPT_LANGUAGE='fr')
        response = ui._render(request, 'assigned.html', {'rows': [{'name': 'Suchen <script>alert(1)</script>'}],
                                                        'private': True, 'user': USER, 'page': 1})
        self.assertIn('Suchen &lt;script&gt;', response.content.decode())
        self.assertNotIn('<script>alert(1)</script>', response.content.decode())

    def test_inspection_wire_value_stays_german(self):
        kind = 'Visuelle Inspektion (VI)'
        for code in CODES:
            response = ui._render(RequestFactory().get('/inspection/', HTTP_ACCEPT_LANGUAGE=code),
                                  'inspection_editor.html', {'kind': kind, 'name': 'Musterpark', 'devices': [],
                                                             'private': True, 'user': USER})
            html = response.content.decode()
            self.assertIn('name="inspectiontype" value="Visuelle Inspektion (VI)"', html)
            if code != 'de':
                self.assertIn(tr(kind, code), html)

    def test_missing_value_labels_only_translate_fallbacks(self):
        from playground_check.django_project.templatetags.ui_language import ui_default
        with translation.override('fr'):
            self.assertEqual(ui_default('', 'Spielgerät'), 'Équipement de jeu')
            self.assertEqual(ui_default('Spielgerät', 'Unbekannt'), 'Spielgerät')

    def test_german_templates_use_formal_address(self):
        for file in (ROOT / 'ui_templates').glob('*.html'):
            self.assertIsNone(re.search(r'\b(?:du|Du|dein\w*|Dein\w*|dich|Dich|dir|Dir)\b', file.read_text()), file.name)


    def test_manifest_and_generic_error_pages_follow_browser_language(self):
        client = Client()
        manifest = client.get('/manifest.webmanifest', SCRIPT_NAME='/spk', HTTP_ACCEPT_LANGUAGE='it-CH')
        self.assertEqual(manifest.json()['name'], 'Controllo parchi giochi')
        self.assertEqual(manifest.json()['lang'], 'it')
        self.assertEqual(manifest.json()['start_url'], '/spk/')
        self.assertTrue(all(icon['src'].startswith('/spk/static/') for icon in manifest.json()['icons']))
        missing = client.get('/this-page-does-not-exist/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(missing.status_code, 404)
        self.assertIn(b'The requested page was not found.', missing.content)
        denied = Client(enforce_csrf_checks=True).post('/profile/', {'language': 'en'}, HTTP_ACCEPT_LANGUAGE='fr', HTTP_SEC_FETCH_SITE='cross-site')
        self.assertEqual(denied.status_code, 403)
        self.assertIn('Cross-site requests are not permitted.', denied.content.decode())

    def test_inspection_select_translates_label_but_preserves_option_value(self):
        response = ui._render(RequestFactory().get('/assigned/', HTTP_ACCEPT_LANGUAGE='en'), 'assigned.html', {
            'private': True, 'user': USER, 'inspection_mode': True,
            'inspection_types': ['Visuelle Inspektion (VI)'], 'rows': [], 'page': 1,
        })
        self.assertIn(b'<option value="Visuelle Inspektion (VI)" >Visual inspection (VI)</option>', response.content)

    def test_user_account_mapping_includes_preference(self):
        from playground_check import service, domain_support
        for module in [service, domain_support]:
            self.assertEqual(module._user_dict({'ui_language': 'rm'})['uiLanguage'], 'rm')

    def test_default_account_clears_an_earlier_signed_language_cookie(self):
        client = Client()
        signed = ui.HttpResponse()
        signed.set_signed_cookie(COOKIE, 'en', salt=COOKIE)
        client.cookies[COOKIE] = signed.cookies[COOKIE].value
        with patch.object(ui, 'require_user', return_value=(USER, None)):
            response = client.get('/profile/', HTTP_ACCEPT_LANGUAGE='it')
        self.assertEqual(response['Content-Language'], 'it')
        self.assertEqual(response.cookies[COOKIE]['max-age'], 0)
