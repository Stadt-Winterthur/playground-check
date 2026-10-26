"""Regression contracts for inspection writes; no PostgreSQL connection used."""
from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from playground_check import inspection_write_repository as repository
from playground_check import service
from test_write_operations_contract import WriteOperationContractTest


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class Recorder:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return Result({"tid": 802})


class InspectionWriteRepositoryTest(unittest.TestCase):
    def test_lock_covers_both_tables(self):
        db = Recorder()
        repository.lock_inspection_tables(db)
        self.assertEqual(len(db.calls), 1)
        self.assertEqual(db.calls[0][0], 'LOCK TABLE "wgr_sp_inspektion", "wgr_sp_insp_bericht" IN EXCLUSIVE MODE')

    def test_parent_insert_allocates_tid_without_fid_column(self):
        db = Recorder()
        tid = repository.insert_inspection(db, 1, 34, date(2026, 10, 26), 12, None)
        self.assertEqual(tid, 802)
        sql, params = db.calls[0]
        self.assertIn('INSERT INTO "wgr_sp_inspektion"', sql)
        self.assertIn('max(tid)+1', sql)
        self.assertIn('RETURNING tid', sql)
        self.assertNotIn('(fid,', sql)
        self.assertEqual(params, (1, 34, date(2026, 10, 26), 12, None))

    def test_report_references_parent_tid_and_existing_device_fid(self):
        db = Recorder()
        repository.insert_report(db, 802, 123, {
            "playdeviceDetailFid": 456, "inspectionText": "Check",
            "inspectionDone": True, "maintenanceDone": False,
        }, "Visuelle Inspektion (VI)", date(2026, 10, 26), "Test User", bool)
        sql, params = db.calls[0]
        self.assertIn('INSERT INTO "wgr_sp_insp_bericht"', sql)
        self.assertIn('max(tid)+1', sql)
        self.assertNotIn('(fid,', sql)
        self.assertEqual(params[:4], (802, 123, 456, "Visuelle Inspektion (VI)"))
        self.assertEqual(params[7], 1)
        self.assertEqual(params[10], 0)

    def test_existing_endpoint_preserves_lock_duplicate_and_insert_order(self):
        case = WriteOperationContractTest(methodName='test_inspection_insert_uses_tid_and_existing_playground_fid')
        case.setUp()
        case.db.responses = [
            {"fid": 12}, {"id": 1}, {"fid_spielplatz": 34},
            {"exists": 1}, {"fid_spielplatz": 34}, None,
            {"target": None}, {"tid": 802},
            {"nicht_zu_pruefen": False, "nicht_pruefbar": False},
        ]
        status, body = case.request("POST", "/Inspection/", [{
            "inspectionType": "Visuelle Inspektion (VI)",
            "playdeviceFid": 123, "inspectionText": "Pruefung", "inspectionDone": True,
        }])
        self.assertEqual((status, body), (200, {"errorMessage": ""}))
        statements = [sql.strip().upper() for sql, _ in case.db.calls]
        lock = next(i for i, sql in enumerate(statements) if sql.startswith('LOCK TABLE'))
        duplicate = next(i for i, sql in enumerate(statements) if 'DATUM_INSPEKTION::DATE' in sql)
        parent = next(i for i, sql in enumerate(statements) if sql.startswith('INSERT INTO "WGR_SP_INSPEKTION"'))
        child = next(i for i, sql in enumerate(statements) if sql.startswith('INSERT INTO "WGR_SP_INSP_BERICHT"'))
        self.assertLess(lock, duplicate)
        self.assertLess(duplicate, parent)
        self.assertLess(parent, child)

    def test_insert_error_preserves_spk3_response(self):
        case = WriteOperationContractTest(methodName='test_inspection_insert_uses_tid_and_existing_playground_fid')
        case.setUp()
        case.db.responses = [
            {"fid": 12}, {"id": 1}, {"fid_spielplatz": 34},
            {"exists": 1}, {"fid_spielplatz": 34}, None, {"target": None},
        ]
        with patch.object(service.inspection_write_repository, 'insert_inspection', side_effect=RuntimeError('DB down')):
            status, body = case.request("POST", "/Inspection/", [{
                "inspectionType": "Visuelle Inspektion (VI)", "playdeviceFid": 123,
            }])
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-3"}))


if __name__ == '__main__':
    unittest.main()
