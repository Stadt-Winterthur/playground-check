"""Device rules apply to every entry point, with no live database writes."""
import json
import os
import unittest
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
from playground_check import playdevice_service as rules


class Database:
    def __init__(self, **state):
        self.state = {'recommended_year': 2031, 'renovation_type': 2,
                      'renovation_comment': 'Bestehend', 'not_to_be_checked': False,
                      'cannot_be_checked': True, 'cannot_be_checked_reason': 'Baustelle', **state}
        self.exists = True
        self.rowcount = 1
        self.writes = []

    def execute(self, sql, params=None):
        if 'FOR UPDATE' in sql:
            return SimpleNamespace(fetchone=lambda: dict(self.state) if self.exists else None)
        if 'SELECT id FROM "wgr_sp_sanierungsart_tbd"' in sql:
            return SimpleNamespace(fetchone=lambda: {'id': params[0]} if params[0] in (2, 3) else None)
        if sql.lstrip().startswith('UPDATE'):
            self.writes.append((sql, params))
            return SimpleNamespace(rowcount=self.rowcount)
        raise AssertionError(sql)


class DeviceRulesTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.clock = patch.object(rules, 'local_today', return_value=date(2030, 1, 1))
        self.clock.start(); self.addCleanup(self.clock.stop)

    def test_missing_or_excessive_reason_prevents_all_writes(self):
        for reason in ('', '  ', 'x' * 256):
            with self.subTest(reason_length=len(reason)), self.assertRaises(rules.DeviceWriteError):
                rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': True,
                    'cannotBeCheckedReason': reason, 'recommendedYearOfRenovation': 2032})
        self.assertEqual(self.db.writes, [])

    def test_valid_reason_is_trimmed_and_renovation_is_untouched(self):
        result = rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': True,
                                            'cannotBeCheckedReason': '  ' + 'x' * 255 + '  '})
        sql, params = self.db.writes[0]
        self.assertEqual(params, (True, 'x' * 255, 42))
        self.assertNotIn('empfohlenes_sanierungsjahr=', sql)
        self.assertEqual(result['cannotBeCheckedReason'], 'x' * 255)

    def test_clearing_checkability_also_clears_reason(self):
        rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': False})
        self.assertEqual(self.db.writes[0][1], (False, '', 42))

    def test_renovation_patch_preserves_omitted_fields_and_checkability(self):
        rules.save_device(self.db, {'fid': 42, 'renovationType': 3})
        sql, params = self.db.writes[0]
        self.assertEqual(params, (2031, 3, 'Bestehend', 42))
        self.assertNotIn('nicht_pruefbar=', sql)

    def test_existing_past_year_can_remain_when_editing_other_fields(self):
        self.db.state['recommended_year'] = 2029
        rules.save_device(self.db, {'fid': 42, 'commentRecommendedYearOfRenovation': 'Neu'})
        self.assertEqual(self.db.writes[0][1], (2029, 2, 'Neu', 42))

    def test_invalid_year_type_comment_flag_or_fid_prevents_write(self):
        for changes in ({'recommendedYearOfRenovation': 2029},
                        {'recommendedYearOfRenovation': 2201},
                        {'renovationType': 999}, {'renovationType': -2},
                        {'commentRecommendedYearOfRenovation': 'x' * 2001},
                        {'cannotBeChecked': 'maybe'}, {'fid': True}, {'fid': 0}, {'fid': 1.5}):
            with self.subTest(changes=changes), self.assertRaises(rules.DeviceWriteError):
                rules.save_device(self.db, {'fid': 42, **changes})
        self.assertEqual(self.db.writes, [])

    def test_exempt_device_cannot_be_changed_via_combined_api_payload(self):
        self.db.state['not_to_be_checked'] = True
        with self.assertRaises(rules.DeviceWriteError) as caught:
            rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': False, 'renovationType': 3})
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(self.db.writes, [])

    def test_exemption_is_never_written(self):
        rules.save_device(self.db, {'fid': 42, 'notToBeChecked': True, 'renovationType': 3})
        self.assertNotIn('nicht_zu_pruefen=', self.db.writes[0][0])

    def test_both_groups_are_written_once_after_full_validation(self):
        rules.save_device(self.db, {'fid': 42, 'recommendedYearOfRenovation': 0,
            'renovationType': 0, 'commentRecommendedYearOfRenovation': '', 'cannotBeChecked': False})
        self.assertEqual(len(self.db.writes), 1)
        self.assertEqual(self.db.writes[0][1], (None, None, None, False, '', 42))
        self.assertIn('COALESCE(nicht_zu_pruefen, false)=false', self.db.writes[0][0])

    def test_missing_device_and_unexpected_rowcounts_never_report_success(self):
        self.db.exists = False
        with self.assertRaises(rules.DeviceWriteError) as caught:
            rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': False})
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.db.writes, [])
        self.db.exists = True
        for rowcount in (0, 2):
            self.db.rowcount = rowcount
            with self.subTest(rowcount=rowcount), self.assertRaises(rules.DeviceWriteError) as caught:
                rules.save_device(self.db, {'fid': 42, 'cannotBeChecked': False})
            self.assertEqual(caught.exception.status, 409)


class DeviceAPIParityTests(unittest.TestCase):
    def test_native_and_compatibility_paths_enforce_the_same_rules(self):
        from playground_check import service, domain_support
        from playground_check.http import Request
        from playground_check.django_project import inspection_device_commands as native
        from playground_check.django_project.ui_command_adapter import CommandInput
        from io import BytesIO
        user = {'fid': 17, 'role': 'inspector'}
        for implementation, owner in ((native.save_playdevice, domain_support), (service.save_playdevice, service)):
            for properties, status in (({'fid': 42, 'cannotBeChecked': True, 'cannotBeCheckedReason': ''}, 400),
                                       ({'fid': 42, 'cannotBeChecked': True, 'cannotBeCheckedReason': 'x' * 256}, 400),
                                       ({'fid': 42, 'cannotBeChecked': False}, 200)):
                db = Database()
                @contextmanager
                def connection():
                    yield db
                body = json.dumps({'properties': properties}).encode()
                meta = {'REQUEST_METHOD': 'POST', 'CONTENT_LENGTH': str(len(body)),
                        'CONTENT_TYPE': 'application/json', 'wsgi.input': BytesIO(body)}
                request = CommandInput(meta, body) if owner is domain_support else Request(meta)
                with self.subTest(implementation=implementation.__module__, status=status), \
                     patch.object(owner, 'require_user', return_value=(user, None)), \
                     patch.object(owner, 'connect', connection):
                    response = implementation(request)
                    actual_status = response.status_code if owner is domain_support else response.status
                    self.assertEqual(actual_status, status)
                    self.assertEqual(len(db.writes), 1 if status == 200 else 0)

    def test_native_api_reports_missing_device_and_ignores_noop_success(self):
        from playground_check import domain_support
        from playground_check.django_project import inspection_device_commands as native
        from playground_check.django_project.ui_command_adapter import CommandInput
        for exists, count, expected in ((False, 1, 404), (True, 0, 409)):
            db = Database(); db.exists = exists; db.rowcount = count
            @contextmanager
            def connection():
                yield db
            body = b'{"properties":{"fid":42,"cannotBeChecked":false}}'
            with self.subTest(expected=expected), \
                 patch.object(domain_support, 'require_user', return_value=({'role': 'inspector'}, None)), \
                 patch.object(domain_support, 'connect', connection):
                response = native.save_playdevice(CommandInput({}, body))
            self.assertEqual(response.status_code, expected)
            self.assertTrue(json.loads(response.content)['errorMessage'])
