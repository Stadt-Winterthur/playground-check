"""F05: exercise HTTP routing, binary responses, errors and a shared cache."""
import io
import json
import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.core.cache import caches
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import path
from playground_check import domain_support as service
from playground_check.http import Response
from playground_check.django_project.cache_policy import PrivateResponseCacheMiddleware


def private_cache_probe(request):
    # Two identities use the same URL. A shared cache must never retain either.
    private_cache_probe.calls += 1
    return HttpResponse(request.COOKIES.get('probe_identity', 'anonymous'))


def public_cache_probe(request):
    public_cache_probe.calls += 1
    return HttpResponse('public data')


private_cache_probe.calls = public_cache_probe.calls = 0
urlpatterns = [
    path('private/', private_cache_probe, name='cache-private-probe'),
    path('public/', public_cache_probe, name='api-health'),
]


class PrivateCachePolicyTests(unittest.TestCase):
    def assert_private(self, response):
        directives = {part.strip().lower() for part in response['Cache-Control'].split(',')}
        self.assertTrue({'private', 'no-store', 'no-cache', 'max-age=0', 'must-revalidate'} <= directives)
        self.assertNotIn('public', directives)
        self.assertFalse(any(x.startswith('s-maxage=') for x in directives))
        vary = {part.strip().lower() for part in response['Vary'].split(',')}
        self.assertTrue({'cookie', 'authorization'} <= vary)
        self.assertEqual(response['Expires'], 'Thu, 01 Jan 1970 00:00:00 GMT')

    def test_account_json_is_private_for_cookie_and_bearer(self):
        expected = {'fid': 31, 'mailAddress': 'synthetic@example.invalid'}
        with patch.object(service, 'require_user', return_value=(expected, None)):
            for headers in ({'HTTP_COOKIE': 'playground.auth=synthetic'},
                            {'HTTP_AUTHORIZATION': 'Bearer synthetic'}):
                with self.subTest(headers=tuple(headers)):
                    response = Client().get('/Account/Me/', **headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(json.loads(response.content), expected)
                    self.assert_private(response)

    def test_login_token_response_is_not_cacheable(self):
        db = MagicMock(); db.__enter__.return_value = MagicMock()
        row = {'fid': 31, 'email': 'synthetic@example.invalid', 'first_name': 'Test',
               'last_name': 'User', 'active': True, 'role': 'inspector', 'pwd': 'synthetic'}
        with patch.object(service, 'connect', return_value=db), \
             patch.object(service.user_repository, 'user_by_email', return_value=row), \
             patch.object(service, 'verify_passphrase', return_value=(True, False)), \
             patch.object(service.user_write_repository, 'record_login_attempt'), \
             patch.object(service.session_repository, 'create_session'):
            response = Client().post('/Account/Login/', json.dumps({
                'mailAddress': row['email'], 'passPhrase': 'synthetic-password'}),
                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('securityTokenString', json.loads(response.content))
        self.assertIn('HttpOnly', response['Set-Cookie'])
        self.assert_private(response)

    def test_pdf_download_bytes_and_type_are_preserved(self):
        db = MagicMock(); db.__enter__.return_value = MagicMock()
        content = b'%PDF-1.4\nsynthetic document'
        with patch.object(service, 'require_user', return_value=({'fid': 31}, None)), \
             patch.object(service, 'connect', return_value=db), \
             patch.object(service.remaining_reads_repository, 'document_blob', return_value={'content': content}):
            for kind in ('abnahme', 'zertifikat'):
                response = Client().get('/Document/9/', {'type': kind})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, content)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assert_private(response)

    def test_real_photos_and_device_placeholder_are_private(self):
        db = MagicMock(); db.__enter__.return_value = MagicMock()
        image = b'\xff\xd8\xff\x00synthetic'
        with patch.object(service, 'require_user', return_value=({'fid': 31}, None)), \
             patch.object(service, 'connect', return_value=db):
            with patch.object(service.remaining_reads_repository, 'playdevice_picture', return_value={'picture': image}):
                response = Client().get('/Playdevice/9/Picture/')
                self.assertEqual(response.content, image)
                self.assertEqual(response['Content-Type'], 'image/jpeg')
                self.assert_private(response)
            with patch.object(service.remaining_reads_repository, 'defect_picture', return_value={'value': image}):
                response = Client().get('/Defect/Picture/9/')
                self.assertEqual(response.content, image)
                self.assert_private(response)
            with patch.object(service.remaining_reads_repository, 'playdevice_picture', return_value={'picture': None}):
                response = Client().get('/Playdevice/9/Picture/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'image/svg+xml')
                self.assert_private(response)

    def test_private_failures_are_not_cacheable(self):
        with patch.object(service, 'require_user', return_value=(None, Response.text('denied', 401))):
            response = Client().get('/Account/Me/')
        self.assertEqual(response.status_code, 401); self.assert_private(response)
        # Framework-level denial and cross-site request rejection pass through the policy.
        for response, status in [(Client().get('/Account/Login/'), 405),
                                 (Client(enforce_csrf_checks=True).post('/session/end/', HTTP_SEC_FETCH_SITE='cross-site'), 403),
                                 (Client().get('/not-a-route/'), 404)]:
            self.assertEqual(response.status_code, status); self.assert_private(response)
        with patch.object(service, 'require_user', side_effect=RuntimeError('synthetic failure')):
            response = Client(raise_request_exception=False).get('/Account/Me/')
        self.assertEqual(response.status_code, 500); self.assert_private(response)

    def test_private_redirect_and_htmx_vary_are_preserved(self):
        response = Client().get('/workspace/')
        self.assertEqual(response.status_code, 302); self.assert_private(response)
        from playground_check.django_project import python_ui
        with patch.object(python_ui, 'require_user', return_value=(None, object())):
            response = Client().get('/assigned/', HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 401)
        self.assertIn('HX-Request', response['Vary']); self.assert_private(response)

    def test_public_endpoints_and_static_policy_are_preserved(self):
        response = Client().get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get('Cache-Control'))
        for name in ('sw.js', 'manifest.webmanifest'):
            response = Client().get('/static/' + name)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'no-cache')
            self.assertIsNone(response.get('Vary'))
        response = Client().get('/static/js/form-safety.js')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get('Cache-Control'))
        self.assert_private(Client().get('/static/does-not-exist.png'))

    def test_canonical_alias_and_base_path_use_same_policy(self):
        from playground_check.django_project import wsgi
        for prefix in ('', '/stadtgruen/spielplatzkontrolle'):
            captured = {}
            environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': prefix + '/aCcOuNt/mE',
                       'SCRIPT_NAME': '', 'QUERY_STRING': '', 'CONTENT_LENGTH': '0',
                       'wsgi.input': io.BytesIO(), 'SERVER_NAME': 'testserver',
                       'SERVER_PORT': '80', 'wsgi.url_scheme': 'http',
                       'SERVER_PROTOCOL': 'HTTP/1.1'}
            def start(status, headers, exc_info=None):
                captured.update(status=int(status.split()[0]), headers=dict(headers))
            with patch.object(wsgi, 'legacy_settings', replace(wsgi.legacy_settings, base_path=prefix)), \
                 patch.object(service, 'require_user', return_value=({'fid': 31}, None)):
                body = b''.join(wsgi.application(environ, start))
            self.assertEqual(captured['status'], 200)
            self.assertEqual(json.loads(body)['fid'], 31)
            self.assertIn('no-store', captured['headers']['Cache-Control'])
            self.assertIn('Authorization', captured['headers']['Vary'])

    def test_existing_cache_headers_are_overridden_but_vary_is_merged(self):
        response = HttpResponse('private')
        response['Cache-Control'] = 'public, max-age=600, s-maxage=900, stale-while-revalidate=60'
        response['Vary'] = 'Accept, Origin, HX-Request, cookie'
        middleware = PrivateResponseCacheMiddleware(lambda request: response)
        result = middleware(RequestFactory().get('/future/private-route/'))
        self.assert_private(result)
        for field in ('Accept', 'Origin', 'HX-Request'):
            self.assertIn(field, result['Vary'])
        self.assertEqual(result['Vary'].lower().count('cookie'), 1)

    def test_public_exception_does_not_allow_cookie_setting_responses(self):
        request = RequestFactory().get('/api/health')
        request.resolver_match = SimpleNamespace(url_name='api-health', kwargs={})
        response = HttpResponse('synthetic'); response.set_cookie('test', 'synthetic')
        self.assert_private(PrivateResponseCacheMiddleware(lambda request: response)(request))

    def test_static_looking_private_route_defaults_to_no_store(self):
        request = RequestFactory().get('/static/private.pdf')
        request.resolver_match = SimpleNamespace(url_name='new-private-download', kwargs={})
        self.assert_private(PrivateResponseCacheMiddleware(lambda request: HttpResponse('private'))(request))

    def test_shared_cache_never_serves_previous_users_private_response(self):
        middleware = [
            'django.middleware.cache.UpdateCacheMiddleware',
            'playground_check.django_project.cache_policy.PrivateResponseCacheMiddleware',
            'django.middleware.cache.FetchFromCacheMiddleware',
        ]
        with override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=middleware,
                               CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                                                   'LOCATION': 'f05-isolated-cache'}},
                               CACHE_MIDDLEWARE_SECONDS=600, CACHE_MIDDLEWARE_KEY_PREFIX='f05'):
            caches['default'].clear()
            private_cache_probe.calls = public_cache_probe.calls = 0
            try:
                # Positive control: the proposed shared cache really stores data.
                self.assertEqual(Client().get('/public/').content, b'public data')
                self.assertEqual(Client().get('/public/').content, b'public data')
                self.assertEqual(public_cache_probe.calls, 1)
                for identity in ('account-A', 'account-B', None):
                    client = Client()
                    if identity:
                        client.cookies['probe_identity'] = identity
                    response = client.get('/private/')
                    self.assertEqual(response.content.decode(), identity or 'anonymous')
                    self.assert_private(response)
                self.assertEqual(private_cache_probe.calls, 3)
            finally:
                caches['default'].clear()


if __name__ == '__main__':
    unittest.main()
