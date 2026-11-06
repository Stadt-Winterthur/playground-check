"""F07: public information, truthful configuration and data-entry links."""
import os
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.template import Context
from django.test import Client
from playground_check.django_project import python_ui


class PageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.links = []; self.ids = set(); self.headings = []; self.current_heading = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs: self.ids.add(attrs['id'])
        if tag == 'a': self.links.append(attrs.get('href', ''))
        if tag in ('h1', 'h2'): self.current_heading = tag

    def handle_data(self, data):
        if self.current_heading and data.strip(): self.headings.append((self.current_heading, data.strip()))

    def handle_endtag(self, tag):
        if tag == self.current_heading: self.current_heading = None


class PrivacyNoticeTests(unittest.TestCase):
    def setUp(self):
        # Keep tests independent of deployment-specific public notices.
        self.environment = patch.dict(os.environ, {
            'PLAYGROUND_PRIVACY_CONTACT_NAME': '', 'PLAYGROUND_PRIVACY_CONTACT_EMAIL': '',
            'PLAYGROUND_PRIVACY_OPERATORS_TEXT': '', 'PLAYGROUND_PRIVACY_RETENTION_TEXT': '',
            'PLAYGROUND_PRIVACY_NOTICE_DATE': '',
        })
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.user = {'fid': 31, 'mailAddress': 'synthetic@example.invalid', 'firstName': 'Audit',
                     'lastName': 'Test', 'role': 'inspector', 'active': True}

    def test_notice_is_public_with_stale_credentials_and_without_database(self):
        with patch('playground_check.domain_support.connect', side_effect=AssertionError('database accessed')):
            for headers in ({}, {'HTTP_COOKIE': 'playground.auth=expired'},
                            {'HTTP_AUTHORIZATION': 'Bearer invalid'}):
                response = Client().get('/privacy/', **headers)
                self.assertEqual(response.status_code, 200)
                self.assertContainsPrivacySections(response.content.decode())
                self.assertNotIn(b'synthetic@example.invalid', response.content)

    def assertContainsPrivacySections(self, html):
        page = PageLinks(html)
        self.assertEqual([x for x in page.headings if x[0] == 'h1'], [('h1', 'Datenschutzerklärung')])
        for anchor in ('verantwortung', 'daten', 'fotos', 'browser', 'push', 'aufbewahrung', 'rechte'):
            self.assertIn(anchor, page.ids)
        self.assertIn('mailto:stadtgruen@win.ch', page.links)
        self.assertIn('mailto:datenschutz@win.ch', page.links)

    def test_configured_public_text_is_escaped_and_no_secrets_are_exposed(self):
        with patch.dict(os.environ, {
            'PLAYGROUND_PRIVACY_CONTACT_NAME': 'Teststelle <script>alert(1)</script>',
            'PLAYGROUND_PRIVACY_CONTACT_EMAIL': 'privacy@example.invalid',
            'PLAYGROUND_PRIVACY_OPERATORS_TEXT': 'Testbetrieb A & B\nSpeicherort Testumgebung',
            'PLAYGROUND_PRIVACY_RETENTION_TEXT': 'Fachlich geprüfte Testfrist <img src=x onerror=alert(1)>',
            'PLAYGROUND_PRIVACY_NOTICE_DATE': '2026-11-05',
            'PLAYGROUND_POSTGRES_DSN': 'PRIVATE_DATABASE_SECRET',
            'PLAYGROUND_SECURITY_KEY': 'PRIVATE_SIGNING_SECRET',
            'PLAYGROUND_ELK_URL': 'PRIVATE_LOGGING_URL',
        }):
            response = Client().get('/privacy/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for expected in ('05.11.2026', 'mailto:privacy@example.invalid', 'A &amp; B',
                         'Testumgebung', '&lt;script&gt;', '&lt;img'):
            self.assertIn(expected, html)
        for forbidden in ('<script>alert', '<img src=x', 'PRIVATE_DATABASE_SECRET',
                          'PRIVATE_SIGNING_SECRET', 'PRIVATE_LOGGING_URL'):
            self.assertNotIn(forbidden, html)

    def test_invalid_email_or_date_does_not_publish_unchecked_values(self):
        for key, value in [('PLAYGROUND_PRIVACY_CONTACT_EMAIL', 'invalid-address'),
                           ('PLAYGROUND_PRIVACY_NOTICE_DATE', 'not-a-date')]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                response = Client(raise_request_exception=False).get('/privacy/')
                self.assertEqual(response.status_code, 500)
                self.assertNotIn(value.encode(), response.content)

    def test_notice_describes_token_free_form_protection_in_all_languages(self):
        from playground_check.django_project.localization import catalogs
        response = Client().get('/privacy/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('Klassische CSRF-Formulartokens kommen nicht zum Einsatz.', html)
        self.assertIn('ausdrücklich als websiteübergreifend kennzeichnet', html)
        self.assertNotIn('Cookies für Anmeldung und Formularschutz', html)
        for language in ('fr', 'it', 'rm', 'en'):
            with self.subTest(language=language):
                self.assertTrue(
                    any(key.startswith('Für die Anmeldung wird ein technisch notwendiges')
                        for key in catalogs()[language]),
                    f'Datenschutzhinweis fehlt in {language}',
                )

    def test_notice_uses_existing_f05_security_headers(self):
        response = Client().get('/privacy/')
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('Authorization', response['Vary'])
        self.assertIn("default-src 'none'", response['Content-Security-Policy'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_login_and_profile_link_to_notice_including_base_path(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        with patch.object(python_ui, 'require_user', return_value=(self.user, None)):
            login = Client().get('/login/', SCRIPT_NAME=prefix)
            profile = Client().get('/profile/', SCRIPT_NAME=prefix)
        self.assertEqual(login.status_code, 200); self.assertEqual(profile.status_code, 200)
        self.assertIn(prefix + '/privacy/', PageLinks(login.content.decode()).links)
        self.assertIn(prefix + '/privacy/#rechte', PageLinks(profile.content.decode()).links)
        self.assertNotIn('type="checkbox"', login.content.decode())

    def test_public_notice_anchors_and_home_link_use_base_path(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        response = Client().get('/privacy/', SCRIPT_NAME=prefix)
        self.assertEqual(response.status_code, 200)
        links = PageLinks(response.content.decode()).links
        self.assertIn(prefix + '/privacy/', links)
        self.assertIn(prefix + '/', links)

    def test_device_photo_explains_data_use_before_upload(self):
        with patch.object(python_ui, 'require_user', return_value=(self.user, None)):
            response = Client().get('/device/photo/?fid=42', SCRIPT_NAME='/spk')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('/spk/privacy/#fotos', PageLinks(html).links)
        self.assertLess(html.index('insbesondere Kinder'), html.index('>Foto ersetzen</button>'))
        self.assertIn('Foto-Metadaten', html)

    def test_both_defect_photo_uploads_show_photo_hint(self):
        html = python_ui.ENGINE.get_template('defect_detail.html').render(Context({
            'prefix': '/spk', 'tid': 42, 'defect': {'responsibleUserFid': -1},
        }))
        self.assertEqual(PageLinks(html).links.count('/spk/privacy/#fotos'), 2)
        self.assertEqual(html.count('insbesondere Kinder'), 2)

    def test_push_notice_precedes_activation_and_explains_logout_limit(self):
        configured = replace(python_ui.settings, service_worker_enabled=True, vapid_public_key='public-test-key')
        with patch.object(python_ui, 'settings', configured), \
             patch.object(python_ui, 'require_user', return_value=(self.user, None)):
            response = Client().get('/push/', SCRIPT_NAME='/spk')
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('/spk/privacy/#push', PageLinks(html).links)
        self.assertLess(html.index('Push-Dienst Ihres Browseranbieters'), html.index('id="push-enable"'))
        self.assertIn('Abmelden allein deaktiviert Push nicht', html)

    def test_notice_is_read_only_and_footer_reaches_anonymous_home(self):
        response = Client().post('/privacy/')
        self.assertEqual(response.status_code, 405)
        self.assertIn('no-store', response['Cache-Control'])
        home = Client().get('/')
        self.assertEqual(home.status_code, 200)
        self.assertIn('/privacy/', PageLinks(home.content.decode()).links)


if __name__ == '__main__':
    unittest.main()
