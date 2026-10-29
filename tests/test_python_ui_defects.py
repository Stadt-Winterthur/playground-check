"""Native Django GUI: defect overview without exposing private records."""
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
class DefectGuiTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()

    def test_anonymous_does_not_query_database(self):
        with patch.object(self.ui, "require_user", return_value=(None, object())), patch.object(self.ui, "connect") as db:
            response = self.ui.defects(self.rf.get("/__ui/defects/"))
        self.assertEqual(response.status_code, 401)
        db.assert_not_called()

    def test_open_filter_escapes_user_data(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.__enter__.return_value = db
        rows = [{"tid": 10, "playground_name": "<script>alert(1)</script>", "description": "Broken", "done_by": None},
                {"tid": 11, "playground_name": "Other", "description": "Fixed", "done_by": 2}]
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)), patch.object(self.ui, "connect", return_value=db), patch.object(self.ui, "defect_overview_rows", return_value=rows):
            response = self.ui.defects(self.rf.get("/__ui/defects/", SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;", response.content)
        self.assertNotIn(b"<script>", response.content)
        self.assertNotIn(b"Fixed", response.content)
        self.assertIn(b"/stadtgruen/spielplatzkontrolle/__ui/defects/", response.content)

    def test_partial_response_filters_done(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.__enter__.return_value = db
        rows = [{"tid": 10, "playground_name": "A", "done_by": None}, {"tid": 11, "playground_name": "B", "done_by": 2}]
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)), patch.object(self.ui, "connect", return_value=db), patch.object(self.ui, "defect_overview_rows", return_value=rows):
            response = self.ui.defects(self.rf.get("/__ui/defects/", {"state": "done"}, HTTP_HX_REQUEST="true"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TID 11", response.content)
        self.assertNotIn(b"TID 10", response.content)
        self.assertNotIn(b"<!doctype", response.content)
