"""Regression tests for the consolidated read-only repository."""
import sys
import types
import unittest
from unittest.mock import Mock

if "psycopg" not in sys.modules:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        sys.modules["psycopg"] = types.SimpleNamespace(Connection=object)

from playground_check import remaining_reads_repository as reads


class RemainingReadsRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.execute.return_value.fetchall.return_value = []
        self.db.execute.return_value.fetchone.return_value = None

    def test_name_filter_keeps_bound_parameters(self):
        reads.playground_name_rows(self.db, {"mailAddress": "test@win.ch"}, "Hauptinspektion (HI)")
        sql, params = self.db.execute.call_args.args
        self.assertIn("wgr_sp_inspart_kontr", sql)
        self.assertEqual(params, ("test@win.ch", "Hauptinspektion"))

    def test_public_uuid_uses_parameter_not_sql_concatenation(self):
        reads.public_playground_by_uuid(self.db, "abc' OR 1=1")
        sql, params = self.db.execute.call_args.args
        self.assertIn("uuid::text=%s", sql)
        self.assertEqual(params, ("abc' OR 1=1",))

    def test_defect_overview_is_read_only_and_preserves_ordering(self):
        reads.defect_overview_rows(self.db)
        sql = self.db.execute.call_args.args[0]
        self.assertIn("assignment_overdue", sql)
        self.assertIn("ORDER BY", sql)
        self.assertNotIn("UPDATE ", sql)

    def test_document_relation_is_whitelisted(self):
        with self.assertRaises(ValueError):
            reads.document_blob(self.db, "other", "blob", 5)
        self.db.execute.assert_not_called()
        reads.document_blob(self.db, "wgr_sp_zertifikat", "zertifikatsdokument", 5)
        self.assertEqual(self.db.execute.call_args.args[1], (5,))

    def test_picture_thumbnail_uses_fixed_column(self):
        reads.defect_picture(self.db, 99, True)
        sql, params = self.db.execute.call_args.args
        self.assertIn("picture_base64_thumb", sql)
        self.assertEqual(params, (99,))

    def test_fid_tid_lookup_uses_given_id(self):
        reads.playground_by_fid(self.db, 301)
        self.assertEqual(self.db.execute.call_args.args[1], (301,))
        reads.defect_picture_rows(self.db, 810)
        self.assertEqual(self.db.execute.call_args.args[1], (810,))

    def test_list_and_options_use_original_tables(self):
        reads.public_playground_rows(self.db)
        self.assertIn('"wgr_sp_spielplatz"', self.db.execute.call_args.args[0])
        reads.inspection_type_rows(self.db)
        self.assertIn('"wgr_sp_inspektionsart_tbd"', self.db.execute.call_args.args[0])
        reads.renovation_type_rows(self.db)
        self.assertIn('"wgr_sp_sanierungsart_tbd"', self.db.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
