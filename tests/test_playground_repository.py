"""Regression tests for the read-only playground repository (no live database)."""
import unittest
from unittest.mock import patch
from playground_check import playground_repository, service


class FakeDB:
    def __init__(self, row=None, rows=None):
        self.row, self.rows, self.calls = row, rows if rows is not None else [], []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PlaygroundRepositoryTest(unittest.TestCase):
    def test_name_uses_bound_parameter_and_preserves_join(self):
        db = FakeDB(row={"id": 25})
        self.assertEqual(playground_repository.playground_by_name(db, "Test'platz"), {"id": 25})
        sql, args = db.calls[0]
        self.assertIn("WHERE sp.name=%s", sql)
        self.assertIn("MAX(datum_inspektion)", sql)
        self.assertEqual(args, ("Test'platz",))

    def test_device_lookup_uses_existing_fid(self):
        db = FakeDB(row={"id": 17})
        self.assertEqual(playground_repository.playground_by_device(db, 987), {"id": 17})
        sql, args = db.calls[0]
        self.assertIn('FROM "gr_v_spielgeraete"', sql)
        self.assertEqual(args, (987,))

    def test_device_rows_keep_identifiers(self):
        rows = [{"fid": 17, "has_open_defects": True}]
        db = FakeDB(rows=rows)
        self.assertIs(playground_repository.playdevice_rows(db, 99), rows)
        sql, args = db.calls[0]
        self.assertIn("WHERE spg.fid_spielplatz=%s", sql)
        self.assertEqual(args, (99,))
        self.assertNotIn("INSERT", sql.upper())

    def test_legacy_wrapper_uses_repository(self):
        db, rows = FakeDB(), [{"fid": 91}]
        with patch.object(playground_repository, "playdevice_rows", return_value=rows) as fetch:
            self.assertIs(service._playdevice_rows(db, 44), rows)
        fetch.assert_called_once_with(db, 44)

    def test_missing_name_keeps_lookup_error(self):
        db = FakeDB()
        with patch.object(service, "connect", return_value=db):
            with self.assertRaisesRegex(LookupError, "Sequence contains no elements"):
                service.playground_by_name_data({"name": "unbekannt"})
        self.assertEqual(len(db.calls), 1)

    def test_missing_device_keeps_empty_response(self):
        db = FakeDB()
        with patch.object(service, "connect", return_value=db):
            result = service.playground_by_device_data(410)
        self.assertEqual(result, {"id": 0, "name": "", "address": "", "playdevices": []})
        self.assertEqual(db.calls[0][1], (410,))

    def test_nonpositive_fid_does_not_connect(self):
        with patch.object(service, "connect") as connection:
            self.assertEqual(service.playground_by_device_data(0)["id"], 0)
        connection.assert_not_called()
