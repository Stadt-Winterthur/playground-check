"""Contract tests for the push-subscription repository (no real database)."""
import unittest
from unittest.mock import MagicMock
from playground_check import push_repository


class PushRepositoryTests(unittest.TestCase):
    def test_register_preserves_upsert_and_user_fid(self):
        db = MagicMock()
        push_repository.register_subscription(db, 123, 'https://push.example/endpoint', 'key', 'secret', 'Browser')
        sql, params = db.execute.call_args.args
        self.assertIn('ON CONFLICT (endpoint) DO UPDATE', sql)
        self.assertIn('aktiv=true', sql)
        self.assertEqual(params, (123, 'https://push.example/endpoint', 'key', 'secret', 'Browser'))
        self.assertNotIn('MAX(fid)', sql)

    def test_unregister_limits_update_to_authenticated_user(self):
        db = MagicMock()
        push_repository.unregister_subscription(db, 456, 'endpoint')
        sql, params = db.execute.call_args.args
        self.assertIn('aktiv=false', sql)
        self.assertIn('WHERE fid_kontrolleur=%s AND endpoint=%s', sql)
        self.assertEqual(params, (456, 'endpoint'))

    def test_active_subscriptions_return_original_rows(self):
        db = MagicMock()
        rows = [{'endpoint': 'one', 'p256dh': 'p', 'auth': 'a', 'user_agent': ''}]
        db.execute.return_value.fetchall.return_value = rows
        self.assertIs(push_repository.active_subscriptions(db, 789), rows)
        sql, params = db.execute.call_args.args
        self.assertIn("COALESCE(user_agent,'') AS user_agent", sql)
        self.assertIn('aktiv=true', sql)
        self.assertEqual(params, (789,))

    def test_database_error_propagates_to_caller(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError('database unavailable')
        with self.assertRaises(RuntimeError):
            push_repository.unregister_subscription(db, 456, 'endpoint')


if __name__ == '__main__':
    unittest.main()
