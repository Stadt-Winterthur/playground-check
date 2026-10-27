"""Compatibility checks for DRF inspection and playdevice routing."""
import os
import unittest
from unittest.mock import patch

from playground_check.http import Response as LegacyResponse

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    views = None
else:
    from playground_check.django_project import wsgi, inspection_device_views as views


@unittest.skipIf(views is None, "Django REST Framework is not installed")
class DRFInspectionDeviceMigrationTests(unittest.TestCase):
    def test_inspection_creation_retains_json_response_and_handler(self):
        from django.test import RequestFactory
        with patch.object(views.service, "post_inspections", return_value=LegacyResponse.json({"errorMessage": "SPK-3"})) as handler:
            response = views.create_inspection(RequestFactory().post("/Inspection/", data="{}", content_type="application/json"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'{"errorMessage":"SPK-3"}')
            handler.assert_called_once()

    def test_playdevice_post_put_forward_to_original_handlers(self):
        from django.test import RequestFactory
        for method, name in (("POST", "save_playdevice"), ("PUT", "exchange_playdevice_picture")):
            with self.subTest(method=method), patch.object(views.service, name, return_value=LegacyResponse.json({"errorMessage": ""})) as handler:
                request = getattr(RequestFactory(), method.lower())("/Playdevice/", data='{"FID":3}', content_type="application/json")
                response = views.playdevice(request)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(handler.call_args.args[0].json()["fid"], 3)

    def test_picture_get_put_preserve_fid_and_binary_response(self):
        from django.test import RequestFactory
        with patch.object(views.service, "get_playdevice_picture", return_value=LegacyResponse.file(b"abc", "image/jpeg")) as handler:
            response = views.playdevice_picture(RequestFactory().get("/Playdevice/12/Picture/"), fid=12)
            self.assertEqual((response.status_code, response.content, response["Content-Type"]), (200, b"abc", "image/jpeg"))
            self.assertEqual(handler.call_args.args[0].params["fid"], "12")
        with patch.object(views.service, "put_playdevice_picture", return_value=LegacyResponse.text("Unauthorized", 401)) as handler:
            response = views.playdevice_picture(RequestFactory().put("/Playdevice/12/Picture/", data="{}", content_type="application/json"), fid=12)
            self.assertEqual((response.status_code, response.content), (401, b"Unauthorized"))
            handler.assert_called_once()

    def test_wsgi_routes_only_supported_methods_to_django(self):
        from io import BytesIO
        cases = [
            ("POST", "/Inspection/", True), ("GET", "/Inspection/", False),
            ("POST", "/Playdevice/", True), ("PUT", "/playdevice", True),
            ("GET", "/Playdevice/", False),
            ("GET", "/Playdevice/42/Picture/", True),
            ("PUT", "/playdevice/42/picture", True),
            ("DELETE", "/Playdevice/42/Picture/", False),
        ]
        for method, path, migrated in cases:
            with self.subTest(method=method, path=path):
                with patch.object(wsgi, "_django_application", return_value=[b"django"]) as django_app, patch.object(wsgi, "legacy_application", return_value=[b"legacy"]) as legacy_app:
                    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": BytesIO(b"")}
                    result = wsgi.application(environ, lambda *a: None)
                    self.assertEqual(result, [b"django"] if migrated else [b"legacy"])
                    self.assertEqual(django_app.called, migrated)
                    self.assertEqual(legacy_app.called, not migrated)
