"""Contracts for native permission classes and legacy error preservation."""

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
class PermissionMigrationTest(unittest.TestCase):
    def request(self, path):
        from playground_check.django_project import wsgi
        captured = {}
        environ = {
            "REQUEST_METHOD": "GET", "PATH_INFO": path,
            "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80",
            "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1",
        }
        def start_response(status, headers, exc_info=None):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)
        body = b"".join(wsgi.application(environ, start_response))
        return captured["status"], captured["headers"], body

    def test_permission_rejects_before_sql_with_plaintext(self):
        from playground_check.django_project import views
        from playground_check.http import Response as LegacyResponse
        with patch.object(views, "require_user", return_value=(None, LegacyResponse.text("unauthorized", 401))) as auth, \
             patch.object(views, "connect") as db:
            status, headers, body = self.request("/Inspection/types/")
        self.assertEqual(status, 401)
        self.assertEqual(body, b"unauthorized")
        self.assertTrue(headers["Content-Type"].startswith("text/plain"))
        auth.assert_called_once()
        db.assert_not_called()

    def test_permission_exposes_existing_user_to_list_filter(self):
        from playground_check.django_project import views
        user = {"fid": 123, "role": "Kontrolleur"}
        with patch.object(views, "require_user", return_value=(user, None)) as auth, \
             patch.object(views, "playground_only_names_data", return_value=[]) as fetch:
            status, _, body = self.request("/Playground/onlynames/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [])
        auth.assert_called_once()
        fetch.assert_called_once_with(user, {})

    def test_public_health_does_not_call_authentication(self):
        from playground_check.django_project import views
        with patch.object(views, "require_user") as auth:
            status, _, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")
        auth.assert_not_called()
