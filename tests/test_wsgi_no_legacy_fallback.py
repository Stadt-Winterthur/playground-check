"""Cutover tests for the native Django-only WSGI entry point."""
import unittest
from unittest.mock import patch

try:
    from playground_check.django_project import wsgi
except ImportError:
    wsgi = None


@unittest.skipIf(wsgi is None, "Django not installed")
class NativeWSGICutoverTest(unittest.TestCase):
    def test_no_legacy_wsgi_application(self):
        self.assertFalse(hasattr(wsgi, "legacy_application"))

    def test_every_method_reaches_django_with_same_base_path(self):
        from playground_check.django_project import route_registry
        from playground_check.config import settings
        path = (settings.base_path or "") + "/account/login"
        for method in ("POST", "GET", "OPTIONS", "DELETE"):
            with self.subTest(method=method), patch.object(wsgi, "_django_application", return_value=[b"ok"]) as app:
                self.assertEqual(wsgi.application({"PATH_INFO": path, "REQUEST_METHOD": method}, lambda *_: None), [b"ok"])
                env = app.call_args.args[0]
                self.assertEqual(env["PATH_INFO"], "/Account/Login/")
                self.assertEqual(env["REQUEST_METHOD"], method)

    def test_unknown_path_is_passed_directly_to_django(self):
        with patch.object(wsgi, "_django_application", return_value=[b"ok"]) as app:
            wsgi.application({"PATH_INFO": "/api/unknown", "REQUEST_METHOD": "GET"}, lambda *_: None)
            self.assertEqual(app.call_args.args[0]["PATH_INFO"], "/api/unknown")
