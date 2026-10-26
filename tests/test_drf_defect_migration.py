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
    def test_all_methods_reach_the_existing_business_handlers(self):
        for method, function in (("GET", "get_defect"), ("POST", "update_defect"), ("PUT", "create_defect")):
            with self.subTest(method=method), patch.object(defect_views.service, function, return_value=LegacyResponse.json({"errorMessage": ""})) as handler:
                from django.test import RequestFactory
                factory = RequestFactory()
                req = (
                    factory.get('/Defect/')
                    if method == 'GET'
                    else getattr(factory, method.lower())('/Defect/', data='{}', content_type='application/json')
                )
                result = defect_views.defect(req)
                self.assertEqual(result.status_code, 200)
                handler.assert_called_once()

    def test_dynamic_id_and_error_response_bytes_are_preserved(self):
        from django.test import RequestFactory
        with patch.object(defect_views.service, 'send_info_mail', return_value=LegacyResponse.text('SMTP nicht erreichbar', 502)) as handler:
            result = defect_views.defect_send_mail(RequestFactory().post('/Defect/123/send-mail/'), tid=123)
            self.assertEqual(result.status_code, 502)
            self.assertEqual(result.content, 'SMTP nicht erreichbar'.encode())
            self.assertEqual(handler.call_args.args[0].params['tid'], '123')

    def test_picture_binary_response_and_permission_status_are_preserved(self):
        from django.test import RequestFactory
        with patch.object(defect_views.service, 'get_defect_picture', return_value=LegacyResponse.file(b'GIF89a', 'image/gif')):
            result = defect_views.defect_picture(RequestFactory().get('/Defect/Picture/17/'), tid=17)
            self.assertEqual((result.status_code, result.content, result['Content-Type']), (200, b'GIF89a', 'image/gif'))
        with patch.object(defect_views.service, 'get_defect_overview', return_value=LegacyResponse.text('Unauthorized', 401)):
            result = defect_views.defect_overview(RequestFactory().get('/Defect/Overview/'))
            self.assertEqual((result.status_code, result.content), (401, b'Unauthorized'))

    def test_legacy_parser_receives_case_insensitive_json(self):
        from django.test import RequestFactory
        body = '{"DefectDescription":"Test"}'
        with patch.object(defect_views.service, 'create_defect', return_value=LegacyResponse.json({'tid': 9})) as handler:
            defect_views.defect(RequestFactory().put('/Defect/', data=body, content_type='application/json'))
            self.assertEqual(handler.call_args.args[0].json().get('defectDescription'), 'Test')
