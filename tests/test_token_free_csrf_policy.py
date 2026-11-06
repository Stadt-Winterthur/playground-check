"""Token-free forms and browser request provenance checks."""
import os
os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','playground_check.django_project.settings')
import unittest
from pathlib import Path
from django.test import Client
from unittest.mock import patch

class TokenFreePolicyTests(unittest.TestCase):
    def test_no_form_or_view_uses_classic_csrf_tokens(self):
        root = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project'
        for file in (root / 'ui_templates').glob('*.html'):
            self.assertNotIn('csrfmiddlewaretoken', file.read_text(), file.name)
        for file in root.glob('*.py'):
            self.assertNotIn('@csrf_protect', file.read_text(), file.name)
            self.assertNotIn('get_token(', file.read_text(), file.name)

    def test_cross_site_writes_blocked_on_html_and_api(self):
        client = Client(enforce_csrf_checks=True)
        for route in ('/login/', '/session/end/', '/profile/', '/Account/Login/'):
            with self.subTest(route=route):
                self.assertEqual(client.post(route, HTTP_SEC_FETCH_SITE='cross-site').status_code, 403)

    def test_same_origin_logout_without_token(self):
        with patch('playground_check.domain_support.revoke_request_session') as revoke:
            response = Client(enforce_csrf_checks=True).post('/session/end/', HTTP_SEC_FETCH_SITE='same-origin')
        self.assertEqual(response.status_code, 302)
        revoke.assert_called_once()
