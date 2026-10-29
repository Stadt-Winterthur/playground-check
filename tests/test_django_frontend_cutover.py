"""Contract checks for the Django-owned browser routes."""
import io
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    import rest_framework
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django REST Framework not installed")
class DjangoFrontendCutover(unittest.TestCase):
    def call(self, route, method="GET"):
        from playground_check.django_project import wsgi
        captured = {}
        env = {"PATH_INFO": route, "REQUEST_METHOD": method, "QUERY_STRING": "",
               "SCRIPT_NAME": "", "SERVER_NAME": "testserver", "SERVER_PORT": "80",
               "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.url_scheme": "http",
               "wsgi.input": io.BytesIO(), "CONTENT_LENGTH": "0"}
        def start_response(status, headers, *args):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)
        with patch.object(wsgi, "legacy_application", side_effect=AssertionError("legacy called")):
            body = b"".join(wsgi.application(env, start_response))
        return captured["status"], captured["headers"], body

    def test_spa_deep_link(self):
        status, headers, body = self.call("/defect/267566/1772")
        self.assertEqual(status, 200)
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn(b"<html", body.lower())

    def test_swagger_and_static(self):
        for route in ("/swagger", "/swagger/index.html", "/swagger/v1/swagger.json",
                      "/static/manifest.webmanifest"):
            self.assertIn(self.call(route)[0], {200, 302})

    def test_static_traversal_rejected(self):
        self.assertEqual(self.call("/static/../templates/index.html")[0], 404)

    def test_other_spa_url(self):
        self.assertEqual(self.call("/a-client-route")[0], 200)
