"""Pinned local HTMX installation does not accept tampered scripts."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/fetch_htmx_verified.py"
spec = importlib.util.spec_from_file_location("fetch_htmx_verified", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LocalHtmxTests(unittest.TestCase):
    def test_fixed_version_and_sri(self):
        self.assertEqual(module.VERSION, "2.0.11")
        self.assertTrue(module.EXPECTED_SRI.startswith("sha384-"))
        self.assertEqual(module.DESTINATION.name, "htmx.min.js")

    def test_modified_bundle_rejected(self):
        with self.assertRaises(ValueError):
            module.verify(b"fake htmx library" * 1000)

    def test_installer_does_not_write_before_verification(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(source.index("verify(content)"), source.index("DESTINATION.parent.mkdir"))


if __name__ == "__main__":
    unittest.main()
