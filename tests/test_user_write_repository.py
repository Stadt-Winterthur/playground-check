"""Regression checks for the previously inline account write statements."""
import unittest
from playground_check import user_write_repository as repo


class DB:
    def __init__(self):
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self
    def fetchone(self):
        return {'count': 1}
    @property
    def rowcount(self):
        return 1


class UserWriteRepositoryTest(unittest.TestCase):
    def test_login_attempt_uses_bound_email(self):
        db = DB()
        repo.record_login_attempt(db, 'a@example.org')
        self.assertIn('letzter_anmeldeversuch=CURRENT_TIMESTAMP', db.calls[0][0])
        self.assertEqual(db.calls[0][1], ('a@example.org',))

    def test_password_hash_is_bound_not_logged_into_sql(self):
        db = DB()
        self.assertEqual(repo.update_password(db, 'a@example.org', 'hashed-secret'), 1)
        sql, params = db.calls[0]
        self.assertIn('SET pwd=%s', sql)
        self.assertNotIn('hashed-secret', sql)
        self.assertEqual(params, ('hashed-secret', 'a@example.org'))

    def test_registration_creates_inactive_inspector_without_fid(self):
        db = DB()
        repo.register_pending_user(db, 'Last', 'First', 'a@example.org', 'hash')
        sql, params = db.calls[0]
        self.assertIn("'inspector', false, true", sql)
        self.assertNotIn('fid,', sql)
        self.assertEqual(params, ('Last', 'First', 'a@example.org', 'hash'))

    def test_update_keeps_all_values_and_existing_email(self):
        db = DB()
        self.assertEqual(repo.update_user(db, 'a@example.org', 'L', 'F', 'maintenance', None, False, True), 1)
        self.assertEqual(db.calls[0][1], ('L', 'F', 'maintenance', None, False, True, 'a@example.org'))

    def test_admin_count_and_deactivation(self):
        db = DB()
        self.assertEqual(repo.active_admin_count(db), 1)
        self.assertIn("rolle='administrator'", db.calls[0][0])
        self.assertEqual(repo.deactivate_user(db, 'a@example.org'), 1)
        self.assertIn('SET aktiv=false', db.calls[1][0])
        self.assertEqual(db.calls[1][1], ('a@example.org',))


if __name__ == '__main__':
    unittest.main()
