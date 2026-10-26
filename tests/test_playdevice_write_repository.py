"""Unit tests for device writes without a live PostgreSQL connection."""
import unittest

from playground_check import playdevice_write_repository as repository


class Database:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((statement, params))


class PlaydeviceWriteRepositoryTest(unittest.TestCase):
    def test_update_uses_existing_fid_and_no_insert(self):
        db = Database()
        repository.update_playdevice(db, 2031, 4, "Kommentar", True, "Grund", 1234)
        self.assertEqual(len(db.calls), 1)
        statement, params = db.calls[0]
        self.assertIn('UPDATE "gr_v_spielgeraete"', statement)
        self.assertIn('WHERE fid=%s', statement)
        self.assertNotIn('INSERT', statement.upper())
        self.assertEqual(params, (2031, 4, "Kommentar", True, "Grund", 1234))

    def test_update_keeps_nulls_and_blank_reason(self):
        db = Database()
        repository.update_playdevice(db, None, None, None, False, "", 86)
        self.assertEqual(db.calls[0][1], (None, None, None, False, "", 86))

    def test_database_exception_remains_caller_responsibility(self):
        class FailingDatabase:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError("db unavailable")
        with self.assertRaisesRegex(RuntimeError, "db unavailable"):
            repository.update_playdevice(FailingDatabase(), None, None, None, False, "", 8)
