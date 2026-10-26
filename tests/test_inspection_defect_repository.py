"""Unit contract tests for read-only inspection/defect queries (no PostgreSQL)."""
import unittest
from unittest.mock import patch

from playground_check import inspection_defect_repository as repo, service


class FakeDB:
    def __init__(self, rows=None, row=None):
        self.rows = [] if rows is None else rows
        self.row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class InspectionDefectRepositoryTest(unittest.TestCase):
    def test_criteria_use_bound_values_and_approved_relation(self):
        db = FakeDB(rows=[{"realm": "Sicherheit"}])
        self.assertEqual(repo.criteria_rows(db, "wgr_v_sp_ger_insp_krit", "inspektionsart", 42, "HI"), db.rows)
        sql, params = db.calls[0]
        self.assertIn('FROM "wgr_v_sp_ger_insp_krit"', sql)
        self.assertEqual(params, (42, "HI"))

    def test_unrecognized_relation_rejected_before_database_query(self):
        db = FakeDB()
        with self.assertRaises(ValueError):
            repo.criteria_rows(db, 'wgr_v_sp_ger_insp_krit";DROP TABLE users;--', "inspektionsart", 1, "HI")
        self.assertEqual(db.calls, [])

    def test_inspection_history_uses_existing_device_fid(self):
        db = FakeDB(rows=[{"inspection_tid": 91, "inspection_type": "HI"}])
        self.assertIs(repo.inspection_report_rows(db, 12, "HI"), db.rows)
        sql, params = db.calls[0]
        self.assertIn('FROM "wgr_sp_insp_bericht"', sql)
        self.assertEqual(params, (12, "HI", 12, "HI"))

    def test_open_defects_are_read_only_and_bound_to_fid(self):
        db = FakeDB(rows=[{"tid": 100}])
        self.assertIs(repo.open_device_defects(db, 12), db.rows)
        sql, params = db.calls[0]
        self.assertIn('datum_erledigung IS NULL', sql)
        self.assertEqual(params, (12,))
        self.assertTrue(sql.lstrip().upper().startswith('SELECT'))

    def test_defect_lookup_uses_tid_not_fid(self):
        db = FakeDB(row={"tid": 900, "playdevice_fid": 12})
        self.assertEqual(repo.defect_by_tid(db, 900), db.row)
        sql, params = db.calls[0]
        self.assertIn('WHERE tid=%s', sql)
        self.assertEqual(params, (900,))

    def test_service_keeps_criteria_serialization(self):
        db = FakeDB()
        with patch.object(repo, 'criteria_rows', return_value=[]) as fetch:
            self.assertEqual(service._criteria(db, 'wgr_v_sp_ger_insp_krit', 'inspektionsart', 12, 'HI'), [])
        fetch.assert_called_once_with(db, 'wgr_v_sp_ger_insp_krit', 'inspektionsart', 12, 'HI')


if __name__ == '__main__':
    unittest.main()
