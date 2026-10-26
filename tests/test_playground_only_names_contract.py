"""Ensure the framework-independent names query returns data, not an HTTP response."""
import json
import unittest
from unittest.mock import patch

from playground_check import service
from playground_check.http import Response


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


class PlaygroundOnlyNamesContractTest(unittest.TestCase):
    def test_data_function_returns_plain_list(self):
        db = FakeDB([{
            'name': 'Testspielplatz', 'date_of_last_inspection': None,
            'suspend_from': None, 'suspend_to': None, 'has_open': True,
        }])
        with patch.object(service, 'connect', return_value=db):
            result = service.playground_only_names_data(None, {})
        self.assertIsInstance(result, list)
        self.assertNotIsInstance(result, Response)
        self.assertEqual(result[0]['name'], 'Testspielplatz')
        self.assertTrue(result[0]['hasOpenDeviceDefects'])
        self.assertEqual(result[0]['dateOfLastInspection'], service.DOTNET_MIN_DATE)

    def test_empty_result_is_empty_list(self):
        with patch.object(service, 'connect', return_value=FakeDB([])):
            self.assertEqual(service.playground_only_names_data(None, {}), [])

    def test_filtered_query_keeps_bound_parameters(self):
        db = FakeDB([])
        with patch.object(service, 'connect', return_value=db):
            service.playground_only_names_data(
                {'mailAddress': 'user@example.org'}, {'inspectiontype': 'Visuelle Inspektion (VI)'}
            )
        self.assertEqual(db.calls[0][1], ('user@example.org', 'Visuelle Inspektion'))

    def test_legacy_handler_wraps_data_once(self):
        expected = [{'name': 'Testspielplatz'}]
        with patch.object(service, 'require_user', return_value=({'fid': 5}, None)), \
             patch.object(service, 'playground_only_names_data', return_value=expected):
            response = service.only_names(type('RequestStub', (), {'query': {}})())
        self.assertIsInstance(response, Response)
        self.assertEqual(json.loads(response.body), expected)


if __name__ == '__main__':
    unittest.main()
