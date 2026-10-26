"""Pure playground-read transformations must remain stable across HTTP frameworks."""

import unittest
from datetime import date, timedelta

from playground_check.playground_reads import inspection_suspended, public_feature


class PlaygroundReadTransformTest(unittest.TestCase):
    def test_geojson_keeps_public_contract_and_legacy_alias(self):
        row = {"uuid": "123", "number": 0, "name": "A&B", "street_name": "Hauptstr.",
               "house_no": "2", "x": 0, "y": 42}
        expected = {
            "type": "Feature",
            "properties": {"uuid": "123", "nummer": 0, "name": "A&B",
                           "streetName": "Hauptstr.", "houseNo": "2"},
            "geometry": {"type": "Point", "coordinates": [0, 42]},
            "errorMessage": "",
        }
        self.assertEqual(public_feature(row), expected)

    def test_geojson_empty_and_error_cases(self):
        self.assertEqual(public_feature()["geometry"]["coordinates"], [])
        self.assertEqual(public_feature()["properties"]["nummer"], -1)
        self.assertEqual(public_feature({"uuid": "missing"}, "No playground found.")["errorMessage"],
                         "No playground found.")

    def test_suspension_date_windows_and_legacy_alias(self):
        today = date.today()
        cases = [
            ({}, False),
            ({"suspend_from": today - timedelta(days=1)}, True),
            ({"suspend_to": today + timedelta(days=1)}, True),
            ({"suspend_from": today + timedelta(days=2)}, False),
            ({"suspend_from": today - timedelta(days=2),
              "suspend_to": today - timedelta(days=1)}, False),
            ({"suspend_from": today.isoformat(), "suspend_to": today.isoformat()}, True),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(inspection_suspended(row), expected)
