"""Dependency audit should reliably detect legacy imports without DB access."""
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.check_migration_dependencies import scan


class MigrationDependencyAuditTests(unittest.TestCase):
    def test_existing_adapter_consumers_are_reported(self):
        found = scan()
        self.assertTrue(any(dependency == 'legacy_adapter' for _, _, dependency in found))

    def test_results_are_sorted_and_have_real_files(self):
        found = scan()
        self.assertEqual(found, sorted(set(found)))
        for filename, lineno, _ in found:
            self.assertTrue((Path(__file__).resolve().parents[1] / 'src/playground_check/django_project' / filename).is_file())
            self.assertGreater(lineno, 0)
