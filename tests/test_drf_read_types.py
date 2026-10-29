"""Read-only DRF endpoint parity including legacy authorization checks."""
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django REST Framework not installed")
class ReadTypesMigrationTest(unittest.TestCase):
    def call(self, path, method="GET", *, prefix="", cookie=None):
        from playground_check.django_project import wsgi
        captured = {}
        env = {"REQUEST_METHOD": method, "SCRIPT_NAME": "", "PATH_INFO": prefix + path,
               "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
               "SERVER_NAME": "testserver", "SERVER_PORT": "80",
               "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1"}
        if cookie:
            env["HTTP_COOKIE"] = cookie
        def start_response(status, headers, exc_info=None):
            captured.update(status=status, headers=dict(headers))
        from dataclasses import replace
        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path=prefix)):
            raw = b"".join(wsgi.application(env, start_response))
        return int(captured["status"].split()[0]), raw, captured["headers"]

    def test_unauthorized_types_keep_legacy_plaintext_401(self):
        from playground_check.service import UNAUTHORIZED
        for endpoint in ("/Inspection/types/", "/Inspection/renovationtypes/"):
            with self.subTest(endpoint=endpoint):
                status, raw, headers = self.call(endpoint)
                self.assertEqual(status, 401)
                self.assertEqual(raw.decode(), UNAUTHORIZED)
                self.assertIn("text/plain", headers["Content-Type"])

    def test_authenticated_type_lists_keep_legacy_json(self):
        from playground_check.django_project import views
        from playground_check import service
        class DB:
            def __init__(self, rows): self.rows = rows
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql): self.sql = sql; return self
            def fetchall(self): return self.rows
        cases = [("/Inspection/types/", [{"short_value": "HI", "value": "Hauptinspektion"}], ["Hauptinspektion (HI)"]),
                 ("/Inspection/renovationtypes/", [{"value": "Ersatz"}], ["Ersatz"])]
        for endpoint, rows, expected in cases:
            with self.subTest(endpoint=endpoint):
                with patch.object(views, "require_user", return_value=({"active": True}, None)), \
                     patch.object(views, "connect", return_value=DB(rows)):
                    status, raw, _ = self.call(endpoint, prefix="/stadtgruen/spielplatzkontrolle")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(raw), expected)
                # Compare the new result against the old handler on identical mock data.
                with patch.object(service, "require_user", return_value=({"active": True}, None)), \
                     patch.object(service, "connect", return_value=DB(rows)):
                    old = (service.inspection_types if "renovation" not in endpoint else service.renovation_types)(None)
                self.assertEqual(json.loads(raw), json.loads(old.body))

    def test_non_get_method_remains_on_legacy(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, "_django_application", return_value=[b"django"]) as app:
            env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/Inspection/types/"}
            self.assertEqual(wsgi.application(env, lambda *_: None), [b"django"])
            app.assert_called_once()
