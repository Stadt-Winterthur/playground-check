"""Regression contract for native DRF GET routes and legacy fallback."""

import io
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")

try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django REST Framework not installed")
class DRFMigrationTest(unittest.TestCase):
    def call(self, path, *, method="GET", base=""):
        from playground_check.django_project import wsgi
        captured = {}
        environ = {
            "REQUEST_METHOD": method, "SCRIPT_NAME": "", "PATH_INFO": path,
            "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80",
            "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1",
        }
        def start_response(status, headers, exc_info=None):
            captured.update(status=status, headers=dict(headers))
        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path=base)):
            body = b"".join(wsgi.application(environ, start_response))
        return int(captured["status"].split()[0]), json.loads(body), captured["headers"]

    def test_health_matches_legacy_json(self):
        from playground_check import __version__
        status, result, headers = self.call("/api/health")
        self.assertEqual((status, result), (200, {"status": "ok", "version": __version__}))
        self.assertIn("application/json", headers["Content-Type"])

    def test_prefixed_health(self):
        status, result, _ = self.call("/stadtgruen/spielplatzkontrolle/api/health", base="/stadtgruen/spielplatzkontrolle")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ok")

    def test_public_collection_returns_same_geojson_as_legacy(self):
        from playground_check import service
        from playground_check.django_project import views
        row = {"uuid": "00000000-0000-0000-0000-000000000001", "number": 1,
               "name": "Test", "street_name": "Street", "house_no": "4", "x": 8.7, "y": 47.5}
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql):
                self.sql = sql
                return self
            def fetchall(self): return [row]
        with patch.object(views, "connect", return_value=DB()), patch.object(service, "connect", return_value=DB()):
            migrated = self.call("/Collections/Playgrounds/Items/")
            legacy = self.call_legacy("/Collections/Playgrounds/Items/")
        self.assertEqual(migrated[:2], legacy[:2])

    def call_legacy(self, path):
        from playground_check.server import application
        captured = {}
        environ = {"REQUEST_METHOD": "GET", "SCRIPT_NAME": "", "PATH_INFO": path,
                   "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
                   "SERVER_NAME": "testserver", "SERVER_PORT": "80",
                   "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1"}
        def start_response(status, headers, exc_info=None):
            captured.update(status=status, headers=dict(headers))
        body = b"".join(application(environ, start_response))
        return int(captured["status"].split()[0]), json.loads(body), captured["headers"]

    def test_public_collection_database_error_keeps_original_payload(self):
        from playground_check.django_project import views
        with patch.object(views, "connect", side_effect=RuntimeError("db down")):
            status, payload, _ = self.call("/Collections/Playgrounds/Items/")
        self.assertEqual(status, 200)
        self.assertEqual(payload[0]["errorMessage"], "Unknown critical error.")

    def test_post_collection_is_not_handled_by_drf(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, "legacy_application", return_value=[b"legacy"]) as legacy:
            self.call_raw_post()
            legacy.assert_called_once()

    def call_raw_post(self):
        from playground_check.django_project import wsgi
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/Collections/Playgrounds/Items/"}
        return wsgi.application(env, lambda *_: None)
