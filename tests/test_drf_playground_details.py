"""Compatibility tests for incremental playground detail GET migration."""
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, 'Django REST Framework not installed')
class PlaygroundDetailsDRFTest(unittest.TestCase):
    def call(self, path, *, method='GET', query=''):
        from playground_check.django_project import wsgi
        from playground_check.config import settings
        from dataclasses import replace
        result = {}
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'SCRIPT_NAME': '',
                   'QUERY_STRING': query, 'CONTENT_LENGTH': '0', 'wsgi.input': io.BytesIO(),
                   'SERVER_NAME': 'testserver', 'SERVER_PORT': '80',
                   'wsgi.url_scheme': 'http', 'SERVER_PROTOCOL': 'HTTP/1.1'}
        def start_response(status, headers, exc_info=None):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        with patch.object(wsgi, 'legacy_settings', replace(settings, base_path='')):
            body = b''.join(wsgi.application(environ, start_response))
        return result['status'], json.loads(body)

    def test_public_uuid_lookup_returns_existing_geojson(self):
        from playground_check.django_project import views
        from playground_check.service import _public_feature
        row = {'uuid': '11111111-1111-1111-1111-111111111111', 'number': 9,
               'name': 'Testplatz', 'street_name': 'Gasse', 'house_no': '3',
               'x': 8.73, 'y': 47.5}
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params):
                self.params = params
                return self
            def fetchone(self): return row
        db = DB()
        with patch.object(views, 'connect', return_value=db):
            status, payload = self.call('/Collections/Playgrounds/Items/11111111-1111-1111-1111-111111111111/')
        self.assertEqual(status, 200)
        self.assertEqual(payload, _public_feature(row))
        self.assertEqual(db.params, (row['uuid'],))

    def test_public_uuid_missing_preserves_error_payload(self):
        from playground_check.django_project import views
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params): return self
            def fetchone(self): return None
        with patch.object(views, 'connect', return_value=DB()):
            status, payload = self.call('/Collections/Playgrounds/Items/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/')
        self.assertEqual(status, 200)
        self.assertEqual(payload['errorMessage'], 'No playground found for given UUID.')

    def test_byname_forwards_query_and_uses_shared_payload(self):
        from playground_check.django_project import views
        expected = {'id': 123, 'name': 'Spielplatz Test', 'playdevices': []}
        with patch.object(views, '_legacy_access_error', return_value=None), \
             patch.object(views, 'playground_by_name_data', return_value=expected) as fetch:
            status, payload = self.call('/Playground/byname/', query='name=Spielplatz+Test&withdefects=true')
        self.assertEqual((status, payload), (200, expected))
        self.assertEqual(fetch.call_args.args[0]['name'], 'Spielplatz Test')
        self.assertEqual(fetch.call_args.args[0]['withdefects'], 'true')

    def test_byname_unauthorized_never_fetches_data(self):
        from django.http import HttpResponse
        from playground_check.django_project import views
        with patch.object(views, '_legacy_access_error', return_value=HttpResponse('unauthorized', status=401)), \
             patch.object(views, 'playground_by_name_data') as fetch:
            from playground_check.django_project import wsgi
            captured = {}
            env = {'REQUEST_METHOD':'GET', 'PATH_INFO':'/Playground/byname/', 'QUERY_STRING':'name=Test',
                   'SCRIPT_NAME':'', 'wsgi.input':io.BytesIO(), 'CONTENT_LENGTH':'0',
                   'SERVER_NAME':'testserver', 'SERVER_PORT':'80',
                   'wsgi.url_scheme':'http', 'SERVER_PROTOCOL':'HTTP/1.1'}
            def start(status, headers, exc_info=None): captured['status'] = status
            with patch.object(wsgi, 'legacy_settings', __import__('dataclasses').replace(wsgi.legacy_settings, base_path='')):
                list(wsgi.application(env, start))
            self.assertTrue(captured['status'].startswith('401'))
            fetch.assert_not_called()

    def test_byname_post_remains_legacy(self):
        from playground_check.django_project import wsgi
        with patch.object(wsgi, 'legacy_application', return_value=[b'legacy']) as legacy:
            env = {'REQUEST_METHOD':'POST', 'PATH_INFO':'/Playground/byname/'}
            self.assertEqual(list(wsgi.application(env, lambda *_: None)), [b'legacy'])
        legacy.assert_called_once()
