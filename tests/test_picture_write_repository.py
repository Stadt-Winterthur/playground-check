"""Regression contracts for image writes; no live database connection."""
from __future__ import annotations

import unittest
from playground_check import picture_write_repository as repo


class FakeCursor:
    def fetchone(self):
        return {"tid": 456}


class FakeDB:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeCursor()


class PictureWriteRepositoryTests(unittest.TestCase):
    def test_device_picture_uses_existing_fid(self):
        db = FakeDB()
        repo.update_playdevice_picture(db, 123, b"image")
        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn('UPDATE "gr_v_spielgeraete"', sql)
        self.assertEqual(params, (b"image", 123))
        self.assertNotIn('INSERT', sql.upper())

    def test_defect_picture_locks_before_tid_insert(self):
        db = FakeDB()
        row = repo.insert_defect_picture(db, 901, "photo", "thumb", True)
        self.assertEqual(row, {"tid": 456})
        self.assertEqual(len(db.calls), 2)
        self.assertIn('LOCK TABLE "wgr_sp_insp_mangel_foto"', db.calls[0][0])
        self.assertIn('COALESCE(MAX(tid),0)+1', db.calls[1][0])
        self.assertIn('RETURNING tid', db.calls[1][0])
        self.assertEqual(db.calls[1][1], (901, "photo", "thumb", True))
        self.assertNotIn(' fid', db.calls[1][0].lower())

    def test_device_picture_accepts_existing_string_encoding(self):
        db = FakeDB()
        repo.update_playdevice_picture(db, 42, 'base64-text')
        self.assertEqual(db.calls[0][1], ('base64-text', 42))
