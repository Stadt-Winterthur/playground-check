"""The Internet-facing test UI is private, including partial HTMX requests."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    from django.test import RequestFactory
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django not installed")
class InternetFacingUISecurityTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()

    def test_every_page_denies_anonymous_before_repository_access(self):
        paths = (
            ("home", "/__ui/"),
            ("playgrounds", "/__ui/playgrounds/"),
            ("workspace", "/__ui/workspace/"),
            ("assigned_playgrounds", "/__ui/assigned/"),
            ("playground_detail", "/__ui/detail/?name=Sensitive"),
            ("defects", "/__ui/defects/"),
        )
        for name, url in paths:
            for partial in (False, True):
                with self.subTest(view=name, partial=partial), \
                     patch.object(self.ui, "require_user", return_value=(None, object())), \
                     patch.object(self.ui, "connect") as database, \
                     patch.object(self.ui, "playground_only_names_data") as names, \
                     patch.object(self.ui, "playground_by_name_data") as detail:
                    kwargs = {"HTTP_HX_REQUEST": "true"} if partial else {}
                    response = getattr(self.ui, name)(self.rf.get(url, **kwargs))
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response["Cache-Control"], "no-store")
                    self.assertIn("Cookie", response["Vary"])
                    self.assertNotIn(b"Sensitive", response.content)
                    database.assert_not_called()
                    names.assert_not_called()
                    detail.assert_not_called()

    def test_authentication_error_fails_closed_without_query(self):
        with patch.object(self.ui, "require_user", side_effect=RuntimeError("secret auth details")), \
             patch.object(self.ui, "connect") as database:
            response = self.ui.playgrounds(self.rf.get("/__ui/playgrounds/"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secret auth details", response.content)
        database.assert_not_called()

    def test_authenticated_home_is_private_and_prefix_safe(self):
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)):
            response = self.ui.home(self.rf.get("/__ui/", SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn(b"/stadtgruen/spielplatzkontrolle/__ui/", response.content)
