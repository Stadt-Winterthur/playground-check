"""Structural regression tests for inspection criteria and image form."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project'

class FinalGuiCriteriaTests(unittest.TestCase):
    def test_criteria_are_rendered_and_revalidated(self):
        source = (ROOT / 'python_ui.py').read_text()
        template = (ROOT / 'ui_templates/inspection_editor.html').read_text()
        self.assertIn('generalInspectionCriteria', source)
        self.assertIn('mainFallProtectionInspectionCriteria', source)
        self.assertIn('secondaryFallProtectionInspectionCriteria', source)
        self.assertIn('criterion["check"]', source)
        self.assertIn('inspection_done_', template)
        self.assertIn('maintenance_done_', template)
    def test_photo_upload_has_auth_and_csrf(self):
        source = (ROOT / 'python_ui_workflows.py').read_text()
        self.assertIn('def playdevice_photo', source)
        self.assertIn("_guard(request, {'inspector', 'administrator'})", source)
        self.assertIn('@csrf_protect', source)
