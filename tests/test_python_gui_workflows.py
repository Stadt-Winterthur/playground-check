import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project'

class GUIWorkflowStructureTests(unittest.TestCase):
    def test_all_mutations_have_csrf_and_auth(self):
        text = (ROOT / 'python_ui_workflows.py').read_text()
        self.assertEqual(text.count('@csrf_protect'), 5)
        self.assertIn('ui._private(request)', text)
        self.assertIn('document_commands.create_document', text)
    def test_routes_declared(self):
        text = (ROOT / 'urls.py').read_text()
        for path in ('__ui/login/', '__ui/defect/edit/', '__ui/device/edit/', '__ui/document/upload/', '__ui/admin/users/'):
            self.assertIn(path, text)
