"""New GUI routes must fail closed before private data access."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    from django.test import RequestFactory
except ImportError:
    django = None

@unittest.skipUnless(django is not None, "Django not installed")
class ExtendedGUIAuthTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()

    def test_new_pages_deny_anonymous(self):
        with patch.object(self.ui, "require_user", return_value=(None, object())), patch.object(self.ui, "connect") as db:
            self.assertEqual(self.ui.my_profile(self.rf.get("/__ui/profile/")).status_code, 401)
            self.assertEqual(self.ui.defect_detail(self.rf.get("/__ui/defect/?tid=23")).status_code, 401)
            db.assert_not_called()

    def test_invalid_tid_rejected_before_database(self):
        with patch.object(self.ui, "require_user", return_value=({"role": "inspector"}, None)), patch.object(self.ui, "connect") as db:
            self.assertEqual(self.ui.defect_detail(self.rf.get("/__ui/defect/?tid=not-an-integer")).status_code, 400)
            db.assert_not_called()

    def test_profile_does_not_expose_credentials(self):
        with patch.object(self.ui, "require_user", return_value=({"name": "Test", "mailAddress": "t@example.ch", "role": "inspector", "password": "secret-token"}, None)):
            response = self.ui.my_profile(self.rf.get("/__ui/profile/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"secret-token", response.content)
