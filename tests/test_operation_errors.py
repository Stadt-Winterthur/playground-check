"""Unexpected failures have useful statuses, safe wire bodies and one traceback."""
import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.test import Client, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from psycopg import OperationalError
from rest_framework.exceptions import ParseError

from playground_check import domain_support as service
from playground_check.django_project import account_commands, document_commands, operation_errors, views
from playground_check.django_project.ui_command_adapter import invoke_upload
from playground_check.http import Response


class OperationErrorTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.user = {'fid': 17, 'role': 'administrator', 'mailAddress': 'test@example.invalid'}
        self.identity = patch.object(service, 'require_user', return_value=(self.user, None))
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def test_login_connection_failure_is_503_with_original_text_format(self):
        with patch.object(service, 'connect', side_effect=OperationalError('private database detail')), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.post('/Account/Login/', json.dumps({
                'mailAddress': 'test@example.invalid', 'passPhrase': 'private-password'}),
                content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertNotIn(b'private', response.content)
        self.assertIn('no-store', response['Cache-Control'])
        log.assert_called_once()
        self.assertIs(log.call_args.kwargs['exc_info'][0], OperationalError)

    def test_bad_login_input_does_not_log_server_error_or_open_database(self):
        with patch.object(service, 'connect') as connect, \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.post('/Account/Login/', '{', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        connect.assert_not_called()
        log.assert_not_called()

    def test_document_failure_rolls_back_before_503_response(self):
        db = MagicMock()
        db.__enter__.return_value = db
        failure = OperationalError('database unavailable')
        with patch.object(service, 'connect', return_value=db), \
             patch.object(service.document_write_repository, 'insert_document', side_effect=failure), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.post('/Document/', json.dumps({
                'type': 'abnahme', 'name': 'Test', 'playgroundId': 42,
                'contentBase64': base64.b64encode(b'%PDF-1.4\nTest').decode()}),
                content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'errorMessage': 'Dokument konnte nicht gespeichert werden.'})
        self.assertIs(db.__exit__.call_args.args[1], failure)
        log.assert_called_once()

    def test_document_download_failure_keeps_empty_response_body(self):
        with patch.object(service, 'connect', side_effect=OperationalError('secret')), \
             patch.object(operation_errors.LOGGER, 'error'):
            response = self.client.get('/Document/42/?type=abnahme')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b'')

    def test_direct_gui_upload_call_has_same_failure_boundary(self):
        request = self.factory.post('/document/upload/')
        with patch.object(service, 'connect', side_effect=OperationalError('secret')), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = invoke_upload(request, document_commands.create_document,
                                     {'type': 'abnahme', 'name': 'Test', 'playgroundId': '42'},
                                     {'document': SimpleUploadedFile('test.pdf', b'%PDF-1.4\nTest')})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content), {'errorMessage': 'Dokument konnte nicht gespeichert werden.'})
        log.assert_called_once()

    def test_programming_errors_are_500_not_400_or_503(self):
        for failure in (TypeError('internal defect'), KeyError('internal defect'), ValueError('internal defect')):
            with self.subTest(error=type(failure).__name__), \
                 patch.object(service, 'connect', side_effect=failure), \
                 patch.object(operation_errors.LOGGER, 'error') as log:
                response = self.client.put('/Account/Users/', json.dumps({
                    'mailAddress': 'test@example.invalid', 'role': 'inspector'}),
                    content_type='application/json')
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {'errorMessage': 'SPK-3'})
            log.assert_called_once()

    def test_unhandled_read_failure_uses_same_drf_boundary(self):
        with patch.object(views, 'map_image_base64', side_effect=OperationalError('secret')), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.get('/Playground/mapimage/?x=1&y=2')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'errorMessage': 'SPK-3'})
        log.assert_called_once()

    def test_public_collection_keeps_geojson_error_envelope(self):
        with patch.object(views, 'connect', side_effect=OperationalError('secret')), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.get('/Collections/Playgrounds/Items/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()[0]['errorMessage'], 'Unknown critical error.')
        log.assert_called_once()

    def test_push_validation_is_400_without_database_or_error_log(self):
        with patch.object(service, 'connect') as connect, \
             patch.object(operation_errors.LOGGER, 'error') as log:
            for method, path in (('post', '/PushSubscription/Register/'),
                                 ('delete', '/PushSubscription/Unregister/')):
                response = getattr(self.client, method)(path, '{}', content_type='application/json')
                self.assertEqual(response.status_code, 400)
        connect.assert_not_called()
        log.assert_not_called()

    def test_expected_errors_and_denials_keep_existing_statuses(self):
        for status in (401, 403):
            with self.subTest(status=status), patch.object(service, 'require_user',
                    return_value=(None, Response.text('denied', status))), \
                 patch.object(operation_errors.LOGGER, 'error') as log:
                response = self.client.post('/Document/', '{}', content_type='application/json')
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.content, b'denied')
            log.assert_not_called()
        with patch.object(account_commands, 'object_body', side_effect=ParseError('invalid')), \
             patch.object(operation_errors.LOGGER, 'error') as log:
            response = self.client.post('/Account/Login/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        log.assert_not_called()
