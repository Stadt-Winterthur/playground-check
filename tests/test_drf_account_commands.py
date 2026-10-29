from playground_check import service as legacy_service
"""Step 35: native account commands preserve the established security contract."""
import io
import json
import os
import unittest
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django is not installed")
class AccountCommandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playground_check.django_project.settings")
        django.setup()

    def request(self, method, path, body=None):
        from playground_check.django_project import wsgi
        payload = json.dumps(body).encode() if body is not None else b""
        route, _, query = path.partition("?")
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": route, "SCRIPT_NAME": "",
            "QUERY_STRING": query, "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/json", "wsgi.input": io.BytesIO(payload),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80", "wsgi.url_scheme": "http",
            "SERVER_PROTOCOL": "HTTP/1.1",
        }
        result = {}
        def start(status, headers, exc_info=None):
            result["status"] = int(status.split()[0])
            result["headers"] = dict(headers)
        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path="")):
            result["body"] = b"".join(wsgi.application(environ, start))
        return result

    def test_invalid_login_uses_native_command_not_legacy_handler(self):
        from playground_check import domain_support as service
        with patch.object(legacy_service, "login", side_effect=AssertionError("legacy HTTP handler called")):
            r = self.request("POST", "/Account/Login/", {"mailAddress": "not-an-email", "passPhrase": "pw"})
        self.assertEqual(r["status"], 400)
        self.assertEqual(r["body"], b"Keine oder falsche Login-Daten.")

    def test_administrative_changes_deny_without_database_writes(self):
        from playground_check import domain_support as service
        from playground_check.http import Response
        with patch.object(service, "require_user", return_value=(None, Response.text("unauthorized", 401))), \
             patch.object(service, "connect", side_effect=AssertionError("unexpected database access")), \
             patch.object(legacy_service, "update_user", side_effect=AssertionError("legacy handler called")), \
             patch.object(legacy_service, "delete_user", side_effect=AssertionError("legacy handler called")):
            for method, body in (("PUT", {"mailAddress": "x@example.org"}), ("DELETE", None)):
                r = self.request(method, "/Account/Users/?email=x@example.org", body)
                self.assertEqual(r["status"], 401)
                self.assertEqual(r["body"], b"unauthorized")

    def test_last_active_admin_cannot_be_deactivated(self):
        from playground_check import domain_support as service
        @contextmanager
        def db():
            yield object()
        with patch.object(service, "require_user", return_value=({"role": "administrator"}, None)), \
             patch.object(service, "connect", db), \
             patch.object(service.user_repository, "users_by_email", return_value=[{"role": "administrator"}]), \
             patch.object(service.user_write_repository, "active_admin_count", return_value=1), \
             patch.object(service.user_write_repository, "deactivate_user", side_effect=AssertionError("last admin deactivated")):
            r = self.request("DELETE", "/Account/Users/?email=admin@example.org")
        self.assertEqual(r["status"], 200)
        self.assertEqual(json.loads(r["body"]), {"errorMessage": "SPK-3"})

    def test_login_rate_limit_keeps_retry_after(self):
        from datetime import datetime, timedelta
        from playground_check import domain_support as service
        @contextmanager
        def db():
            yield object()
        now = datetime(2026, 1, 1)
        row = {"last_login_attempt": now - timedelta(seconds=1), "database_time": now}
        with patch.object(service, "connect", db), \
             patch.object(service.user_repository, "user_by_email", return_value=row), \
             patch.object(service.user_write_repository, "record_login_attempt", side_effect=AssertionError("too soon")):
            r = self.request("POST", "/Account/Login/", {"mailAddress": "test@example.org", "passPhrase": "secret"})
        self.assertEqual(r["status"], 429)
        self.assertEqual(r["headers"]["Retry-After"], "2")

    def test_update_user_keeps_legacy_validation_and_no_write(self):
        from playground_check import domain_support as service
        with patch.object(service, "require_user", return_value=({"role": "administrator"}, None)), \
             patch.object(service, "connect", side_effect=AssertionError("invalid payload reached database")):
            r = self.request("PUT", "/Account/Users/", {"mailAddress": "bad", "role": "administrator"})
        self.assertEqual(json.loads(r["body"]), {"errorMessage": "SPK-3"})


if __name__ == "__main__":
    unittest.main()
