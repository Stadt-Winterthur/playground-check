"""Step 34: native account reads and logout keep exact legacy contracts."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
try:
    import django
except ImportError:
    django = None


@unittest.skipUnless(django is not None, 'Django/DRF not installed')
class NativeAccountQueriesTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import account_document_push_views as views
        self.views = views


    def test_me_uses_domain_identity_without_old_http_handler(self):
        from django.test import RequestFactory
        from playground_check import service
        expected = {'fid': 12, 'mailAddress': 'user@example.org'}
        with patch.object(service, 'require_user', return_value=(expected, None)), \
                patch.object(service, 'get_current_account', side_effect=AssertionError('legacy handler invoked')):
            result = self.views.account_me(RequestFactory().get('/Account/Me/'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.content), expected)

    def test_get_users_requires_admin_before_repository(self):
        from django.test import RequestFactory
        from playground_check import service
        from playground_check.http import Response
        with patch.object(service, 'require_user', return_value=(None, Response.text('denied', 401))) as auth, \
                patch.object(service.user_repository, 'users', side_effect=AssertionError('unauthorized DB access')):
            result = self.views.users(RequestFactory().get('/Account/Users/'))
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.content, b'denied')
        self.assertEqual(auth.call_args.args[1], 'administrator')

    def test_get_users_preserves_filter_and_public_fields(self):
        from django.test import RequestFactory
        from playground_check import service
        row = {'fid': 3, 'email': 'a@example.org', 'pwd': 'SECRET', 'role': 'inspector', 'active': True}
        connection = MagicMock()
        connection.__enter__.return_value = 'db'
        with patch.object(service, 'require_user', return_value=({'fid': 1}, None)), \
                patch.object(service, 'connect', return_value=connection), \
                patch.object(service.user_repository, 'users', return_value=[row]) as users:
            result = self.views.users(RequestFactory().get('/Account/Users/?email=A%40EXAMPLE.ORG'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.content)[0]['passPhrase'], '')
        users.assert_called_once_with('db', 'a@example.org')

    def test_assignable_users_uses_repository_directly(self):
        from django.test import RequestFactory
        from playground_check import service
        connection = MagicMock()
        connection.__enter__.return_value = 'db'
        with patch.object(service, 'require_user', return_value=({'fid': 1}, None)), \
                patch.object(service, 'connect', return_value=connection), \
                patch.object(service.user_repository, 'assignable_users', return_value=[]) as repo:
            result = self.views.assignable_users(RequestFactory().get('/Account/Users/Assignable/'))
        self.assertEqual(json.loads(result.content), [])
        repo.assert_called_once_with('db')

    def test_logout_clears_cookie_without_old_handler(self):
        from django.test import RequestFactory
        from playground_check import service
        with patch.object(service, 'logout', side_effect=AssertionError('legacy handler invoked')):
            result = self.views.logout(RequestFactory().post('/Account/Logout/'))
        self.assertEqual(result.status_code, 204)
        self.assertEqual(result.content, b'')
        self.assertIn('Max-Age=0', result['Set-Cookie'])

    def test_admin_writes_and_login_still_use_compatibility_layer(self):
        from django.test import RequestFactory
        from playground_check import service
        from playground_check.http import Response
        with patch.object(service, 'login', return_value=Response.text('invalid', 400)), \
                patch.object(service, 'update_user', return_value=Response.json({'errorMessage': 'SPK-3'})):
            login = self.views.login(RequestFactory().post('/Account/Login/', data='{}', content_type='application/json'))
            update = self.views.users(RequestFactory().put('/Account/Users/', data='{}', content_type='application/json'))
        self.assertEqual(login.status_code, 400)
        self.assertEqual(update.status_code, 200)
