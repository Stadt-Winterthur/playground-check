"""Regression tests for the native playground document management UI."""
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.http import HttpResponse
    from django.test import RequestFactory
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django not available")
class PlaygroundDocumentUITests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui, python_ui_workflows
        self.ui = python_ui
        self.workflows = python_ui_workflows
        self.rf = RequestFactory()
        self.payload = {
            'id': 17,
            'name': 'Alpenblick Anlage',
            'address': 'Beispielweg 1',
            'playdevices': [],
            'inspectionTypeOptions': ['Visuelle Inspektion'],
            'documentsOfAcceptance': [{'fid': 45, 'name': 'Test'}],
            'certificateDocuments': [{'fid': 46, 'name': 'Zertifikat'}],
        }

    def test_detail_view_replaces_old_document_box_and_hides_defect_overview_button(self):
        request = self.rf.get('/__ui/detail/?name=Alpenblick%20Anlage')
        with patch.object(self.ui, '_private', return_value=({'role': 'administrator'}, None)), \
             patch.object(self.ui, 'playground_by_name_data', return_value=self.payload):
            response = self.ui.playground_detail(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('Mängelübersicht', content)
        self.assertIn('Abnahmen und Zertifikate', content)
        self.assertIn('/__ui/detail/documents/', content)
        self.assertIn('Weiteres Dokument hochladen', content)
        self.assertIn('Verwalten', content)

    def test_non_admin_sees_documents_without_management_forms(self):
        request = self.rf.get('/__ui/detail/?name=Alpenblick%20Anlage')
        with patch.object(self.ui, '_private', return_value=({'role': 'inspector'}, None)), \
             patch.object(self.ui, 'playground_by_name_data', return_value=self.payload):
            response = self.ui.playground_detail(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Abnahmen und Zertifikate', content)
        self.assertNotIn('Weiteres Dokument hochladen', content)
        self.assertNotIn('Löschen', content)

    def test_upload_action_redirects_back_to_detail_with_notice(self):
        upload = SimpleUploadedFile('abnahme.pdf', b'%PDF-1.4\n%', content_type='application/pdf')
        request = self.rf.post('/__ui/detail/documents/', {
            'action': 'upload',
            'documentType': 'abnahme',
            'playgroundId': '17',
            'documentName': 'Schlussabnahme',
            'name': 'Alpenblick Anlage',
            'inspectiontype': 'Visuelle Inspektion',
            'document': upload,
            'csrfmiddlewaretoken': 'a' * 32,
        })
        request.COOKIES['csrftoken'] = 'a' * 32
        api_response = HttpResponse(json.dumps({'fid': 99, 'name': 'Schlussabnahme'}), content_type='application/json')
        with patch.object(self.workflows, '_guard', return_value=({'role': 'administrator'}, None)), \
             patch.object(self.workflows, '_native', return_value=api_response) as native:
            response = self.workflows.playground_document_action(request)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/__ui/detail/?name=Alpenblick+Anlage&tab=documents&inspectiontype=Visuelle+Inspektion&notice=', response['Location'])
        payload = native.call_args.args[2]
        self.assertEqual(payload['playgroundId'], 17)
        self.assertEqual(payload['type'], 'abnahme')
        self.assertEqual(payload['name'], 'Schlussabnahme')
        self.assertTrue(payload['contentBase64'])

    def test_rename_action_propagates_document_context(self):
        request = self.rf.post('/__ui/detail/documents/', {
            'action': 'rename',
            'documentType': 'zertifikat',
            'documentFid': '46',
            'documentName': 'Neuer Zertifikatsname',
            'name': 'Alpenblick Anlage',
            'inspectiontype': '',
            'csrfmiddlewaretoken': 'a' * 32,
        })
        request.COOKIES['csrftoken'] = 'a' * 32
        api_response = HttpResponse(json.dumps({'fid': 46, 'name': 'Neuer Zertifikatsname'}), content_type='application/json')
        with patch.object(self.workflows, '_guard', return_value=({'role': 'administrator'}, None)), \
             patch.object(self.workflows, '_native', return_value=api_response) as native:
            response = self.workflows.playground_document_action(request)
        self.assertEqual(response.status_code, 303)
        self.assertIn('notice=Dokumentname+gespeichert.', response['Location'])
        self.assertEqual(native.call_args.kwargs['kwargs'], {'fid': 46})
        self.assertIn('/Document/46/Name/?type=zertifikat', native.call_args.kwargs['url'])
