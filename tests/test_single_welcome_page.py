"""Login and old bookmarks lead to the single canonical welcome page."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve
from playground_check.django_project import python_ui as ui, python_ui_workflows as workflows


class SingleWelcomePageTests(unittest.TestCase):
    def test_old_bookmarks_redirect_without_private_queries(self):
        for prefix in ('', '/stadtgruen/spielplatzkontrolle'):
            with self.subTest(prefix=prefix), patch.object(ui, '_identity') as identity, patch.object(ui, 'connect') as db:
                request = RequestFactory().get('/workspace/', SCRIPT_NAME=prefix)
                # Resolve the real URL so this also verifies the compatibility route.
                with patch.object(ui, '_prefix', return_value=prefix):
                    response = resolve('/workspace/').func(request)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], prefix + '/')
                identity.assert_not_called()
                db.assert_not_called()

    def test_successful_login_goes_home_and_preserves_cookie(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        request = RequestFactory().post('/login/', {'email': 'test@example.org', 'password': 'test-password'}, SCRIPT_NAME=prefix)
        request._dont_enforce_csrf_checks = True
        answer = HttpResponse('{}', content_type='application/json')
        name = workflows.account_commands.service.settings.auth_cookie_name
        answer.set_cookie(name, 'test-token', httponly=True, path=prefix + '/')
        with patch.object(workflows, '_native', return_value=answer):
            response = workflows.login(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], prefix + '/')
        self.assertEqual(response.cookies[name].value, 'test-token')
        self.assertTrue(response.cookies[name]['httponly'])

    def test_authenticated_home_shows_canonical_welcome(self):
        request = RequestFactory().get('/')
        request.COOKIES[ui.settings.auth_cookie_name] = 'test-token'
        with patch.object(ui, '_identity', return_value=({'fid': 17, 'firstName': 'Edgar'}, None)):
            response = ui.home(request)
        self.assertIn(b'Willkommen bei der Spielplatzkontrolle', response.content)
        self.assertNotIn(b'W\xc3\xa4hle die passende Aufgabe', response.content)
        self.assertNotIn(b'/workspace/', response.content)
        self.assertIn(b'authenticated', response.content)
