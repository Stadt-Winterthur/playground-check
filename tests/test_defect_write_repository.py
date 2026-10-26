"""Regression checks for the PostgreSQL defect write boundary (no real database)."""
from __future__ import annotations

import unittest
from datetime import datetime

from playground_check import defect_write_repository as repository


class FakeCursor:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class FakeDatabase:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query.lstrip().startswith("INSERT INTO"):
            return FakeCursor({"tid": 734})
        if query.lstrip().startswith("SELECT"):
            return FakeCursor({"responsible_user_fid": 47})
        return FakeCursor(None)


class DefectWriteRepositoryTest(unittest.TestCase):
    def test_insert_locks_before_allocating_transfer_id_and_never_sets_fid(self):
        db = FakeDatabase()
        body = {"playdeviceFid": 234, "priority": 1, "defectDescription": "Test",
                "tid": 9999, "fid": 8888}
        row = repository.insert_defect(db, body, {"fid": 42}, None, -1, None, None)
        self.assertEqual(row, {"tid": 734})
        self.assertEqual(len(db.calls), 2)
        self.assertEqual(db.calls[0][0], 'LOCK TABLE "wgr_sp_insp_mangel" IN EXCLUSIVE MODE')
        sql, params = db.calls[1]
        self.assertIn('max(tid)+1', sql)
        self.assertIn('RETURNING tid', sql)
        self.assertNotIn('fid, tid', sql.lower())
        self.assertNotIn('8888', str(params))
        self.assertNotIn('9999', str(params))
        self.assertEqual(params[0], 234)

    def test_insert_keeps_assignment_columns_and_existing_user_fid(self):
        db = FakeDatabase()
        assigned_at = datetime(2026, 10, 26, 10, 0)
        repository.insert_defect(db, {"playdeviceFid": 123, "priority": 2,
            "defectDescription": "Mangel", "assignmentComment": "Hinweis"},
            {"fid": 9}, None, 47, 4, assigned_at)
        params = db.calls[1][1]
        self.assertEqual(params[6:10], (4, 47, 'zugewiesen', assigned_at))
        self.assertEqual(params[-1], 9)

    def test_existing_assignment_uses_tid_parameter(self):
        db = FakeDatabase()
        self.assertEqual(repository.current_responsible(db, 711), {"responsible_user_fid": 47})
        self.assertEqual(db.calls[0][1], (711,))

    def test_update_resets_assignment_and_mail_columns_on_change(self):
        db = FakeDatabase()
        repository.update_defect(db, {"tid": 711, "priority": 1, "defectDescription": "neu"},
            None, None, 47, "zugewiesen", None, None, None)
        sql, params = db.calls[0]
        self.assertIn('infomail_gesendet_am=CASE', sql)
        self.assertIn('datum_auftrag_angenommen=CASE', sql)
        self.assertIn('WHERE tid=%s', sql)
        self.assertEqual(params[-1], 711)
        self.assertEqual(params[9:13], (47, 47, 47, 47))
        self.assertNotIn('INSERT', sql)


if __name__ == "__main__":
    unittest.main()
