"""Regression tests for pure write rules; no DB or SMTP calls."""
import unittest
from datetime import datetime

from playground_check import defect_write_rules as rules


class DefectWriteRulesTest(unittest.TestCase):
    def test_priority_two_requires_both_responsibilities(self):
        self.assertFalse(rules.priority_two_fields_complete({"priority": 2}))
        self.assertFalse(rules.priority_two_fields_complete({"priority": 2, "defectsResponsibleBodyId": 3}))
        self.assertTrue(rules.priority_two_fields_complete({"priority": 2, "defectsResponsibleBodyId": 3, "responsibleUserFid": 12}))
        self.assertFalse(rules.priority_two_fields_complete({"priority": "invalid"}))

    def test_missing_responsibility_keeps_legacy_null_and_sentinel(self):
        self.assertEqual(rules.responsible_user_fid({}), -1)
        self.assertIsNone(rules.responsible_body_id({"defectsResponsibleBodyId": -1}))
        self.assertEqual(rules.responsible_body_id({"defectsResponsibleBodyId": "4"}), "4")

    def test_change_of_responsible_resets_status_and_comment(self):
        now = datetime(2026, 10, 26, 12, 0)
        actual = rules.update_assignment_fields(
            {"responsibleUserFid": 42, "assignmentStatus": "angenommen", "assignmentComment": "keep?"},
            41, now=now, parse_date=lambda value: value,
        )
        self.assertEqual(actual, (42, True, "zugewiesen", now, None))

    def test_unchanged_responsible_keeps_status_and_comment(self):
        existing = datetime(2026, 10, 1)
        actual = rules.update_assignment_fields(
            {"responsibleUserFid": 42, "assignmentStatus": "angenommen",
             "assignmentComment": "  geprüft  ", "dateAssignmentCreated": existing},
            42, now=datetime(2026, 10, 26), parse_date=lambda value: value,
        )
        self.assertEqual(actual, (42, False, "angenommen", existing, "geprüft"))

    def test_unassignment_returns_null_assignment_columns(self):
        actual = rules.update_assignment_fields(
            {}, 42, now=datetime(2026, 10, 26), parse_date=lambda value: value,
        )
        self.assertEqual(actual, (None, True, None, None, None))


if __name__ == "__main__":
    unittest.main()
