"""Read-only composition contracts for the step-12 service extraction."""
import unittest
from unittest.mock import Mock

from playground_check import inspection_defect_service


class InspectionDefectServiceTests(unittest.TestCase):
    def test_history_preserves_legacy_grouping_and_order(self):
        rows = {
            "HI": [
                {"inspection_tid": 7, "tid": 11},
                {"inspection_tid": 7, "tid": 12},
                {"inspection_tid": 6, "tid": 13},
            ],
            "VI": [{"inspection_tid": 9, "tid": 14}],
        }
        loader = Mock(side_effect=lambda db, fid, kind: rows[kind])
        recent, previous = inspection_defect_service.inspection_history(
            object(), 123, ["HI", "VI"], load_reports=loader,
            serialize_report=lambda row: {"tid": row["tid"]},
        )
        self.assertEqual(recent, [{"tid": 13}])
        self.assertEqual(previous, [{"tid": 11}, {"tid": 12}, {"tid": 14}])
        self.assertEqual([call.args[1:] for call in loader.call_args_list],
                         [(123, "HI"), (123, "VI")])

    def test_history_handles_empty_results(self):
        self.assertEqual(
            inspection_defect_service.inspection_history(
                None, 1, ["HI"], load_reports=lambda *_: [], serialize_report=dict),
            ([], []),
        )

    def test_defect_payload_keeps_tid_fids_and_photo_groups(self):
        result = inspection_defect_service.defect_payload(
            {"tid": 901, "playdevice_fid": 333, "priority": 0,
             "done_by": None, "created_by_fid": 44},
            picture_rows=[{"tid": 20, "after_fixing": None},
                          {"tid": 21, "after_fixing": True}],
            done_by_name="", created_by_name="Tester",
            assignment_history=[{"id": 1}],
        )
        self.assertEqual(result["tid"], 901)
        self.assertEqual(result["playdeviceFid"], 333)
        self.assertEqual(result["priority"], 0)
        self.assertEqual(result["defectPicsTids"], [20])
        self.assertEqual(result["defectPicsAfterFixingTids"], [21])
        self.assertEqual(result["createdByName"], "Tester")
        self.assertEqual(result["assignmentHistory"], [{"id": 1}])
        self.assertFalse(result["done"])

    def test_defect_payload_defaults_are_backward_compatible(self):
        result = inspection_defect_service.defect_payload(
            {"tid": 1}, picture_rows=[], done_by_name="",
            created_by_name="", assignment_history=[],
        )
        self.assertEqual(result["priority"], -1)
        self.assertEqual(result["responsibleUserFid"], -1)
        self.assertEqual(result["defectDescription"], "")
        self.assertEqual(result["defectPicsTids"], [])
        self.assertEqual(result["errorMessage"], "")


if __name__ == "__main__":
    unittest.main()
