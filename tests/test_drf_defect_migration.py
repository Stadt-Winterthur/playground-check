"""Endpoint compatibility of the full defect DRF routing group."""
import os
import unittest
from unittest.mock import patch

from playground_check.http import Response as LegacyResponse

# Importing DRF views requires configured Django settings. The WSGI module
# initializes Django exactly as the existing DRF integration tests do.
os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    defect_views = None
else:
    from playground_check.django_project import wsgi  # noqa: F401
    from playground_check.django_project import defect_views


@unittest.skipIf(defect_views is None, "Django REST Framework is not installed")
class DRFDefectMigrationTests(unittest.TestCase):
    def test_all_write_methods_use_native_commands(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = defect_views.defect_commands
        for method, function in (("POST", "update_defect"), ("PUT", "create_defect")):
            with self.subTest(method=method), patch.object(native, function,
                    return_value=HttpResponse(b'{"errorMessage":""}', content_type="application/json")) as handler:
                req = getattr(RequestFactory(), method.lower())('/Defect/', data='{}', content_type='application/json')
                result = defect_views.defect(req)
                self.assertEqual(result.status_code, 200)
                handler.assert_called_once()

    def test_dynamic_id_and_error_response_bytes_are_preserved(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = defect_views.defect_commands
        with patch.object(native, 'send_info_mail', return_value=HttpResponse(
                'SMTP nicht erreichbar', status=502, content_type="text/plain")) as handler:
            result = defect_views.defect_send_mail(RequestFactory().post('/Defect/123/send-mail/'), tid=123)
            self.assertEqual(result.status_code, 502)
            self.assertEqual(result.content, 'SMTP nicht erreichbar'.encode())
            self.assertEqual(handler.call_args.args[1], 123)

    def test_picture_binary_response_and_permission_status_are_preserved(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        native = defect_views.defect_commands
        with patch.object(native, 'get_defect_picture', return_value=HttpResponse(b'GIF89a', content_type='image/gif')):
            result = defect_views.defect_picture(RequestFactory().get('/Defect/Picture/17/'), tid=17)
            self.assertEqual((result.status_code, result.content, result['Content-Type']), (200, b'GIF89a', 'image/gif'))
        with patch.object(defect_views.defect_native.service, 'require_user',
                          return_value=(None, LegacyResponse.text('Unauthorized', 401))):
            result = defect_views.defect_overview(RequestFactory().get('/Defect/Overview/'))
            self.assertEqual((result.status_code, result.content), (401, b'Unauthorized'))

    def test_native_parser_receives_case_insensitive_json(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        from playground_check.django_project.api_wire import to_legacy_request
        body = '{"DefectDescription":"Test"}'
        def handler(request):
            self.assertEqual(to_legacy_request(request).json().get('defectDescription'), 'Test')
            return HttpResponse(b'{"tid":9}', content_type='application/json')
        with patch.object(defect_views.defect_commands, 'create_defect', side_effect=handler):
            defect_views.defect(RequestFactory().put('/Defect/', data=body, content_type='application/json'))

    def test_native_defect_read_and_assignment_skip_legacy_handlers(self):
        from django.test import RequestFactory
        from unittest.mock import MagicMock
        native = defect_views.defect_native
        connection = MagicMock()
        connection.__enter__.return_value = "db"
        identity = {"fid": 12, "mailAddress": "worker@example.org"}
        with patch.object(native.service, "require_user", return_value=(identity, None)), \
             patch.object(native.service, "connect", return_value=connection), \
             patch.object(native.service.inspection_defect_repository, "defect_by_tid", return_value=None) as lookup, \
             patch.object(native.service, "get_defect", side_effect=AssertionError("legacy read")):
            response = defect_views.defect(RequestFactory().get("/Defect/?tid=77"))
        self.assertEqual((response.status_code, response.content), (200, b"null"))
        lookup.assert_called_once_with("db", 77)

        with patch.object(native.service, "require_user", return_value=(identity, None)), \
             patch.object(native.service, "connect", return_value=connection), \
             patch.object(native.service.assignment_repository, "update_assignment_status", return_value=1) as update, \
             patch.object(native.service, "assignment_status", side_effect=AssertionError("legacy assignment")):
            response = defect_views.defect_accept(RequestFactory().post(
                "/Defect/99/accept/", data='{"AssignmentComment":" OK "}', content_type="application/json"), tid=99)
        self.assertEqual((response.status_code, response.content), (200, b'{"errorMessage":""}'))
        update.assert_called_once_with("db", 99, 12, "worker@example.org", "OK", True)

    def test_native_defect_rejects_unauthorized_before_database(self):
        from django.test import RequestFactory
        native = defect_views.defect_native
        with patch.object(native.service, "require_user", return_value=(None, LegacyResponse.text("Unauthorized", 401))), \
             patch.object(native.service, "connect", side_effect=AssertionError("DB must not be accessed")):
            response = defect_views.defect_reject(RequestFactory().post("/Defect/99/reject/"), tid=99)
        self.assertEqual((response.status_code, response.content), (401, b"Unauthorized"))
