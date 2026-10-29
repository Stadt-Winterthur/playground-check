"""Method-aware DRF routing contracts without a Django dependency."""
import unittest
from playground_check.django_project.route_registry import migrated_path


class RouteRegistryTests(unittest.TestCase):
    def test_all_functional_groups(self):
        routes = [
            ("GET", "/api/health", "/api/health"),
            ("GET", "/Collections/Playgrounds/Items/", "/Collections/Playgrounds/Items/"),
            ("GET", "/Collections/Playgrounds/Items/AbC-987", "/Collections/Playgrounds/Items/AbC-987/"),
            ("GET", "/Playground/byplaydevice/123", "/Playground/byplaydevice/123/"),
            ("GET", "/playground/123", "/Playground/123/"),
            ("GET", "/Defect/", "/Defect/"),
            ("PUT", "/Defect/Picture/45", "/Defect/Picture/45/"),
            ("POST", "/defect/45/SEND-MAIL", "/Defect/45/send-mail/"),
            ("POST", "/Defect/45/accept", "/Defect/45/accept/"),
            ("POST", "/Defect/45/reject", "/Defect/45/reject/"),
            ("POST", "/Inspection/", "/Inspection/"),
            ("PUT", "/playdevice/", "/Playdevice/"),
            ("GET", "/playdevice/123/picture", "/Playdevice/123/Picture/"),
        ]
        for method, url, expected in routes:
            with self.subTest(method=method, url=url):
                self.assertEqual(migrated_path(url, method), expected)

    def test_non_migrated_methods_and_malformed_paths_keep_legacy(self):
        cases = [
            ("GET", "/Account/Login/"),
            ("POST", "/Playground/byname/"),
            ("POST", "/Collections/Playgrounds/Items/"),
            ("GET", "/Playground/invalid/"),
            ("GET", "/Defect/Picture/not-an-id/"),
            ("POST", "/Document/123/Name/"),
            ("GET", "/Document/"),
            ("POST", "/PushSubscription/Me/"),
            ("GET", "/defect/not-an-api-route"),
            ("GET", "/api/health/extra"),
            ("GET", "/Collections/Playgrounds/Items/abc/extra"),
        ]
        for method, url in cases:
            with self.subTest(method=method, url=url):
                self.assertIsNone(migrated_path(url, method))

    def test_canonical_paths_cover_all_declared_routes(self):
        from playground_check.django_project.route_registry import ROUTES
        for _, methods, canonical in ROUTES:
            sample = canonical.replace("{fid}", "123").replace("{tid}", "456").replace("{uuid}", "abc")
            for method in methods.split():
                with self.subTest(method=method, canonical=sample):
                    self.assertEqual(migrated_path(sample, method), sample)


if __name__ == "__main__":
    unittest.main()
