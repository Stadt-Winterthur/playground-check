"""Global GUI policy: proxy-safe rendered form failures, never API rewrites."""
import unittest
from types import SimpleNamespace

from django.http import HttpResponse, JsonResponse

from playground_check.django_project.gui_error_policy import BrowserFormErrorMiddleware


class BrowserFormErrorsTests(unittest.TestCase):
    def response(self, method, route, status, content_type='text/html'):
        request = SimpleNamespace(method=method, resolver_match=SimpleNamespace(url_name=route))
        response = HttpResponse('<main>Formularfehler</main>', status=status, content_type=content_type)
        return BrowserFormErrorMiddleware(lambda _: response)(request)

    def test_all_gui_form_errors_are_proxy_safe(self):
        for route in ('python-ui-defect-detail', 'python-ui-inspection', 'python-ui-login',
                      'python-ui-device-edit', 'python-ui-document-upload',
                      'python-ui-admin-users', 'python-ui-profile'):
            for status in (400, 409, 413, 422):
                with self.subTest(route=route, status=status):
                    result = self.response('POST', route, status)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result['X-UI-Original-Status'], str(status))
                    self.assertEqual(result['X-UI-Outcome'], 'error')
                    self.assertIn(b'Formularfehler', result.content)
                    self.assertIn('no-store', result['Cache-Control'])

    def test_api_denials_and_non_html_are_untouched(self):
        for method, route, status, content_type in (
            ('POST', 'defect', 409, 'text/html'),
            ('POST', 'python-ui-defect-detail', 403, 'text/html'),
            ('POST', 'python-ui-login', 401, 'text/html'),
            ('GET', 'python-ui-defect-detail', 404, 'text/html'),
            ('POST', 'python-ui-defect-detail', 409, 'application/json'),
        ):
            with self.subTest(method=method, route=route, status=status):
                result = self.response(method, route, status, content_type)
                self.assertEqual(result.status_code, status)
                self.assertFalse(result.has_header('X-UI-Original-Status'))

    def test_server_failures_stay_real_http_errors_for_monitoring(self):
        for status in (500, 502, 503):
            with self.subTest(status=status):
                result = self.response('POST', 'python-ui-defect-detail', status)
                self.assertEqual(result.status_code, status)
                self.assertFalse(result.has_header('X-UI-Original-Status'))
                self.assertEqual(result['X-UI-Outcome'], 'error')
                self.assertIn('no-store', result['Cache-Control'])


    def test_get_server_failure_keeps_http_status_and_error_outcome(self):
        result = self.response('GET', 'python-ui-defect-detail', 503)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result['X-UI-Outcome'], 'error')
        self.assertFalse(result.has_header('X-UI-Original-Status'))

    def test_success_and_authentication_are_not_mislabelled(self):
        for status in (200, 201, 302, 401, 403):
            with self.subTest(status=status):
                result = self.response('POST', 'python-ui-defect-detail', status)
                self.assertEqual(result.status_code, status)
                self.assertFalse(result.has_header('X-UI-Outcome'))

    def test_form_error_focus_is_shared_and_does_not_change_values(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / 'src/playground_check/static/js/form-safety.js').read_text()
        self.assertIn("focusFormError(document)", source)
        self.assertIn("htmx:afterSwap", source)
        self.assertIn("preventScroll: true", source)
        self.assertIn(".app-form-error", source)

    def test_redirects_are_untouched(self):
        self.assertEqual(self.response('POST', 'python-ui-defect-detail', 303).status_code, 303)
