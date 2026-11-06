"""Malformed API input must become HTTP 400 before business reads or writes."""
import json
import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.test import Client
from playground_check import domain_support
from playground_check.django_project import views


class APIInputValidationTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        self.identity = stack.enter_context(patch.object(domain_support, 'require_user',
            return_value=({'fid': 17, 'role': 'administrator', 'mailAddress': 'test@example.invalid'}, None)))
        stack.enter_context(patch.object(domain_support, 'current_user',
            return_value={'fid': 17, 'role': 'administrator', 'mailAddress': 'test@example.invalid'}))
        self.db = stack.enter_context(patch.object(domain_support, 'connect',
            side_effect=AssertionError('Business DB must not be accessed for invalid input')))
        self.map = stack.enter_context(patch.object(views, 'map_image_base64',
            side_effect=AssertionError('WMS must not be accessed for invalid coordinates')))
        self.client = Client(raise_request_exception=False)

    def assert_bad_input(self, method, path, body):
        response = getattr(self.client, method)(path, data=body, content_type='application/json')
        self.assertEqual(response.status_code, 400, (method, path, response.content[:150]))
        self.assertTrue(response.json()['errorMessage'])
        self.assertIn('no-store', response['Cache-Control'])
        self.db.assert_not_called()

    def test_object_endpoints_reject_arrays_scalars_and_broken_json(self):
        routes = [('post', '/Account/Login/'), ('put', '/Account/Users/'),
                  ('post', '/Playdevice/'), ('put', '/Playdevice/?fid=42'),
                  ('put', '/Playdevice/42/Picture/'), ('post', '/Defect/'),
                  ('put', '/Defect/'), ('put', '/Defect/Picture/42/'),
                  ('post', '/Defect/42/accept/'), ('post', '/Defect/42/reject/'),
                  ('post', '/Document/'), ('put', '/Document/42/Name/'),
                  ('post', '/PushSubscription/Register/'), ('delete', '/PushSubscription/Unregister/')]
        for method, path in routes:
            for body in ('[1]', '[]', '42', 'true', '"text"', '{', b'\xff'):
                with self.subTest(method=method, path=path, body=body):
                    self.assert_bad_input(method, path, body)

    def test_report_endpoint_requires_list_of_objects_with_typed_fields(self):
        for body in ('{}', '42', '[1]', '[null]', '{',
                     '[{"playdeviceFid": {}}]', '[{"inspectionType": []}]',
                     '[{"inspectionComment": {}}]', '[{"inspectionDone": []}]'):
            with self.subTest(body=body):
                self.assert_bad_input('post', '/Inspection/', body)

    def test_wrong_nested_field_types_are_rejected(self):
        cases = [('post', '/Playdevice/', {'properties': []}),
                 ('post', '/Playdevice/', {'properties': 'not an object'}),
                 ('put', '/Playdevice/42/Picture/', {'data': {}}),
                 ('post', '/Account/Login/', {'mailAddress': [], 'passPhrase': 'test'}),
                 ('put', '/Account/Users/', {'role': {}, 'active': []}),
                 ('post', '/Defect/', {'tid': [], 'defectDescription': 'Test'}),
                 ('put', '/Defect/', {'defectDescription': 'Test', 'priority': 'invalid'}),
                 ('put', '/Defect/', {'defectDescription': 'Test', 'dateDone': 'not-a-date'}),
                 ('put', '/Defect/Picture/42/', {'base64StringPicture': []}),
                 ('post', '/Defect/42/accept/', {'assignmentComment': 123}),
                 ('post', '/Document/', {'name': [], 'playgroundId': {}}),
                 ('post', '/PushSubscription/Register/', {'endpoint': {}})]
        for method, path, body in cases:
            with self.subTest(method=method, path=path, body=body):
                self.assert_bad_input(method, path, json.dumps(body))

    def test_invalid_ids_are_rejected_before_business_database_access(self):
        for value in ('abc', '-1', '0', '1.5', 'true', '2147483648', ''):
            with self.subTest(value=value):
                self.assert_bad_input('get', '/Defect/?tid=' + value, '')
                self.assert_bad_input('put', '/Playdevice/?fid=' + value, '{}')

    def test_invalid_or_nonfinite_coordinates_are_rejected_before_wms(self):
        for value in ('abc', 'NaN', 'Infinity', '-Infinity', '1e999'):
            for axis in ('x', 'y'):
                with self.subTest(value=value, axis=axis):
                    other = 'y' if axis == 'x' else 'x'
                    self.assert_bad_input('get', f'/Playground/mapimage/?{axis}={value}&{other}=1', '')
        self.map.assert_not_called()

    def test_authentication_denial_is_preserved(self):
        from playground_check.http import Response
        self.identity.return_value = (None, Response.text('Unauthorized', 401))
        response = self.client.post('/Playdevice/', data='[1]', content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.db.assert_not_called()

    def test_valid_empty_object_keeps_existing_missing_properties_response(self):
        response = self.client.post('/Playdevice/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'errorMessage': 'SPK-5'})
        self.db.assert_not_called()

    def test_internal_programming_errors_are_not_disguised_as_bad_input(self):
        self.map.side_effect = TypeError('internal defect')
        response = self.client.get('/Playground/mapimage/?x=1&y=2')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b'internal defect', response.content)
