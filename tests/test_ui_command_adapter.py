"""In-process GUI command invocation: no RequestFactory or database required."""
import json
import unittest
from types import SimpleNamespace

from playground_check.django_project.ui_command_adapter import command_input, invoke


class UICommandAdapterTests(unittest.TestCase):
    def setUp(self):
        self.browser_request = SimpleNamespace(META={
            'HTTP_COOKIE': 'auth=fake', 'HTTP_AUTHORIZATION': 'Bearer fake',
            'HTTP_X_CSRFTOKEN': 'form-csrf', 'HTTP_CONTENT_TYPE': 'multipart/form-data',
            'CONTENT_LENGTH': '999999', 'REMOTE_ADDR': '127.0.0.1',
        })

    def test_payload_identity_and_query_are_preserved_without_http_request(self):
        command = command_input(self.browser_request, {'data': 'bild'},
                                method='PUT', url='/Playdevice/?fid=123')
        self.assertEqual(command.META['REQUEST_METHOD'], 'PUT')
        self.assertEqual(command.META['QUERY_STRING'], 'fid=123')
        self.assertEqual(json.loads(command.body), {'data': 'bild'})
        self.assertEqual(command.META['HTTP_COOKIE'], 'auth=fake')
        self.assertEqual(command.META['HTTP_AUTHORIZATION'], 'Bearer fake')
        self.assertNotIn('HTTP_X_CSRFTOKEN', command.META)
        self.assertNotIn('HTTP_CONTENT_TYPE', command.META)
        self.assertEqual(command.META['CONTENT_LENGTH'], str(len(command.body)))

    def test_handler_is_called_directly_with_explicit_arguments(self):
        def command(data, fid, *, accepted):
            return (json.loads(data.body), fid, accepted)
        self.assertEqual(
            invoke(self.browser_request, command, {'x': True},
                   url='/Defect/55/accept/', kwargs={'fid': 55, 'accepted': True}),
            ({'x': True}, 55, True))
