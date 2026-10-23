"""Contracts for the shared legacy-to-DRF authentication bridge."""

import io
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
class DRFAccessBridgeTest(unittest.TestCase):
    def test_authorized_user_is_returned_without_http_error(self):
        from playground_check.django_project import wsgi  # noqa: F401; configures Django
        from django.test import RequestFactory
        from playground_check.django_project.access import authenticated_legacy_user
        user = {"mailAddress": "inspector@example.org"}
        check = unittest.mock.Mock(return_value=(user, None))
        request = RequestFactory().get("/Playground/onlynames/", HTTP_AUTHORIZATION="Bearer token")
        actual_user, error = authenticated_legacy_user(request, check)
        self.assertIs(actual_user, user)
        self.assertIsNone(error)
        self.assertEqual(check.call_args.args[0].headers.get("Authorization"), "Bearer token")

    def test_unauthorized_preserves_plain_text_and_status(self):
        from playground_check.django_project import wsgi  # noqa: F401; configures Django
        from django.test import RequestFactory
        from playground_check.django_project.access import authenticated_legacy_user
        from playground_check.http import Response as LegacyResponse
        check = unittest.mock.Mock(return_value=(None, LegacyResponse.text("unauthorized", 401)))
        _, error = authenticated_legacy_user(RequestFactory().get("/Inspection/types/"), check)
        self.assertEqual(error.status_code, 401)
        self.assertEqual(error.content, b"unauthorized")
        self.assertTrue(error["Content-Type"].startswith("text/plain"))

    def test_denied_access_does_not_execute_data_query(self):
        from playground_check.django_project import views
        from playground_check.http import Response as LegacyResponse
        from playground_check.django_project import wsgi
        environ = {
            "REQUEST_METHOD": "GET", "PATH_INFO": "/Playground/onlynames/",
            "QUERY_STRING": "", "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80",
            "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1",
        }
        captured = {}
        def start_response(status, headers, exc_info=None):
            captured["status"] = int(status.split()[0])
        with patch.object(views, "require_user", return_value=(None, LegacyResponse.text("unauthorized", 401))), \
             patch.object(views, "playground_only_names_data") as query:
            body = b"".join(wsgi.application(environ, start_response))
        self.assertEqual(captured["status"], 401)
        self.assertEqual(body, b"unauthorized")
        query.assert_not_called()
