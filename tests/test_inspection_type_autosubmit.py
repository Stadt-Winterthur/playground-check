"""Regression: selection is submitted as a normal GET navigation.

A normal GET preserves browser history, works without HTMX-specific events,
and keeps the backend's assignment filtering intact.
"""
import unittest
from pathlib import Path


TEMPLATE = (Path(__file__).resolve().parents[1]
            / "src/playground_check/django_project/ui_templates/assigned.html")


class InspectionTypeAutoSubmitTests(unittest.TestCase):
    def test_inspection_selection_submits_on_change(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('name="inspectiontype" required hx-get=', html)
        self.assertIn('hx-trigger="change"', html)
        self.assertIn('hx-push-url="true"', html)
        self.assertNotIn('onchange="', html)
        self.assertIn('Inspektionsart auswählen', html)
        self.assertIn('method="get"', html)
        self.assertIn('name="mode" value="inspection"', html)

    def test_no_forced_autosubmit_on_device_selector(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('{% if inspection_mode %}', html)
        self.assertNotIn('location.href=', html)
        self.assertNotIn('history.replaceState(', html)
