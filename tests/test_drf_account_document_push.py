"""Step 33: method-aware routing, and byte-exact service dispatch."""
import io
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")

try:
    import django  # noqa: F401
except ImportError:
    django = None

from playground_check.django_project.route_registry import migrated_path


class Step33RoutingTests(unittest.TestCase):
    def test_migrated_methods_and_case_variants(self):
        cases = [
            ("POST", "/account/login", "/Account/Login/"),
            ("POST", "/Account/Logout/", "/Account/Logout/"),
            ("GET", "/account/me", "/Account/Me/"),
            ("GET", "/account/users/assignable/", "/Account/Users/Assignable/"),
            ("GET", "/Account/Users", "/Account/Users/"),
            ("PUT", "/Account/Users/", "/Account/Users/"),
            ("DELETE", "/Account/Users/", "/Account/Users/"),
            ("POST", "/document", "/Document/"),
            ("GET", "/document/123", "/Document/123/"),
            ("DELETE", "/document/123/", "/Document/123/"),
            ("PUT", "/document/123/name", "/Document/123/Name/"),
            ("POST", "/pushsubscription/register", "/PushSubscription/Register/"),
            ("DELETE", "/pushsubscription/unregister", "/PushSubscription/Unregister/"),
            ("GET", "/pushsubscription/me", "/PushSubscription/Me/"),
        ]
        for method, path, expected in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(migrated_path(path, method), expected)

    def test_unsupported_methods_and_invalid_ids_remain_legacy(self):
        cases = [
            ("GET", "/Account/Login/"),
            ("POST", "/Account/Users/"),
            ("POST", "/Document/123/"),
            ("PUT", "/Document/123/"),
            ("GET", "/Document/"),
            ("GET", "/Document/abc/"),
            ("PUT", "/Document/abc/Name/"),
            ("DELETE", "/PushSubscription/Me/"),
            ("POST", "/PushSubscription/Unregister/"),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assertIsNone(migrated_path(path, method))


@unittest.skipUnless(django is not None, "Django is not installed")
class Step33DispatchTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import wsgi
        self.wsgi = wsgi
        self.base_patcher = patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path=""))
        self.base_patcher.start()
        self.addCleanup(self.base_patcher.stop)

    def request(self, method, path, body=b"", query=""):
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path, "SCRIPT_NAME": "",
            "QUERY_STRING": query, "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json", "wsgi.input": io.BytesIO(body),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80",
            "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1",
        }
        captured = {}
        def start_response(status, headers, exc_info=None):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)
        payload = b"".join(self.wsgi.application(environ, start_response))
        return captured["status"], captured["headers"], payload

    def test_post_login_preserves_json_body_and_status(self):
        from playground_check import service
        from playground_check.django_project import account_commands
        from playground_check.django_project.legacy_adapter import to_legacy_request
        from django.http import HttpResponse
        def handler(req):
            self.assertEqual(to_legacy_request(req).json(), {"mailAddress": "test@example.org"})
            return HttpResponse(b'{"errorMessage":"invalid credentials"}', status=401, content_type="application/json")
        with patch.object(service, "login", side_effect=AssertionError("legacy login invoked")), \
                patch.object(account_commands, "login", side_effect=handler):
            status, headers, body = self.request("POST", "/account/login", b'{"mailAddress":"test@example.org"}')
        self.assertEqual(status, 401)
        self.assertEqual(body, b'{"errorMessage":"invalid credentials"}')

    def test_document_binary_response_keeps_fid_and_content_type(self):
        from playground_check import service
        from playground_check.http import Response
        def handler(req):
            self.assertEqual(req.params["fid"], "77")
            self.assertEqual(req.query["type"], "certificate")
            return Response.file(b"%PDF-1.5\n\x00payload", "application/pdf")
        with patch.object(service, "get_document", side_effect=handler):
            status, headers, body = self.request("GET", "/document/77", query="type=certificate")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/pdf"))
        self.assertEqual(body, b"%PDF-1.5\n\x00payload")

    def test_logout_preserves_empty_body_and_cookie(self):
        from playground_check import service
        from playground_check.http import Response
        response = Response(b"", 204)
        response.headers.append(("Set-Cookie", "auth=; Max-Age=0; Path=/"))
        with patch.object(service, "logout", return_value=response):
            status, headers, body = self.request("POST", "/account/logout")
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
