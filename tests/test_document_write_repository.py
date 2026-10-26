"""Regression tests for the PostgreSQL document-FID exception."""
import unittest

from playground_check import document_write_repository as repo


class FakeDB:
    def __init__(self, *, next_fid=42, document=None, deleted=None):
        self.calls = []
        self.next_fid = next_fid
        self.document = document
        self.deleted = deleted
        self.last_sql = ""

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        self.last_sql = sql
        return self

    def fetchone(self):
        if "COALESCE(MAX(fid)" in self.last_sql:
            return {"fid": self.next_fid}
        if "SELECT" in self.last_sql:
            return self.document
        if "DELETE" in self.last_sql:
            return self.deleted
        return None


class DocumentWriteRepositoryTest(unittest.TestCase):
    def test_upload_locks_before_allocating_document_fid_and_insert(self):
        db = FakeDB(next_fid=221)
        fid = repo.insert_document(db, "wgr_sp_abnahmen", "abnahmedokument", 91, b"%PDF-1.7")
        self.assertEqual(fid, 221)
        self.assertEqual(len(db.calls), 3)
        self.assertIn('LOCK TABLE "wgr_sp_abnahmen" IN EXCLUSIVE MODE', db.calls[0][0])
        self.assertIn('MAX(fid)', db.calls[1][0])
        self.assertIn('INSERT INTO "wgr_sp_abnahmen"', db.calls[2][0])
        self.assertEqual(db.calls[2][1], (221, 91, b"%PDF-1.7"))

    def test_certificate_uses_its_existing_document_column(self):
        db = FakeDB(next_fid=3)
        repo.insert_document(db, "wgr_sp_zertifikat", "zertifikatsdokument", 22, b"content")
        self.assertIn("zertifikatsdokument", db.calls[2][0])
        self.assertEqual(db.calls[2][1], (3, 22, b"content"))

    def test_rename_fetches_existing_content_and_updates_same_fid(self):
        db = FakeDB(document={"content": b"existing"})
        self.assertEqual(repo.document_content(db, "wgr_sp_abnahmen", "abnahmedokument", 25), {"content": b"existing"})
        repo.rename_document(db, "wgr_sp_abnahmen", "abnahmedokument", 25, b"new")
        self.assertEqual(db.calls[0][1], (25,))
        self.assertEqual(db.calls[1][1], (b"new", 25))

    def test_delete_returns_existing_fid_or_missing(self):
        db = FakeDB(deleted={"fid": 5})
        self.assertEqual(repo.delete_document(db, "wgr_sp_zertifikat", 5), {"fid": 5})
        self.assertEqual(db.calls[0][1], (5,))
        self.assertIsNone(repo.delete_document(FakeDB(), "wgr_sp_zertifikat", 6))

    def test_unknown_table_or_mismatched_column_never_reaches_database(self):
        db = FakeDB()
        with self.assertRaises(ValueError):
            repo.insert_document(db, "other_table", "abnahmedokument", 1, b"PDF")
        with self.assertRaises(ValueError):
            repo.rename_document(db, "wgr_sp_abnahmen", "zertifikatsdokument", 5, b"PDF")
        with self.assertRaises(ValueError):
            repo.delete_document(db, "unknown", 5)
        self.assertEqual(db.calls, [])


if __name__ == "__main__":
    unittest.main()
