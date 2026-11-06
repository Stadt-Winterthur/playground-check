"""Ensure the private inspection UI does not save drafts offline."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/playground_check"

class OnlineOnlyInspectionTests(unittest.TestCase):
    def test_inspection_form_has_no_offline_controls(self):
        template = (ROOT / "django_project/ui_templates/inspection_editor.html").read_text()
        for marker in ("offline-drafts", "draft-save", "draft-restore", "draft-delete", "python-ui-offline.js"):
            self.assertNotIn(marker, template)
        self.assertIn('method="post"', template)

    def test_local_htmx_integration_remains_available(self):
        ui = (ROOT / "django_project/python_ui.py").read_text()
        layout = (ROOT / "django_project/ui_templates/layout.html").read_text()
        self.assertIn("local_htmx_available", ui)
        self.assertIn("{% if local_htmx_available %}", layout)
        self.assertTrue((ROOT.parents[1] / "tools/install_htmx_local.py").is_file())
