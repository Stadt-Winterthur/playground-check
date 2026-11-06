"""Renovation editor: business-year validation and saved form response."""
import os
import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.test import RequestFactory
from playground_check.django_project import python_ui_workflows as workflows


class RenovationEditorTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(workflows, '_guard', return_value=({'fid': 17, 'role': 'inspector'}, None)))
        self.stack.enter_context(patch.object(workflows, 'local_today', return_value=date(2032, 1, 1)))
        self.stack.enter_context(patch('playground_check.playdevice_service.local_today', return_value=date(2032, 1, 1)))
        self.db = MagicMock()
        self.db.__enter__.return_value = self.db
        self.db.execute.return_value.fetchone.return_value = {}
        self.db.execute.return_value.fetchall.return_value = [{'id': 2, 'value': 'Ersatz'}]
        self.stack.enter_context(patch('playground_check.db.connect', return_value=self.db))
        self.write = self.stack.enter_context(patch('playground_check.playdevice_write_repository.update_renovation_only', return_value=1))
        self.factory = RequestFactory()

    def post(self, year):
        request = self.factory.post('/device/edit/', {
            'fid': '42', 'recommendedYearOfRenovation': year, 'renovationType': '2',
            'commentRecommendedYearOfRenovation': 'Ersatz vorsehen',
        }, SCRIPT_NAME='/stadtgruen/spielplatzkontrolle')
        request._dont_enforce_csrf_checks = True
        return workflows.device_editor(request)

    def test_get_dynamic_minimum_without_visible_fid_or_notice(self):
        props = {'recommendedYearOfRenovation': 2031, 'renovationType': 2}
        with patch('playground_check.domain_support.playground_by_device_data',
                   return_value={'playdevices': [{'properties': props}]}):
            response = workflows.device_editor(self.factory.get('/device/edit/', {'fid': '42'}))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('min="2032"', html)
        self.assertIn('value="2031"', html)  # Existing values remain visible for correction.
        self.assertNotIn('Spielgeraet FID', html)
        self.assertNotIn('Die Angaben zur Pruefbarkeit', html)
        self.assertNotIn('data-renovation-saved', html)

    def test_previous_year_rejected_before_any_write(self):
        response = self.post('2031')
        self.assertEqual(response.status_code, 400)
        self.write.assert_not_called()

    def test_current_future_and_empty_year_save_to_same_form(self):
        for year, expected in [('2032', 2032), ('2033', 2033), ('', None)]:
            with self.subTest(year=year):
                response = self.post(year)
                self.assertEqual(response.status_code, 200)
                self.write.assert_called_with(self.db, expected, 2, 'Ersatz vorsehen', 42)
                html = response.content.decode()
                self.assertIn('Sanierungsangaben bearbeiten', html)
                self.assertIn('>gespeichert</p>', html)
                self.assertLess(html.index('Sanierungsangaben speichern'), html.index('data-renovation-saved'))
                self.assertIn('Ersatz vorsehen</textarea>', html)
                self.assertIn('value="2" selected', html)
                self.assertIn('/stadtgruen/spielplatzkontrolle/static/js/device-renovation.js', html)
                self.assertIn("script-src 'self'", response['Content-Security-Policy'])

    def test_write_failure_does_not_show_success(self):
        self.write.side_effect = RuntimeError('write failed')
        with self.assertLogs(workflows.LOG, level='ERROR'):
            response = self.post('2032')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('data-renovation-saved', response.content.decode())
