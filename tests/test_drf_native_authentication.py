"""Native DRF authentication compatibility and single database revalidation."""

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
class NativeAuthenticationTest(unittest.TestCase):
    def request(self, path="/Playground/onlynames/"):
        from playground_check.django_project import wsgi
        captured = {}
        environ = {
            "REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": "",
            "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80",
            "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1",
        }
        def start_response(status, headers, exc_info=None):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)
        body = b"".join(wsgi.application(environ, start_response))
        return captured["status"], captured["headers"], body

    def test_authenticated_user_is_verified_only_once(self):
        from playground_check.django_project import views
        user = {"fid": 5, "mailAddress": "test@example.org", "role": "Kontrolleur"}
        with patch.object(views, "require_user", return_value=(user, None)) as authenticate, \
             patch.object(views, "playground_only_names_data", return_value=[]) as fetch:
            status, _, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [])
        authenticate.assert_called_once()
        fetch.assert_called_once_with(user, {})

    def test_unauthorized_response_stays_plaintext_and_no_query(self):
        from playground_check.django_project import views
        from playground_check.http import Response as LegacyResponse
        with patch.object(views, "require_user", return_value=(None, LegacyResponse.text("unauthorized", 401))) as authenticate, \
             patch.object(views, "playground_only_names_data") as fetch:
            status, headers, body = self.request()
        self.assertEqual(status, 401)
        self.assertEqual(body, b"unauthorized")
        self.assertTrue(headers["Content-Type"].startswith("text/plain"))
        authenticate.assert_called_once()
        fetch.assert_not_called()

    def test_public_endpoint_does_not_authenticate(self):
        from playground_check.django_project import views
        with patch.object(views, "require_user") as authenticate:
            status, _, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")
        authenticate.assert_not_called()
