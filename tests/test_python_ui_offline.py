"""Contract checks for opt-in offline inspection drafts."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check'

class OfflineUIContractTests(unittest.TestCase):
    def test_private_inspection_form_has_explicit_draft_controls(self):
        template = (ROOT/'django_project/ui_templates/inspection_editor.html').read_text()
        self.assertIn('id="draft-save"', template)
        self.assertIn('id="draft-restore"', template)
        self.assertIn('id="draft-delete"', template)
        self.assertIn('id="inspection-form"', template)
    def test_draft_script_never_autosubmits_or_persists_auth_tokens(self):
        script = (ROOT/'static/js/python-ui-offline.js').read_text()
        self.assertIn("indexedDB.open", script)
        self.assertIn("'csrfmiddlewaretoken'", script)
        self.assertNotIn('form.submit(', script)
        self.assertNotIn('fetch(', script)
    def test_htmx_is_only_loaded_when_local_file_exists(self):
        ui = (ROOT/'django_project/python_ui.py').read_text()
        layout = (ROOT/'django_project/ui_templates/layout.html').read_text()
        self.assertIn('local_htmx_available', ui)
        self.assertIn('{% if local_htmx_available %}', layout)
