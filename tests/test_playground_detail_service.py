"""Regression tests for the read-only playground detail orchestration."""
import unittest
from unittest.mock import patch

from playground_check import playground_detail_service, service


class FakeDB:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        sql = self.calls[-1][0]
        if 'wgr_sp_dringlichkeit_tbd' in sql:
            return [{'id': 2, 'short_value': '2', 'value': 'Mittel'}]
        if 'wgr_sp_inspektionsart_tbd' in sql:
            return [{'short_value': 'HI', 'value': 'Hauptinspektion'}]
        if 'wgr_sp_sanierungsart_tbd' in sql:
            return [{'id': 1, 'value': 'Reparieren'}, {'id': 2, 'value': 'Ersetzen'}]
        if 'wgr_sp_zust_mangelbeheb_tbd' in sql:
            return [{'id': 7, 'value': 'Stadtgruen'}]
        if 'wgr_sp_abnahmen' in sql:
            return [{'fid': 45, 'meta_tail': b'a'}]
        if 'wgr_sp_zertifikat' in sql:
            return [{'fid': 46, 'meta_tail': b'b'}]
        raise AssertionError(f'Unexpected query: {sql}')


class PlaygroundDetailServiceTest(unittest.TestCase):
    def build(self, *, compatibility=False):
        db = FakeDB()
        devices = [{'fid': 100}, {'fid': 101, 'not_to_be_checked': True}]
        calls = []

        def build_device(connection, device, kind, defects, inspections):
            calls.append((connection, device['fid'], kind, defects, inspections))
            return {'fid': device['fid']}

        result = playground_detail_service.build_playground_detail(
            db, {'id': 10, 'name': 'Testplatz'}, 'HI', True, False,
            load_devices=lambda connection, fid: devices,
            build_device=build_device,
            document_name=lambda data, fallback: 'Name-' + fallback,
            compatibility_bugs=compatibility,
            min_date='0001-01-01T00:00:00',
        )
        return db, result, calls

    def test_payload_keeps_existing_fids_and_filters_hidden_devices(self):
        db, result, calls = self.build()
        self.assertEqual(result['id'], 10)
        self.assertEqual(result['playdevices'], [{'fid': 100}])
        self.assertEqual(calls, [(db, 100, 'HI', True, False)])
        self.assertEqual(result['documentsOfAcceptanceFids'], [45])
        self.assertEqual(result['certificateDocuments'], [{'fid': 46, 'name': 'Name-46'}])
        self.assertEqual(result['defectPriorityOptions'], ['2 (Mittel)'])
        self.assertEqual(result['inspectionTypeOptions'], ['Hauptinspektion (HI)'])
        self.assertTrue(all(not sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql, _ in db.calls))

    def test_legacy_renovation_compatibility_remains_optional(self):
        _, normal, _ = self.build()
        _, legacy, _ = self.build(compatibility=True)
        self.assertEqual(normal['renovationTypeOptions'], [{'id': 1, 'value': 'Reparieren'}, {'id': 2, 'value': 'Ersetzen'}])
        self.assertEqual(legacy['renovationTypeOptions'], [{'id': 2, 'value': 'Ersetzen'}] * 2)

    def test_service_wrapper_passes_current_dependencies(self):
        db = FakeDB()
        with patch.object(service, '_playdevice_rows', return_value=[]), patch.object(service, '_document_name_from_tail', return_value='dokument'):
            result = service._playground_result(db, {'id': 55}, '', False, False)
        self.assertEqual(result['id'], 55)
        self.assertEqual(db.calls[-1][1], (55,))
