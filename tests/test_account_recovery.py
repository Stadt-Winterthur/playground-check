"""Public account flow security regressions (no real mail or database)."""
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode

os.environ.setdefault('PLAYGROUND_SECURITY_KEY','test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','playground_check.django_project.settings')
import django
django.setup()
from django.test import RequestFactory
from playground_check.django_project import account_recovery as flow
from playground_check.django_project.urls import urlpatterns


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_routes_are_public_and_separate_from_login(self):
        routes = {str(entry.pattern): entry.name for entry in urlpatterns}
        self.assertEqual(routes['register/'], 'public-register')
        self.assertEqual(routes['password/forgot/'], 'public-password-forgot')
        self.assertEqual(routes['password/set/<str:token>/'], 'public-password-set')

    def test_token_random_digest_and_expiry_policy(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'n': 0}
        raw = flow._issue(db, 'u@example.org', 'register', 'x'*64)
        self.assertRegex(raw, r'^[A-Za-z0-9_-]{43}$')
        self.assertNotEqual(raw, flow._hash(raw))
        sql, params = db.execute.call_args.args
        self.assertIn("30 minutes", sql)
        self.assertEqual(params[0], flow._hash(raw))
        self.assertNotIn(raw, str(params))

    def test_token_generation_rate_limited(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'n': 3}
        with patch.object(flow.secrets, 'token_urlsafe') as random_token:
            self.assertIsNone(flow._issue(db, 'u@example.org', 'reset', 'x'*64))
            random_token.assert_not_called()

    def test_registration_never_grants_active_access(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = {'n': 0}
        cm = MagicMock()
        cm.__enter__.return_value = db
        with patch.object(flow, 'connect', return_value=cm), patch.object(flow.user_repository, 'users_by_email', return_value=[]), patch.object(flow, '_send') as send:
            result = flow.register(self.rf.post('/register/', urlencode({'first_name':'Anna', 'last_name':'Muster','email':'anna@example.org'}), content_type='application/x-www-form-urlencoded'))
        self.assertEqual(result.status_code, 200)
        inserts = [sql for call in db.execute.call_args_list for sql in [call.args[0]] if 'INSERT INTO "wgr_sp_kontrolleur"' in sql]
        self.assertEqual(len(inserts), 1)
        self.assertIn('NULL', inserts[0])
        self.assertIn('false, true', inserts[0])
        send.assert_called_once()
        self.assertNotIn('Set-Cookie', result)

    def test_reset_uses_generic_answer_for_unknown_email(self):
        cm = MagicMock()
        cm.__enter__.return_value = MagicMock()
        with patch.object(flow, 'connect', return_value=cm), patch.object(flow.user_repository, 'users_by_email', return_value=[]), patch.object(flow, '_send') as send:
            response = flow.forgot(self.rf.post('/password/forgot/', urlencode({'email':'unknown@example.org'}), content_type='application/x-www-form-urlencoded'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Falls die Angaben', response.content.decode())
        send.assert_not_called()

    def test_invalid_token_does_not_reach_db(self):
        with patch.object(flow, 'connect') as connect:
            result = flow.set_password(self.rf.post('/password/set/invalid/', {'password':'strong enough password','confirm':'strong enough password'}), 'invalid')
        self.assertEqual(result.status_code, 200)
        connect.assert_not_called()

    def test_original_api_does_not_create_user_from_failed_login(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'src/playground_check/django_project/account_commands.py'
        source = path.read_text()
        login = source.split('def login(request):',1)[1].split('@operation_errors()',1)[0]
        self.assertNotIn('register_pending_user(', login)
