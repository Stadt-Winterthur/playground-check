"""F02: replay, account-wide revocation and transactional PostgreSQL checks.

Set PLAYGROUND_TEST_SESSION_DSN to a dedicated disposable test database.
Every integration test owns a randomly named schema, never existing tables.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')

import django
django.setup()
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from django.test import Client, RequestFactory
from playground_check import auth, domain_support as service, session_repository, user_write_repository
from playground_check.config import settings
from playground_check.http import Request
from playground_check.django_project import account_queries, python_ui_workflows


class SessionTokenTests(unittest.TestCase):
    user = {'fid': 1, 'mailAddress': 'audit@example.invalid', 'firstName': 'Test',
            'lastName': 'User', 'role': 'inspector'}

    def test_each_login_has_an_independent_session_id(self):
        first = auth.decode_token(auth.issue_token(self.user))
        second = auth.decode_token(auth.issue_token(self.user))
        self.assertNotEqual(first['jti'], second['jti'])
        self.assertEqual(len(first['jti']), 32)

    def test_signed_pre_f02_token_without_session_id_is_rejected(self):
        token = auth.issue_token(self.user)
        head, body, _ = token.split('.')
        payload = auth.decode_token(token)
        payload.pop('jti')
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
        unsigned = f'{head}.{body}'
        signature = hmac.new(settings.security_key.encode(), unsigned.encode(), hashlib.sha256).digest()
        signed = unsigned + '.' + base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
        self.assertIsNone(auth.decode_token(signed))

    def test_api_logout_reports_persistent_failure_without_clearing_cookie(self):
        from psycopg import OperationalError
        request = RequestFactory().post('/Account/Logout/')
        with patch.object(service, 'revoke_request_session', side_effect=OperationalError('database unavailable')):
            response = account_queries.logout(request)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.cookies)
        self.assertIsNone(response.get('Set-Cookie'))

    def test_gui_logout_reports_persistent_failure_without_clearing_cookie(self):
        request = RequestFactory().post('/logout/')
        request._dont_enforce_csrf_checks = True
        with patch.object(service, 'revoke_request_session', side_effect=OSError('database unavailable')):
            response = python_ui_workflows.logout(request)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(settings.auth_cookie_name, response.cookies)

    def test_invalid_token_cannot_trigger_a_database_delete(self):
        with patch.object(service, 'connect', side_effect=AssertionError('database accessed')):
            service.revoke_request_session(Request({'HTTP_AUTHORIZATION': 'Bearer invalid'}))


@unittest.skipUnless(os.getenv('PLAYGROUND_TEST_SESSION_DSN'), 'dedicated session test database not configured')
class PostgreSQLSessionTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['PLAYGROUND_TEST_SESSION_DSN']
        self.schema = 'test_f02_' + uuid.uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.connection() as db:
            db.execute('''CREATE TABLE wgr_sp_kontrolleur (
                fid bigserial PRIMARY KEY, nachname text, vorname text, e_mail text UNIQUE,
                pwd text, letzter_anmeldeversuch timestamp, rolle text, zustaendigkeit text,
                aktiv boolean, is_new boolean DEFAULT false, ui_language text)''')
        migration = (Path(__file__).resolve().parents[1] / 'tests/fixtures/auth_sessions.sql').read_text()
        # Use an isolated session fixture; no production migration files are required.
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
            db.execute(migration)
            db.execute(migration)  # Safe to reapply to an already matching table.
        with self.connection() as db:
            for fid, email, role in [(1, 'admin@example.invalid', 'administrator'),
                                     (2, 'inspector@example.invalid', 'inspector')]:
                db.execute('''INSERT INTO wgr_sp_kontrolleur
                    (fid, nachname, vorname, e_mail, pwd, rolle, zustaendigkeit, aktiv)
                    VALUES (%s, 'Test', 'Audit', %s, %s, %s, '', true)''',
                    (fid, email, auth.hash_passphrase('original-password', email), role))
        self.connector = patch.object(service, 'connect', self.connection)
        self.connector.start()
        self.addCleanup(self.connector.stop)

    def drop_schema(self):
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    @contextmanager
    def connection(self):
        with psycopg.connect(self.dsn, row_factory=dict_row) as db:
            db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
            db.execute("SET TIME ZONE 'Europe/Zurich'")
            yield db

    def login(self, email='inspector@example.invalid', password='original-password'):
        # Keep rate-limit timing unrelated to the session regression tests.
        with self.connection() as db:
            db.execute('UPDATE wgr_sp_kontrolleur SET letzter_anmeldeversuch=NULL WHERE e_mail=%s', (email,))
        response = Client().post('/Account/Login/', json.dumps({
            'mailAddress': email, 'passPhrase': password}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)['securityTokenString']

    def me(self, token, cookie=False):
        client = Client()
        if cookie:
            client.cookies[settings.auth_cookie_name] = token
            return client.get('/Account/Me/').status_code
        return client.get('/Account/Me/', HTTP_AUTHORIZATION='Bearer ' + token).status_code

    def test_api_logout_rejects_cookie_and_bearer_replay_but_keeps_other_sessions(self):
        first, second = self.login(), self.login()
        other = self.login('admin@example.invalid')
        self.assertEqual(self.me(first), 200)
        self.assertEqual(self.me(first, cookie=True), 200)
        client = Client(); client.cookies[settings.auth_cookie_name] = first
        response = client.post('/Account/Logout/')
        self.assertEqual(response.status_code, 204)
        self.assertIn('Max-Age=0', response['Set-Cookie'])
        self.assertEqual(self.me(first), 401)
        self.assertEqual(self.me(first, cookie=True), 401)
        self.assertEqual(self.me(second), 200)
        self.assertEqual(self.me(other), 200)
        # Repeating logout with the removed session remains harmless.
        self.assertEqual(client.post('/Account/Logout/').status_code, 204)

    def test_gui_logout_without_csrf_revokes_token_and_prevents_replay(self):
        token = self.login()
        client = Client(enforce_csrf_checks=True)
        client.cookies[settings.auth_cookie_name] = token
        self.assertEqual(self.me(token), 200)
        response = client.post('/session/end/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(response.cookies[settings.auth_cookie_name]['max-age']), '0')
        self.assertEqual(self.me(token), 401)
        # Logging out a second time must not reactivate the revoked token.
        client.cookies[settings.auth_cookie_name] = token
        self.assertEqual(client.post('/session/end/').status_code, 302)
        self.assertEqual(self.me(token), 401)

    def test_password_change_revokes_all_target_sessions_and_allows_only_new_password(self):
        first, second = self.login(), self.login()
        admin = self.login('admin@example.invalid')
        response = Client().put('/Account/Users/?changePassphrase=true', json.dumps({
            'mailAddress': 'inspector@example.invalid', 'firstName': 'Audit', 'lastName': 'Test',
            'role': 'inspector', 'responsibility': '', 'active': True, 'passPhrase': 'new-password-123'}),
            content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + admin)
        self.assertEqual(json.loads(response.content)['errorMessage'], '')
        self.assertEqual(self.me(first), 401); self.assertEqual(self.me(second), 401)
        self.assertEqual(self.me(admin), 200)
        with self.connection() as db:
            db.execute('UPDATE wgr_sp_kontrolleur SET letzter_anmeldeversuch=NULL WHERE fid=2')
        old = Client().post('/Account/Login/', json.dumps({
            'mailAddress': 'inspector@example.invalid', 'passPhrase': 'original-password'}),
            content_type='application/json')
        self.assertEqual(old.status_code, 401)
        self.assertEqual(self.me(self.login(password='new-password-123')), 200)

    def test_deactivate_reactivate_does_not_revive_old_tokens(self):
        token = self.login()
        with self.connection() as db:
            user_write_repository.deactivate_user(db, 'inspector@example.invalid')
        self.assertEqual(self.me(token), 401)
        with self.connection() as db:
            user_write_repository.update_user(db, 'inspector@example.invalid', 'Test', 'Audit',
                                              'inspector', '', True, False)
        self.assertEqual(self.me(token), 401)
        self.assertEqual(self.me(self.login()), 200)

    def test_admin_edit_revokes_sessions_and_keeps_unrelated_user(self):
        token = self.login(); other = self.login('admin@example.invalid')
        with self.connection() as db:
            user_write_repository.update_user(db, 'inspector@example.invalid', 'Test', 'Audit',
                                              'maintenance', '', True, False)
        self.assertEqual(self.me(token), 401); self.assertEqual(self.me(other), 200)

    def test_individual_account_emergency_revocation(self):
        first, second = self.login(), self.login()
        other = self.login('admin@example.invalid')
        with self.connection() as db:
            session_repository.revoke_user_sessions(db, 'inspector@example.invalid')
        self.assertEqual(self.me(first), 401); self.assertEqual(self.me(second), 401)
        self.assertEqual(self.me(other), 200)

    def test_missing_expired_and_wrong_account_session_are_rejected(self):
        token = self.login(); claims = auth.decode_token(token)
        with self.connection() as db:
            db.execute('UPDATE wgr_sp_auth_session SET fid_kontrolleur=1 WHERE session_id=%s', (claims['jti'],))
        self.assertEqual(self.me(token), 401)
        with self.connection() as db:
            db.execute("UPDATE wgr_sp_auth_session SET fid_kontrolleur=2, expires_at=now()-interval '1 second' WHERE session_id=%s", (claims['jti'],))
        self.assertEqual(self.me(token), 401)
        with self.connection() as db:
            session_repository.revoke_session(db, claims['jti'])
        self.assertEqual(self.me(token), 401)

    def test_signed_but_unregistered_token_is_rejected(self):
        token = auth.issue_token({'fid': 2, 'mailAddress': 'inspector@example.invalid',
                                 'firstName': 'Audit', 'lastName': 'Test', 'role': 'inspector'})
        self.assertEqual(self.me(token), 401)

    def test_password_and_revocation_roll_back_together(self):
        token = self.login()
        with self.assertRaises(RuntimeError):
            with self.connection() as db:
                user_write_repository.update_password(db, 'inspector@example.invalid', 'replacement-hash')
                raise RuntimeError('abort transaction')
        self.assertEqual(self.me(token), 200)
        self.assertEqual(self.me(self.login()), 200)

    def test_expired_sessions_are_cleaned_up_on_login(self):
        token = self.login(); claims = auth.decode_token(token)
        with self.connection() as db:
            db.execute("UPDATE wgr_sp_auth_session SET expires_at=now()-interval '1 second' WHERE session_id=%s", (claims['jti'],))
        self.login()
        with self.connection() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM wgr_sp_auth_session WHERE session_id=%s', (claims['jti'],)).fetchone())

    def test_database_failure_never_authenticates_a_signed_token(self):
        token = self.login()
        with patch.object(service, 'connect', side_effect=OSError('database unavailable')):
            with self.assertRaises(OSError):
                service.current_user(Request({'HTTP_AUTHORIZATION': 'Bearer ' + token}))

    def test_legacy_password_upgrade_creates_a_valid_new_session(self):
        token = self.login()
        with self.connection() as db:
            db.execute('UPDATE wgr_sp_kontrolleur SET pwd=%s WHERE fid=2',
                       (auth.hash_passphrase('original-password'),))
        upgraded = self.login()
        self.assertEqual(self.me(token), 401)
        self.assertEqual(self.me(upgraded), 200)


if __name__ == '__main__':
    unittest.main()
