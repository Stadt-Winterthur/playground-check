"""Push GUI must remain private even on an Internet-facing test host."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
try:
    import django
    from django.test import RequestFactory
except ImportError:
    django = None


@unittest.skipUnless(django is not None, 'Django not installed')
class PushGuiTest(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()

    def test_unauthenticated_push_settings_denied_before_any_db_query(self):
        with patch.object(self.ui, 'require_user', return_value=(None, object())), \
             patch.object(self.ui, 'connect') as database:
            response = self.ui.push_settings(self.rf.get('/push/'))
        self.assertEqual(response.status_code, 401)
        database.assert_not_called()

    def test_private_push_page_scopes_script_and_has_no_store(self):
        with patch.object(self.ui, 'require_user', return_value=({'fid': 1}, None)):
            response = self.ui.push_settings(self.rf.get('/push/', SCRIPT_NAME='/stadtgruen/spielplatzkontrolle'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/stadtgruen/spielplatzkontrolle/static/js/python-ui-push.js', response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_push_settings_does_not_accept_post(self):
        response = self.ui.push_settings(self.rf.post('/push/'))
        self.assertEqual(response.status_code, 405)
