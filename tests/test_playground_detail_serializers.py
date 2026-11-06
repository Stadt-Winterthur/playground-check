"""Behavioral contracts for pure playground detail transformations."""

import unittest

from playground_check.playground_detail_serializers import (
    criterion_dict, playdevice_feature, report_dict,
)
DOTNET_MIN_DATE = "0001-01-01T00:00:00"


class DetailSerializerTest(unittest.TestCase):
    def test_report_defaults_and_identity(self):
        row = {"tid": 5, "inspection_tid": 16, "inspection_done": 0,
               "maintenance_done": 1, "playdevice_fid": 47, "inspection_type": "HI"}
        actual = report_dict(row)
        self.assertEqual(actual["tid"], 5)
        self.assertEqual(actual["tidInspection"], 16)
        self.assertEqual(actual["playdeviceFid"], 47)
        self.assertEqual(actual["inspectionType"], "HI")
        self.assertIs(actual["inspectionDone"], False)
        self.assertIs(actual["maintenanceDone"], True)
        self.assertEqual(actual["inspectionText"], "")

    def test_criterion_defaults_and_separate_nested_instances(self):
        row = {"realm": "Safety", "check_text": "Schrauben", "inspection_type": "Visuell"}
        first, second = criterion_dict(row), criterion_dict(row)
        self.assertEqual(first["checkShortText"], "")
        self.assertEqual(first["check"], "Schrauben")
        self.assertEqual(first["currentInspectionReport"]["tid"], 0)
        first["currentInspectionReport"]["tid"] = 100
        self.assertEqual(second["currentInspectionReport"]["tid"], 0)

    def test_device_feature_preserves_fid_and_no_fid_creation(self):
        feature = playdevice_feature(
            {"fid": 123, "x": 0, "y": 5, "type_name": "Rutsche", "has_open_defects": True},
            general=[{"check": "A"}], main=[], secondary=[],
            last=[{"tid": 1}], previous=[], defects=None, min_date=DOTNET_MIN_DATE,
        )
        props = feature["properties"]
        self.assertEqual(feature["geometry"]["coordinates"], [0, 5])
        self.assertEqual(props["fid"], 123)
        self.assertNotIn("tid", props)
        self.assertEqual(props["dateOfService"], DOTNET_MIN_DATE)
        self.assertIsNone(props["defects"])
        self.assertTrue(props["hasOpenDefects"])
        self.assertEqual(props["generalInspectionCriteria"], [{"check": "A"}])

    def test_device_feature_preserves_optional_values_and_empty_defects(self):
        feature = playdevice_feature(
            {"fid": 8, "construction_date": "2024-01-02",
             "recommended_year": 2030, "not_to_be_checked": 1,
             "cannot_be_checked": 0, "x": None, "y": None},
            general=[], main=[], secondary=[], last=[], previous=[],
            defects=[], min_date=DOTNET_MIN_DATE,
        )
        props = feature["properties"]
        self.assertEqual(props["constructionDate"], "2024-01-02")
        self.assertEqual(props["recommendedYearOfRenovation"], 2030)
        self.assertTrue(props["notToBeChecked"])
        self.assertFalse(props["cannotBeChecked"])
        self.assertEqual(props["defects"], [])
        self.assertEqual(feature["geometry"]["coordinates"], [None, None])
