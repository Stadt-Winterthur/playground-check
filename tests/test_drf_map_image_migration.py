"""Contract checks for the unauthenticated map-image DRF migration."""
import base64
import io
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.error import HTTPError

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django REST Framework not installed")
class MapImageMigrationTests(unittest.TestCase):
    def request(self, path, query="", base=""):
        from playground_check.django_project import wsgi
        meta = {"REQUEST_METHOD": "GET", "PATH_INFO": path,
                "QUERY_STRING": query, "CONTENT_LENGTH": "0", "wsgi.input": io.BytesIO(),
                "SERVER_NAME": "testserver", "SERVER_PORT": "80",
                "wsgi.url_scheme": "http", "SERVER_PROTOCOL": "HTTP/1.1"}
        capture = {}
        def response(status, headers, exc_info=None):
            capture["status"] = int(status.split()[0])
            capture["headers"] = dict(headers)
        with patch.object(wsgi, "legacy_settings", replace(wsgi.legacy_settings, base_path=base)):
            body = b"".join(wsgi.application(meta, response))
        return capture["status"], json.loads(body), capture["headers"]

    def test_zero_coordinates_do_not_contact_wms_and_are_public(self):
        from playground_check import map_image_queries
        with patch.object(map_image_queries, "urlopen") as get:
            for path in ("/playground/mapimage", "/Playground/MAPIMAGE/"):
                status, payload, _ = self.request(path, "x=0&y=100")
                self.assertEqual((status, payload), (200, ""))
            get.assert_not_called()

    def test_upstream_bytes_base64_and_query_contract(self):
        from playground_check import map_image_queries
        raw = b"\x89PNG\r\n\x1a\nexample"
        with patch.object(map_image_queries, "urlopen", return_value=io.BytesIO(raw)) as get:
            status, payload, headers = self.request("/Playground/mapimage/", "x=2600000&y=1200000")
        self.assertEqual((status, payload), (200, base64.b64encode(raw).decode("ascii")))
        self.assertIn("application/json", headers["Content-Type"])
        url = get.call_args.args[0]
        self.assertIn("BBOX=2599990.0,1199995.0,2600010.0,1200005.0", url)
        self.assertIn("WIDTH=800&HEIGHT=400", url)
        self.assertEqual(get.call_args.kwargs, {"timeout": 20})

    def test_http_error_body_retained_as_base64(self):
        from playground_check import map_image_queries
        body = b"upstream WMS exception"
        error = HTTPError("http://example.org", 403, "Forbidden", {}, io.BytesIO(body))
        with patch.object(map_image_queries, "urlopen", side_effect=error):
            status, payload, _ = self.request("/Playground/mapimage", "x=1&y=2")
        self.assertEqual((status, payload), (200, base64.b64encode(body).decode("ascii")))

    def test_reverse_proxy_path_base(self):
        from playground_check import map_image_queries
        base = "/stadtgruen/spielplatzkontrolle"
        with patch.object(map_image_queries, "urlopen") as get:
            status, payload, _ = self.request(base + "/Playground/mapimage", "x=0&y=0", base)
        self.assertEqual((status, payload), (200, ""))
        get.assert_not_called()

    def test_other_methods_still_legacy(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, "_django_application", return_value=[b"django"]) as app:
            result = list(wsgi.application({"REQUEST_METHOD": "POST", "PATH_INFO": "/Playground/mapimage"}, lambda *_: None))
        self.assertEqual(result, [b"django"])
        self.assertEqual(app.call_args.args[0]["PATH_INFO"], "/Playground/mapimage/")
