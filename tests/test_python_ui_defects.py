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
            response = self.ui.defects(self.rf.get("/defects/"))
        self.assertEqual(response.status_code, 401)
        db.assert_not_called()

    def test_open_filter_escapes_user_data(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.__enter__.return_value = db
        rows = [{"tid": 10, "playground_name": "<script>alert(1)</script>", "description": "Broken", "done_by": None},
                {"tid": 11, "playground_name": "Other", "description": "Fixed", "done_by": 2}]
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)), patch.object(self.ui, "connect", return_value=db), patch("playground_check.remaining_reads_repository.gui_defect_page", side_effect=lambda db, query, state, offset, limit: [r for r in rows if (state == "all" or (r["done_by"] is None) == (state == "open"))][:limit]):
            response = self.ui.defects(self.rf.get("/defects/", SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;script&gt;", response.content)
        self.assertNotIn(b"<script>", response.content)
        self.assertNotIn(b"Fixed", response.content)
        self.assertIn(b"/stadtgruen/spielplatzkontrolle/defects/", response.content)

    def test_partial_response_filters_done(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.__enter__.return_value = db
        rows = [{"tid": 10, "playground_name": "A", "done_by": None}, {"tid": 11, "playground_name": "B", "done_by": 2}]
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)), patch.object(self.ui, "connect", return_value=db), patch("playground_check.remaining_reads_repository.gui_defect_page", side_effect=lambda db, query, state, offset, limit: [r for r in rows if (state == "all" or (r["done_by"] is None) == (state == "open"))][:limit]):
            response = self.ui.defects(self.rf.get("/defects/", {"state": "done"}, HTTP_HX_REQUEST="true"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tid=11', response.content)
        self.assertIn(b'Mangel-Nummer 11', response.content)
        self.assertNotIn(b'TID', response.content)
        self.assertNotIn(b'tid=10', response.content)
        self.assertNotIn(b"<!doctype", response.content)

    def test_overview_and_appended_rows_show_number_without_technical_ids(self):
        from datetime import date
        from html.parser import HTMLParser
        from unittest.mock import MagicMock

        class TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.cells = []
                self.links = []
                self.in_cell = False
            def handle_starttag(self, tag, attrs):
                if tag == 'td':
                    self.cells.append('')
                    self.in_cell = True
                if tag == 'a':
                    self.links.append(dict(attrs).get('href', ''))
            def handle_endtag(self, tag):
                if tag == 'td':
                    self.in_cell = False
            def handle_data(self, text):
                self.text.append(text)
                if self.in_cell:
                    self.cells[-1] += text

        row = {'tid': 2452, 'playdevice_fid': 858534, 'playground_name': 'Alpenblick Anlage',
               'playdevice_type': 'Tischtennistisch', 'priority': 1, 'date_creation': date(2026, 7, 8),
               'description': 'Testmangel', 'assignment_overdue': True,
               'responsible_body_id': 3, 'responsible_user_name': 'Edgar Butwilowski'}
        db = MagicMock()
        db.__enter__.return_value = db
        for params, headers in [({}, {}), ({'page': '2', 'append': '1'}, {'HTTP_HX_REQUEST': 'true'})]:
            with self.subTest(params=params), patch.object(self.ui, 'require_user', return_value=({'fid': 1}, None)), \
                 patch.object(self.ui, 'connect', return_value=db), \
                 patch('playground_check.remaining_reads_repository.gui_defect_page', return_value=[row]):
                response = self.ui.defects(self.rf.get('/defects/', params,
                    SCRIPT_NAME='/stadtgruen/spielplatzkontrolle', **headers))
            self.assertEqual(response.status_code, 200)
            parsed = TableParser()
            parsed.feed(response.content.decode())
            visible = ''.join(parsed.text)
            self.assertNotIn('Mangel erfassen', visible)
            self.assertNotIn('Geräte-FID', visible)
            self.assertNotIn('TID', visible)
            self.assertNotIn('858534', visible)
            self.assertIn('Mangel-Nummer', visible)
            self.assertEqual(len(parsed.cells), 9)
            self.assertEqual(parsed.cells[0], '2452')
            self.assertEqual(parsed.cells[4], '08.07.2026')
            self.assertIn('Edgar Butwilowski', parsed.cells[6])
            self.assertIn('/stadtgruen/spielplatzkontrolle/defect/?tid=2452', parsed.links)
