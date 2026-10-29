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

    def test_numeric_playground_id_uses_native_read(self):
        from playground_check.django_project import views
        with patch.object(views, "require_user", return_value=({"fid": 1}, None)), \
             patch.object(views, "legacy_settings", replace(views.legacy_settings, compatibility_bugs=False)), \
             patch.object(views, "playground_by_id_data", return_value={"id": 123}) as fetch:
            self.assertEqual(self.call("/Playground/123/", query="withdefects=true"), (200, {"id": 123}))
        fetch.assert_called_once_with(123, {"withdefects": "true"})

    def test_numeric_playground_id_preserves_compatibility_bug(self):
        from playground_check.django_project import views
        with patch.object(views, "require_user", return_value=({"fid": 1}, None)), \
             patch.object(views, "legacy_settings", replace(views.legacy_settings, compatibility_bugs=True)), \
             patch.object(views, "playground_by_id_data") as fetch:
            self.assertEqual(self.call("/Playground/123/"), (500, "Index was outside the bounds of the array."))
        fetch.assert_not_called()

    def test_malformed_id_uses_drf_and_other_methods_stay_legacy(self):
        from playground_check.django_project import views, wsgi
        from playground_check.django_project.route_registry import migrated_path
        malformed = "/Playground/123&inspectiontype=x"
        self.assertEqual(migrated_path(malformed, "GET"), "/Playground/123&inspectiontype=x/")
        with patch.object(wsgi, "legacy_application", return_value=[b"legacy"]) as legacy, \
             patch.object(views, "require_user", return_value=({"fid": 1}, None)):
            status, payload = self.call(malformed)
            self.assertEqual(status, 400)
            self.assertEqual(payload["status"], 400)
            self.assertIn("123&inspectiontype=x", payload["errors"]["id"][0])
            self.assertEqual(list(wsgi.application(
                {"REQUEST_METHOD": "POST", "PATH_INFO": "/Playground/123/"},
                lambda *_: None,
            )), [b"legacy"])
        legacy.assert_called_once()

@unittest.skipUnless(django is not None, "Django REST Framework not installed")
class PlaygroundIdPayloadTest(unittest.TestCase):
    def test_id_query_reuses_detail_builder(self):
        from playground_check import service
        from unittest.mock import MagicMock
        db = MagicMock()
        manager = MagicMock()
        manager.__enter__.return_value = db
        with patch.object(service, "connect", return_value=manager), \
             patch.object(service.remaining_reads_repository, "playground_by_fid", return_value={"fid": 123}) as get_row, \
             patch.object(service, "_playground_result", return_value={"id": 123}) as build:
            self.assertEqual(service.playground_by_id_data(123, {"inspectiontype": "Hauptinspektion", "withdefects": "true", "withinspections": "false"}), {"id": 123})
        get_row.assert_called_once_with(db, 123)
        build.assert_called_once_with(db, {"fid": 123}, "Hauptinspektion", True, False)

    def test_missing_id_is_null_without_detail_builder(self):
        from playground_check import service
        from unittest.mock import MagicMock
        manager = MagicMock()
        manager.__enter__.return_value = MagicMock()
        with patch.object(service, "connect", return_value=manager), \
             patch.object(service.remaining_reads_repository, "playground_by_fid", return_value=None), \
             patch.object(service, "_playground_result") as build:
            self.assertIsNone(service.playground_by_id_data(999, {}))
        build.assert_not_called()
