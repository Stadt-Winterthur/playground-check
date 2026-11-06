"""Pure form-model regression tests: no requests, database mocks or writes."""
import os
import unittest
from copy import deepcopy
from datetime import datetime, timezone

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
from playground_check.django_project.inspection_forms import (
    InspectionFormError, inspection_devices, bind_inspection_values, inspection_reports,
)
from playground_check.django_project.defect_forms import (
    DefectFormError, defect_update_payload, defect_edit_context,
)

KIND = 'Visuelle Inspektion (VI)'


class InspectionFormModelTests(unittest.TestCase):
    def setUp(self):
        self.payload = {'inspectionTypeOptions': [KIND], 'playdevices': [{'fid': 42, 'name': 'Schaukel', 'properties': {
            'generalInspectionCriteria': [{'check': 'Allgemein', 'maintenance': 'Reinigen'}],
            'mainFallProtectionInspectionCriteria': [{'check': 'Hauptprüfung', 'maintenance': 'Hauptwartung'}],
            'secondaryFallProtectionInspectionCriteria': [{'check': 'Nebenprüfung', 'maintenance': 'Nebenwartung'}],
        }}]}

    def form(self):
        values = {}
        for index in range(3):
            values.update({f'inspection_done_42_{index}': 'on', f'maintenance_done_42_{index}': 'on',
                           f'comment_42_{index}': ' Geprüft ', f'maintenance_comment_42_{index}': ' Gewartet '})
        return values

    def test_groups_keep_stable_indices_and_server_instructions(self):
        snapshot = deepcopy(self.payload)
        devices = inspection_devices(self.payload, KIND)
        form = {**self.form(), 'inspectionText': 'Erfunden', 'playdeviceFid': '999'}
        bind_inspection_values(devices, form)
        reports = inspection_reports(devices, form, KIND)
        self.assertEqual([check['index'] for check in devices[0]['checks']], [0, 1, 2])
        self.assertEqual([report['inspectionText'] for report in reports], ['Allgemein', 'Hauptprüfung', 'Nebenprüfung'])
        self.assertEqual([report['fallProtectionType'] for report in reports], ['', 'Hauptfallschutz', 'Nebenfallschutz'])
        self.assertTrue(all(report['playdeviceFid'] == 42 for report in reports))
        self.assertTrue(all(report['inspectionComment'] == 'Geprüft' for report in reports))
        self.assertEqual(self.payload, snapshot)

    def test_navigation_binding_retains_draft_without_marking_incomplete_checks_done(self):
        devices = inspection_devices(self.payload, KIND)
        bind_inspection_values(devices, {'comment_42_0': 'Behalten', 'inspection_done_42_0': 'on'})
        check = devices[0]['checks'][0]
        self.assertEqual(check['comment'], 'Behalten')
        self.assertTrue(check['inspection_done'])
        self.assertFalse(check['maintenance_done'])
        with self.assertRaises(InspectionFormError):
            inspection_reports(devices, {'inspection_done_42_0': 'on'}, KIND)

    def test_exempt_devices_are_omitted_and_missing_reason_is_rejected(self):
        devices = inspection_devices(self.payload, KIND)
        devices.append({**deepcopy(devices[0]), 'fid': 43, 'not_to_be_checked': True})
        devices.append({**deepcopy(devices[0]), 'fid': 44, 'cannot_be_checked': True, 'cannot_reason': 'Baustelle'})
        self.assertEqual(len(inspection_reports(devices, self.form(), KIND)), 3)
        devices[-1]['cannot_reason'] = ' '
        with self.assertRaisesRegex(InspectionFormError, 'Begründung'):
            inspection_reports(devices, self.form(), KIND)

    def test_duplicate_ids_and_overlong_comments_are_rejected(self):
        self.payload['playdevices'] *= 2
        with self.assertRaises(InspectionFormError):
            inspection_devices(self.payload, KIND)
        self.payload['playdevices'] = self.payload['playdevices'][:1]
        with self.assertRaisesRegex(InspectionFormError, 'Kommentar'):
            inspection_reports(inspection_devices(self.payload, KIND),
                               {**self.form(), 'comment_42_0': 'x' * 2001}, KIND)


class DefectFormModelTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        self.previous = {'tid': 321, 'playdevice_fid': 42, 'responsible_user_fid': 18,
                         'assignment_status': 'angenommen', 'assignment_created': self.now,
                         'assignment_comment': 'Zugewiesen', 'date_done': self.now}
        self.form = {'description': ' Neu ', 'defect_comment': ' Bemerkung ', 'priority': '1',
                     'body_id': '1', 'person_id': '18', 'done': 'on', 'record_version': '12345'}

    def test_save_preserves_database_metadata_and_concurrency_version(self):
        payload = defect_update_payload(self.previous, {**self.form, 'tid': '999', 'playdeviceFid': '888'}, self.now)
        self.assertEqual((payload['tid'], payload['playdeviceFid']), (321, 42))
        self.assertEqual(payload['expectedVersion'], '12345')
        self.assertEqual(payload['assignmentStatus'], 'angenommen')
        self.assertEqual(payload['assignmentComment'], 'Zugewiesen')
        self.assertEqual(payload['dateDone'], self.now.isoformat())
        self.assertEqual(payload['defectDescription'], 'Neu')

    def test_completion_only_uses_current_time_for_new_completion(self):
        self.previous['date_done'] = None
        self.assertEqual(defect_update_payload(self.previous, self.form, self.now)['dateDone'], self.now.isoformat())
        form = {k: v for k, v in self.form.items() if k != 'done'}
        self.assertIsNone(defect_update_payload(self.previous, form, self.now)['dateDone'])

    def test_priority_b_and_invalid_choices_are_rejected(self):
        for changes in ({'priority': '2', 'person_id': '-1'}, {'priority': 'invalid'},
                        {'body_id': '99'}, {'description': ' '}, {'defect_comment': 'x' * 256}):
            with self.subTest(changes=changes), self.assertRaises(DefectFormError):
                defect_update_payload(self.previous, {**self.form, **changes}, self.now)

    def test_error_context_keeps_user_input_and_does_not_mutate_database_payload(self):
        data = {'responsibleUserFid': 18, 'defectDescription': 'Alt', 'assignmentStatus': 'angenommen'}
        context = defect_edit_context(data, [], {'description': 'Ungespeichert', 'person_id': '17'})
        self.assertEqual(context['defect']['defectDescription'], 'Ungespeichert')
        self.assertEqual(context['defect']['responsibleUserFid'], 17)
        self.assertTrue(context['inactive_assignee'])
        self.assertEqual(data['defectDescription'], 'Alt')
