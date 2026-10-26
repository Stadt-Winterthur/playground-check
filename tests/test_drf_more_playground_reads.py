"""Compatibility tests for the next incremental read-only DRF routes."""

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
class MorePlaygroundReadsTest(unittest.TestCase):
    def call(self, path, *, method="GET", query="", base=""):
        from playground_check.django_project import wsgi
        captured = {}
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path, "SCRIPT_NAME": "",
            "QUERY_STRING": query, "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
            "SERVER_NAME": "testserver", "SERVER_PORT": "80", "wsgi.url_scheme": "http",
            "SERVER_PROTOCOL": "HTTP/1.1",
        }
        def start_response(status, headers, exc_info=None):
            captured["status"] = int(status.split()[0])
        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path=base)):
            body = b"".join(wsgi.application(environ, start_response))
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = body.decode("utf-8")
        return captured["status"], payload

    def test_only_names_preserves_user_and_query(self):
        from playground_check.django_project import views
        user = {"mailAddress": "inspector@example.org"}
        result = [{"id": 0, "name": "Spielplatz", "playdevices": []}]
        with patch.object(views, "require_user", return_value=(user, None)), \
             patch.object(views, "playground_only_names_data", return_value=result) as fetch:
            self.assertEqual(self.call("/Playground/onlynames/", query="inspectiontype=Keine+Inspektion"), (200, result))
        self.assertEqual(fetch.call_args.args[0], user)
        self.assertEqual(fetch.call_args.args[1]["inspectiontype"], "Keine Inspektion")

    def test_only_names_denies_unauthorized_before_query(self):
        from playground_check.django_project import views
        from playground_check.http import Response as LegacyResponse
        with patch.object(views, "require_user", return_value=(None, LegacyResponse.text("unauthorized", 401))), \
             patch.object(views, "playground_only_names_data") as fetch:
            status, payload = self.call("/Playground/onlynames/")
        self.assertEqual(status, 401)
        self.assertEqual(payload, "unauthorized")
        fetch.assert_not_called()

    def test_device_lookup_preserves_fid_and_missing_device_payload(self):
        from playground_check.django_project import views
        result = {"id": 0, "name": "", "address": "", "playdevices": []}
        with patch.object(views, "require_user", return_value=({"fid": 1}, None)), \
             patch.object(views, "playground_by_device_data", return_value=result) as fetch:
            self.assertEqual(self.call("/Playground/byplaydevice/123/"), (200, result))
        fetch.assert_called_once_with(123)

    def test_device_lookup_preserves_path_base(self):
        from playground_check.django_project import views
        base = "/stadtgruen/spielplatzkontrolle"
        with patch.object(views, "require_user", return_value=({"fid": 1}, None)), \
             patch.object(views, "playground_by_device_data", return_value={"id": 123}):
            self.assertEqual(self.call(base + "/Playground/byplaydevice/123/", base=base), (200, {"id": 123}))

    def test_invalid_device_id_and_post_still_use_legacy(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, "legacy_application", return_value=[b"legacy"]) as legacy:
            for method, path in (("GET", "/Playground/byplaydevice/invalid/"), ("POST", "/Playground/byplaydevice/123/")):
                env = {"REQUEST_METHOD": method, "PATH_INFO": path}
                self.assertEqual(list(wsgi.application(env, lambda *_: None)), [b"legacy"])
        self.assertEqual(legacy.call_count, 2)

    def test_numeric_playground_id_still_legacy(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, "legacy_application", return_value=[b"legacy"]) as legacy:
            env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/Playground/123/"}
            self.assertEqual(list(wsgi.application(env, lambda *_: None)), [b"legacy"])
        legacy.assert_called_once()
