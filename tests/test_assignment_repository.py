"""No-database contract tests for defect assignment SQL."""
import unittest
from unittest.mock import MagicMock, patch
from playground_check import assignment_repository, service


class AssignmentRepositoryTest(unittest.TestCase):
    def test_accept_is_authorized_in_sql_using_fid_or_email(self):
        db = MagicMock()
        db.execute.return_value.rowcount = 1
        result = assignment_repository.update_assignment_status(db, 912, 44, 'user@example.org', 'ok', True)
        sql, params = db.execute.call_args.args
        self.assertEqual(result, 1)
        self.assertIn("auftrag_status='angenommen'", sql)
        self.assertIn('mangel.fid_zustaendig_kontrolleur=%s OR EXISTS', sql)
        self.assertIn('trim(lower(kontrolleur.e_mail))=%s', sql)
        self.assertEqual(params, ('ok', 912, 44, 'user@example.org'))

    def test_decline_resets_accepted_timestamp_and_reports_missing_row(self):
        db = MagicMock()
        db.execute.return_value.rowcount = 0
        self.assertEqual(assignment_repository.update_assignment_status(db, 1, 2, 'x@y.ch', None, False), 0)
        sql, params = db.execute.call_args.args
        self.assertIn("auftrag_status='abgelehnt'", sql)
        self.assertIn('datum_auftrag_angenommen=NULL', sql)
        self.assertEqual(params, (None, 1, 2, 'x@y.ch'))

    def test_history_query_filters_by_tid_and_keeps_sorting(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [{'id': 4}]
        self.assertEqual(assignment_repository.assignment_history_rows(db, 56), [{'id': 4}])
        sql, params = db.execute.call_args.args
        self.assertIn('WHERE tid_mangel=%s ORDER BY geaendert_am DESC, id DESC', sql)
        self.assertEqual(params, (56,))

    def test_history_insert_uses_existing_fids(self):
        db = MagicMock()
        assignment_repository.record_assignment_change(db, 90, 3, 'Tester', 1, 'Alt', 2, 'Neu')
        sql, params = db.execute.call_args.args
        self.assertIn('INSERT INTO "wgr_sp_mangel_zuweisung_hist"', sql)
        self.assertEqual(params, (90, 3, 'Tester', 1, 'Alt', 2, 'Neu'))
        self.assertNotIn('MAX(fid)', sql)

    def test_unchanged_assignment_does_not_write_history(self):
        db = MagicMock()
        service._record_assignment_change(db, 90, {'fid': 3}, 5, 5)
        db.execute.assert_not_called()

    def test_service_endpoint_preserves_error_contract(self):
        request = MagicMock()
        request.params = {'tid': '90'}
        request.json.return_value = {'assignmentComment': ' Hallo '}
        with patch.object(service, 'require_user', return_value=({'fid': 3, 'mailAddress': 'u@x.ch'}, None)), \
             patch.object(service, 'connect') as connect, \
             patch.object(service.assignment_repository, 'update_assignment_status', return_value=0) as update:
            response = service.assignment_status(request, True)
        update.assert_called_once_with(connect.return_value.__enter__.return_value, 90, 3, 'u@x.ch', 'Hallo', True)
        self.assertIn('SPK-3', response.body.decode())


if __name__ == '__main__':
    unittest.main()
