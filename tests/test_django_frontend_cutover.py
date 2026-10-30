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
        body = b"".join(wsgi.application(env, start_response))
        return captured["status"], captured["headers"], body

    def test_legacy_defect_bookmark_redirects_to_native_ui(self):
        status, headers, body = self.call("/defect/267566/1772")
        self.assertEqual(status, 302)
        self.assertIn("/__ui/defect/?tid=1772", headers["Location"])

    def test_swagger_and_static(self):
        for route in ("/swagger", "/swagger/index.html", "/swagger/v1/swagger.json",
                      "/static/manifest.webmanifest"):
            self.assertIn(self.call(route)[0], {200, 302})

    def test_static_traversal_rejected(self):
        self.assertEqual(self.call("/static/../templates/index.html")[0], 404)

    def test_unknown_urls_are_not_spa_routes(self):
        self.assertEqual(self.call("/a-client-route")[0], 404)

    def test_root_opens_native_ui_and_legacy_assets_gone(self):
        self.assertEqual(self.call("/")[1]["Location"], "/__ui/")
        self.assertEqual(self.call("/static/js/app.js")[0], 404)
        self.assertEqual(self.call("/static/css/app.css")[0], 404)
