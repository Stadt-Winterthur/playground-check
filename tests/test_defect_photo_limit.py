"""Photo limits and replacement must be atomic and not discard previously saved rows."""
import unittest
from playground_check.picture_write_repository import (
    save_defect_picture, DefectPhotoLimitError, DefectPhotoTargetError,
)

class Cursor:
    def __init__(self, row): self.row = row
    def fetchone(self): return self.row

class DB:
    def __init__(self, count=0, match=True):
        self.count, self.match, self.calls = count, match, []
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if 'COUNT(*)' in sql: return Cursor({'amount': self.count})
        if sql.startswith('SELECT tid FROM'): return Cursor({'tid': 11} if self.match else None)
        return Cursor({'tid': 11})

class DefectPhotoLimitTests(unittest.TestCase):
    def test_first_three_uploads_allowed(self):
        for count in (0, 1, 2):
            db = DB(count)
            self.assertEqual(save_defect_picture(db, 77, 'raw', 'small', False), {'tid': 11})
            self.assertIn('LOCK TABLE', db.calls[0][0])
            self.assertIn('INSERT INTO', db.calls[-1][0])
            self.assertEqual(db.calls[-2][1], (77, False))

    def test_fourth_upload_rejected_before_write(self):
        db = DB(3)
        with self.assertRaises(DefectPhotoLimitError):
            save_defect_picture(db, 77, 'raw', 'small', True)
        self.assertFalse(any('INSERT INTO' in sql or 'UPDATE' in sql for sql, _ in db.calls))
        self.assertEqual(db.calls[-1][1], (77, True))

    def test_three_before_do_not_block_first_after_photo(self):
        db = DB(0)
        self.assertEqual(save_defect_picture(db, 77, 'raw', 'small', True), {'tid': 11})
        self.assertEqual(db.calls[-2][1], (77, True))

    def test_existing_photo_can_be_replaced_at_limit_without_changing_identity(self):
        db = DB(3)
        self.assertEqual(save_defect_picture(db, 77, 'new', 'thumbnail', True, 11), {'tid': 11})
        self.assertIn('UPDATE', db.calls[-1][0]); self.assertNotIn('DELETE', str(db.calls))
        self.assertEqual(db.calls[-1][1], ('new', 'thumbnail', 11, 77))

    def test_replacement_cannot_target_another_defect_or_category(self):
        db = DB(2, match=False)
        with self.assertRaises(DefectPhotoTargetError):
            save_defect_picture(db, 77, 'new', 'thumbnail', False, 11)
        self.assertFalse(any('UPDATE' in sql for sql, _ in db.calls))

if __name__ == '__main__': unittest.main()

class DefectPhotoDeleteTests(unittest.TestCase):
    def test_delete_is_scoped_to_defect_photo_and_category(self):
        from playground_check.picture_write_repository import delete_defect_picture
        db = DB()
        self.assertTrue(delete_defect_picture(db, 77, 11, True))
        self.assertIn('LOCK TABLE', db.calls[0][0])
        query, params = db.calls[-1]
        self.assertIn('DELETE FROM', query)
        self.assertIn('tid_maengel=%s', query)
        self.assertIn('zeitpunkt=%s', query)
        self.assertEqual(params, (11, 77, True))

    def test_missing_photo_returns_false(self):
        from playground_check.picture_write_repository import delete_defect_picture
        class MissingDB(DB):
            def execute(self, sql, params=None):
                self.calls.append((sql, params))
                return Cursor(None)
        self.assertFalse(delete_defect_picture(MissingDB(), 77, 11, False))
