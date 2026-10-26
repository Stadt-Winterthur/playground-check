"""Regression coverage for the larger step 26 repository extraction."""
import unittest
from unittest.mock import Mock

from playground_check import mail_repository, inspection_validation_repository


class RepositoryExtractionTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.execute.return_value.fetchone.return_value = {"fid": 17}
        self.db.execute.return_value.fetchall.return_value = [{"tid": 42}]

    def test_mail_queries_are_parameterized(self):
        mail_repository.defect(self.db, 71)
        self.assertEqual(self.db.execute.call_args.args[1], (71,))
        mail_repository.recipient(self.db, 19)
        self.assertEqual(self.db.execute.call_args.args[1], (19,))
        mail_repository.device(self.db, 202)
        self.assertEqual(self.db.execute.call_args.args[1], (202,))
        mail_repository.pictures(self.db, 71)
        self.assertEqual(self.db.execute.call_args.args[1], (71,))

    def test_mail_status_update_is_separate_and_guarded(self):
        mail_repository.mark_sent(self.db, 71, "Name", 19)
        sql, params = self.db.execute.call_args.args
        self.assertIn('infomail_gesendet_am', sql)
        self.assertIn('fid_zustaendig_kontrolleur=%s', sql)
        self.assertEqual(params, ('Name', 71, 19))

    def test_inspection_authorization_keeps_three_identifiers(self):
        inspection_validation_repository.is_authorized(self.db, 17, 203, 3)
        sql, params = self.db.execute.call_args.args
        self.assertIn('wgr_sp_inspart_kontr', sql)
        self.assertEqual(params, (17, 203, 3))

    def test_inspection_duplicate_check_uses_date_and_type(self):
        inspection_validation_repository.duplicate_inspection(self.db, 203, 3, '2026-10-26')
        sql, params = self.db.execute.call_args.args
        self.assertIn('datum_inspektion::date=%s', sql)
        self.assertEqual(params, (203, 3, '2026-10-26'))

    def test_inspection_target_column_is_allowlisted(self):
        with self.assertRaises(ValueError):
            inspection_validation_repository.target_date_row(self.db, 203, 'fid; DROP TABLE x')
        self.db.execute.assert_not_called()
        inspection_validation_repository.target_date_row(self.db, 203, 'dat_naech_haupt_insp')
        self.assertEqual(self.db.execute.call_args.args[1], (203,))

    def test_device_lookup_uses_existing_fid(self):
        inspection_validation_repository.device_playground(self.db, 123)
        self.assertEqual(self.db.execute.call_args.args[1], (123,))
        inspection_validation_repository.device_check_state(self.db, 123)
        self.assertEqual(self.db.execute.call_args.args[1], (123,))


if __name__ == '__main__':
    unittest.main()
