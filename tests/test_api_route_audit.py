"""Ensure newly introduced legacy API operations cannot silently bypass DRF."""
from pathlib import Path
import importlib.util
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/check_api_routes.py'
spec = importlib.util.spec_from_file_location('check_api_routes', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ApiRouteAuditTests(unittest.TestCase):
    def test_every_legacy_api_method_has_drf_dispatch(self):
        self.assertEqual(module.audit(), [])

    def test_registry_preserves_negative_method_matching(self):
        from playground_check.django_project.route_registry import migrated_path
        self.assertIsNone(migrated_path('/Playground/mapimage', 'POST'))
        self.assertIsNone(migrated_path('/Playground/nope', 'POST'))
        self.assertIsNone(migrated_path('/Document/', 'GET'))
        self.assertIsNone(migrated_path('/swagger/index.html', 'GET'))
        self.assertIsNone(migrated_path('/static/sw.js', 'GET'))
        self.assertEqual(migrated_path('/Playground/abc', 'GET'), '/Playground/abc/')


if __name__ == '__main__':
    unittest.main()
