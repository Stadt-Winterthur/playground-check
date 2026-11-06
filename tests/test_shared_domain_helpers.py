"""Behavioural parity of shared helpers through native and compatibility exports."""
import base64
import os
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
from playground_check import service, domain_support
from playground_check.auth import issue_token
from playground_check.http import Request

FACADES = (service, domain_support)


class SharedDomainHelperTests(unittest.TestCase):
    def setUp(self):
        self.user = {'fid': 17, 'mailAddress': 'test@example.invalid', 'firstName': 'Test',
                     'lastName': 'Person', 'role': 'inspector'}
        self.token = issue_token(self.user)

    def test_custom_cookie_configuration_is_preserved_per_entry_point(self):
        for module in FACADES:
            with self.subTest(module=module.__name__), patch.object(module, 'settings',
                    replace(module.settings, auth_cookie_name='review.auth', base_path='/review', token_issuer='https://example.invalid/review')):
                request = Request({'HTTP_COOKIE': 'review.auth=' + self.token})
                self.assertEqual(module._request_token(request), self.token)
                self.assertEqual(module.token_user(request)['mailAddress'], 'test@example.invalid')
                _, cookie = module._auth_cookie(self.token)
                self.assertIn('Path=/review', cookie)
                self.assertIn('Secure', cookie)
                self.assertIn('SameSite=Strict', cookie)
                self.assertIn('Max-Age=0', module._auth_cookie('', clear=True)[1])

    def test_bearer_precedence_and_role_check_are_unchanged(self):
        for module in FACADES:
            with self.subTest(module=module.__name__):
                request = Request({'HTTP_AUTHORIZATION': 'Bearer ' + self.token,
                                   'HTTP_COOKIE': module.settings.auth_cookie_name + '=invalid'})
                self.assertEqual(module._request_token(request), self.token)
                self.assertIsNone(module.token_user(request, 'administrator'))

    def test_session_revalidation_uses_each_callers_connection(self):
        row = {'fid': 17, 'email': 'test@example.invalid', 'first_name': 'Test',
               'last_name': 'Person', 'role': 'inspector', 'active': True}
        for module in FACADES:
            for active in (True, False):
                db = MagicMock(); db.__enter__.return_value = db
                with self.subTest(module=module.__name__, active=active), \
                     patch.object(module, 'connect', return_value=db) as connect, \
                     patch.object(module.user_repository, 'user_by_email', return_value=row), \
                     patch.object(module.session_repository, 'is_active', return_value=active) as session:
                    result = module.current_user(Request({'HTTP_AUTHORIZATION': 'Bearer ' + self.token}))
                    self.assertEqual(result['fid'] if result else None, 17 if active else None)
                    connect.assert_called_once_with()
                    self.assertEqual(session.call_args.args[0], db)

    def test_dry_run_still_skips_database_and_denies_identity(self):
        for module in FACADES:
            with self.subTest(module=module.__name__), patch.object(module, 'connect') as connect:
                user, error = module.require_user(Request({'HTTP_AUTHORIZATION': 'Bearer ' + self.token,
                                                          'QUERY_STRING': 'dryRun=true'}))
                self.assertIsNone(user)
                self.assertEqual(error.status, 401)
                connect.assert_not_called()

    def test_document_and_image_formats_roundtrip_through_both_exports(self):
        pdf = b'%PDF-1.4\nTest'
        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 12
        data = 'data:image/png;base64,' + base64.b64encode(png).decode()
        outputs = []
        for module in FACADES:
            stored = module._document_with_name(pdf, 'Abnahme ä.pdf')
            self.assertEqual(module._document_parts(memoryview(stored)), (pdf, 'Abnahme ä.pdf'))
            self.assertEqual(module._decode_image(data), (png, 'image/png'))
            self.assertIsNone(module._image_upload_error(data))
            self.assertIsNotNone(module._image_upload_error('invalid base64'))
            outputs.append(stored)
        self.assertEqual(outputs[0], outputs[1])

    def test_playground_lookup_keeps_bound_connection_and_build_strategy(self):
        for module in FACADES:
            db = MagicMock(); db.__enter__.return_value = db
            with self.subTest(module=module.__name__), \
                 patch.object(module, 'connect', return_value=db), \
                 patch.object(module.playground_repository, 'playground_by_name', return_value={'id': 42}), \
                 patch.object(module, '_playground_result', return_value={'id': 42}) as build:
                self.assertEqual(module.playground_by_name_data({'name': 'Test', 'inspectiontype': 'VI',
                                                                'withdefects': 'true'}), {'id': 42})
                build.assert_called_once_with(db, {'id': 42}, 'VI', True, False)
