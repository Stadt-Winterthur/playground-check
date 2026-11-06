"""GUI authentication is reused within a request, never across requests."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')

import django
django.setup()

from django.test import RequestFactory
from playground_check import domain_support
from playground_check.auth import issue_token
from playground_check.django_project import python_ui as ui
from playground_check.django_project.python_ui_workflows import _guard
from playground_check.http import Response


class UIRequestIdentityTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = {'fid': 17, 'mailAddress': 'test@example.invalid',
                     'firstName': 'Test', 'lastName': 'Person', 'role': 'inspector'}

    def test_inspection_decorator_and_view_validate_only_once(self):
        from django.http import HttpResponse
        request = self.factory.get('/inspection/')
        with patch.object(ui, 'require_user', return_value=(self.user, None)) as identity, \
             patch('playground_check.django_project.inspection_ui.edit_inspection',
                   return_value=HttpResponse('inspection')) as editor:
            response = ui.inspection_editor(request)
        self.assertEqual(response.status_code, 200)
        identity.assert_called_once()
        self.assertIs(editor.call_args.args[1], self.user)
        self.assertIs(request._ui_user, self.user)

    def test_cached_identity_still_enforces_each_role_requirement(self):
        request = self.factory.get('/admin/')
        with patch.object(ui, 'require_user', return_value=(self.user, None)) as identity:
            self.assertEqual(_guard(request)[0], self.user)
            user, denial = _guard(request, role=('administrator',))
        self.assertIsNone(user)
        self.assertEqual(denial.status_code, 403)
        identity.assert_called_once()

    def test_rejected_credentials_are_not_revalidated_within_request(self):
        request = self.factory.get('/profile/')
        with patch.object(ui, 'require_user', return_value=(None, Response.text('denied', 401))) as identity:
            for _ in range(2):
                user, denial = ui._private(request)
                self.assertIsNone(user)
                self.assertEqual(denial.status_code, 401)
        identity.assert_called_once()

    def test_database_failure_does_not_grant_access_or_run_editor(self):
        request = self.factory.get('/inspection/')
        with patch.object(ui, 'require_user', side_effect=RuntimeError('database unavailable')), \
             patch('playground_check.django_project.inspection_ui.edit_inspection') as editor:
            with self.assertLogs(ui.LOGGER, level='ERROR'):
                response = ui.inspection_editor(request)
        self.assertEqual(response.status_code, 503)
        editor.assert_not_called()

    def test_next_request_rechecks_session_and_current_database_role(self):
        token = issue_token(self.user)
        row = {'fid': 17, 'email': self.user['mailAddress'], 'active': True,
               'role': 'inspector'}
        db = MagicMock()
        db.__enter__.return_value = db
        with patch.object(domain_support, 'connect', return_value=db) as connect, \
             patch.object(domain_support.user_repository, 'user_by_email', return_value=row), \
             patch.object(domain_support.session_repository, 'is_active', side_effect=(True, True, False)) as session:
            first = self.factory.get('/profile/', HTTP_AUTHORIZATION='Bearer ' + token)
            self.assertEqual(ui._private(first)[0]['role'], 'inspector')
            self.assertEqual(ui._private(first)[0]['role'], 'inspector')
            row['role'] = 'maintenance'
            second = self.factory.get('/profile/', HTTP_AUTHORIZATION='Bearer ' + token)
            self.assertEqual(ui._private(second)[0]['role'], 'maintenance')
            third = self.factory.get('/profile/', HTTP_AUTHORIZATION='Bearer ' + token)
            self.assertEqual(ui._private(third)[1].status_code, 401)
        self.assertEqual(connect.call_count, 3)
        self.assertEqual(session.call_count, 3)
