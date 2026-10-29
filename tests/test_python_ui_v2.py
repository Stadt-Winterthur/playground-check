"""Python GUI: auth isolation, safe templates and reverse-proxy links."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    from django.test import RequestFactory
except ImportError:
    django = None

@unittest.skipUnless(django is not None, "Django not available")
class PythonUIV2Tests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui as ui
        self.ui = ui
        self.rf = RequestFactory()

    def test_unidentified_user_never_queries_private_records(self):
        with patch.object(self.ui, "require_user", return_value=(None, object())), \
             patch.object(self.ui, "playground_only_names_data") as fetch:
            response = self.ui.assigned_playgrounds(self.rf.get("/__ui/assigned/"))
        self.assertEqual(response.status_code, 401)
        fetch.assert_not_called()

    def test_reverse_proxy_navigation(self):
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)):
            response = self.ui.home(self.rf.get("/__ui/", SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/stadtgruen/spielplatzkontrolle/__ui/workspace/", response.content)

    def test_authenticated_lookup_escapes_names(self):
        with patch.object(self.ui, "require_user", return_value=({"mailAddress": "a@example.ch"}, None)), \
             patch.object(self.ui, "playground_only_names_data", return_value=[{"name": "<script>alert(1)</script>"}]):
            response = self.ui.assigned_playgrounds(self.rf.get("/__ui/assigned/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>", response.content)
        self.assertIn(b"&lt;script&gt;", response.content)

    def test_no_unbounded_private_search_input(self):
        with patch.object(self.ui, "require_user", return_value=({"mailAddress": "a@example.ch"}, None)), \
             patch.object(self.ui, "playground_only_names_data", return_value=[]) as fetch:
            response = self.ui.assigned_playgrounds(self.rf.get("/__ui/assigned/", {"q":"a"*1000, "inspectiontype":"b"*500}))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(fetch.call_args.args[1]["inspectiontype"]), 100)
