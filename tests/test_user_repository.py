"""Verify the original user read SQL remains bound and preserves its ordering."""
import unittest
from playground_check import user_repository


class DB:
    def __init__(self):
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self
    def fetchone(self):
        return {'fid': 42}
    def fetchall(self):
        return [{'fid': 42}]


class UserRepositoryTest(unittest.TestCase):
    def test_single_user_lookup_binds_email(self):
        db = DB()
        self.assertEqual(user_repository.user_by_email(db, 'person@example.org')['fid'], 42)
        self.assertEqual(db.calls[-1][1], ('person@example.org',))
        self.assertIn('trim(lower(e_mail))=%s', db.calls[-1][0])

    def test_multiple_user_lookup_binds_email(self):
        db = DB()
        self.assertEqual(len(user_repository.users_by_email(db, 'person@example.org')), 1)
        self.assertEqual(db.calls[-1][1], ('person@example.org',))

    def test_unfiltered_list_orders_by_name(self):
        db = DB()
        user_repository.users(db)
        self.assertEqual(db.calls[-1][1], ())
        self.assertTrue(db.calls[-1][0].endswith(' ORDER BY vorname, nachname'))

    def test_filtered_list_binds_email_and_orders(self):
        db = DB()
        user_repository.users(db, 'person@example.org')
        sql, params = db.calls[-1]
        self.assertEqual(params, ('person@example.org',))
        self.assertIn('WHERE trim(lower(e_mail))=%s ORDER BY vorname, nachname', sql)

    def test_assignable_users_only_active(self):
        db = DB()
        user_repository.assignable_users(db)
        self.assertIn('WHERE aktiv=true ORDER BY vorname, nachname', db.calls[-1][0])
        self.assertEqual(db.calls[-1][1], ())


if __name__ == '__main__':
    unittest.main()
