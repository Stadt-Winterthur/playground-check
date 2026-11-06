import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project'

class GUIWorkflowStructureTests(unittest.TestCase):
    def test_all_mutations_have_auth_without_csrf_tokens(self):
        text = (ROOT / 'python_ui_workflows.py').read_text()
        self.assertNotIn('@csrf_protect', text)
        self.assertNotIn('get_token(', text)
        self.assertIn('ui._private(request)', text)
        self.assertIn('document_commands.create_document', text)
    def test_routes_declared(self):
        text = (ROOT / 'urls.py').read_text()
        for path in ('path("login/"', 'path("defect/edit/"', 'path("device/edit/"', 'path("document/upload/"', 'path("admin/users/"'):
            self.assertIn(path, text)
