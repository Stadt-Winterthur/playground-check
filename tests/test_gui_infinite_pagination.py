"""Verify bounded SQL and progressive-enhancement pagination, without a live DB."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check'

class InfinitePaginationTests(unittest.TestCase):
    def test_three_results_use_htmx_revealed_and_limit(self):
        for name in ('assigned_rows.html', 'defects_rows.html'):
            content = (ROOT / 'django_project/ui_templates' / name).read_text()
            self.assertIn('hx-trigger="revealed"', content)
            self.assertIn('hx-swap="outerHTML"', content)
            self.assertIn('append=1', content)
        views = (ROOT / 'django_project/python_ui.py').read_text()
        self.assertIn('size = 20', views)
        self.assertIn('gui_playground_page(db,', views)
        self.assertIn('gui_defect_page(db,', views)

    def test_sql_is_bounded_and_parameterized(self):
        sql = (ROOT / 'remaining_reads_repository.py').read_text()
        for fn in ('gui_playground_page', 'gui_defect_page'):
            self.assertIn('def ' + fn, sql)
        self.assertGreaterEqual(sql.count('LIMIT %s OFFSET %s'), 3)
        self.assertIn('ikt.fid_kontrolleur', sql)
        self.assertIn('ina.value=%s', sql)
        self.assertIn('AND done_by IS NULL', sql)

    def test_search_keeps_full_page_navigation(self):
        for name in ('assigned.html', 'defects.html'):
            s = (ROOT / 'django_project/ui_templates' / name).read_text()
            self.assertIn('method="get"', s)
            self.assertIn('hx-target=', s)
            self.assertIn('hx-replace-url="true"', s)
