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
    def test_inspection_creation_uses_native_command(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = views.inspection_device_commands
        with patch.object(native, "create_inspection", return_value=HttpResponse(b'{"errorMessage":"SPK-3"}', content_type="application/json")) as handler:
            response = views.create_inspection(RequestFactory().post("/Inspection/", data="{}", content_type="application/json"))
            self.assertEqual(response.content, b'{"errorMessage":"SPK-3"}')
            handler.assert_called_once()

    def test_playdevice_post_put_use_native_commands(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = views.inspection_device_commands
        for method, name in (("POST", "save_playdevice"), ("PUT", "exchange_playdevice_picture")):
            with self.subTest(method=method), patch.object(native, name, return_value=HttpResponse(b'{"errorMessage":""}', content_type="application/json")) as handler:
                request = getattr(RequestFactory(), method.lower())("/Playdevice/", data='{"FID":3}', content_type="application/json")
                response = views.playdevice(request)
                self.assertEqual(response.status_code, 200)
                handler.assert_called_once()

    def test_picture_get_put_preserve_fid_and_binary_response(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = views.inspection_device_commands
        with patch.object(native, "get_playdevice_picture", return_value=HttpResponse(b"abc", content_type="image/jpeg")) as handler:
            response = views.playdevice_picture(RequestFactory().get("/Playdevice/12/Picture/"), fid=12)
            self.assertEqual((response.status_code, response.content, response["Content-Type"]), (200, b"abc", "image/jpeg"))
            self.assertEqual(handler.call_args.args[1], 12)
        with patch.object(native, "put_playdevice_picture", return_value=HttpResponse(b"Unauthorized", status=401)) as handler:
            response = views.playdevice_picture(RequestFactory().put("/Playdevice/12/Picture/", data="{}", content_type="application/json"), fid=12)
            self.assertEqual((response.status_code, response.content), (401, b"Unauthorized"))
            handler.assert_called_once()

    def test_dry_run_get_picture_never_accesses_database(self):
        from django.test import RequestFactory
        native = views.inspection_device_commands
        with patch.object(native.service, "connect", side_effect=AssertionError("database touched")):
            response = views.playdevice_picture(RequestFactory().get("/Playdevice/12/Picture/?dryRun=true"), fid=12)
        self.assertEqual((response.status_code, response.content), (200, b""))

    def test_unauthorized_inspection_never_accesses_database(self):
        from django.test import RequestFactory
        native = views.inspection_device_commands
        with patch.object(native.service, "current_user", return_value=None), patch.object(native.service, "connect", side_effect=AssertionError("database touched")):
            response = views.create_inspection(RequestFactory().post("/Inspection/", data="[]", content_type="application/json"))
        self.assertEqual((response.status_code, response.content), (401, b"Unauthorized"))

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
                with patch.object(wsgi, "_django_application", return_value=[b"django"]) as django_app:
                    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": BytesIO(b"")}
                    result = wsgi.application(environ, lambda *a: None)
                    self.assertEqual(result, [b"django"])
                    django_app.assert_called_once()
