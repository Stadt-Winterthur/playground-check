"""Contract checks for the optional Django migration entry point."""

import io
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")

try:
    import django  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django optional dependency is not installed")
class DjangoBridgeTest(unittest.TestCase):
    def request(self, path):
        from playground_check.django_project.wsgi import application

        captured = {}
        environ = {
            "REQUEST_METHOD": "GET", "SCRIPT_NAME": "", "PATH_INFO": path,
            "QUERY_STRING": "", "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(), "SERVER_NAME": "testserver",
            "SERVER_PORT": "80", "wsgi.url_scheme": "http",
            "SERVER_PROTOCOL": "HTTP/1.1",
        }

        def start_response(status, headers, exc_info=None):
            captured.update(status=status, headers=dict(headers))

        body = b"".join(application(environ, start_response))
        return int(captured["status"].split()[0]), body, captured["headers"]

    def test_django_health_is_available(self):
        from playground_check.django_project import wsgi

        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path="")):
            status, body, _ = self.request("/__django/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["backend"], "django")

    def test_legacy_health_stays_unchanged(self):
        from playground_check.django_project import wsgi

        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path="")):
            status, body, _ = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(set(json.loads(body)), {"status", "version"})

    def test_legacy_deep_link_redirects_to_native_view(self):
        from playground_check.django_project import wsgi

        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path="")):
            status, body, _ = self.request("/defect/267566/1772")
        self.assertEqual(status, 302)
        self.assertEqual(_["Location"], "/defect/?tid=1772")
