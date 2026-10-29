"""Security boundary and native inspection form regression tests."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
    from django.test import RequestFactory
except ImportError:
    django = None

@unittest.skipUnless(django is not None, "Django not installed")
class InspectionEditorTests(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()
        self.kind = "Visuelle Inspektion (VI)"
        self.user = {"fid": 17, "role": "inspector", "mailAddress": "test@example.ch"}
        self.payload = {"inspectionTypeOptions": [self.kind], "playdevices": [{"fid": 42, "name": "Schaukel"}], "inspectionSuspended": False}

    def test_anonymous_cannot_access_form_or_post(self):
        for method in ("get", "post"):
            with self.subTest(method=method), patch.object(self.ui, "require_user", return_value=(None, object())), patch.object(self.ui, "playground_by_name_data") as fetch:
                request = getattr(self.rf, method)("/__ui/inspection/?name=A&inspectiontype=B")
                if method == "post":
                    # csrf_protect itself rejects POST without a token before reaching auth
                    self.assertEqual(self.ui.inspection_editor(request).status_code, 403)
                else:
                    self.assertEqual(self.ui.inspection_editor(request).status_code, 401)
                fetch.assert_not_called()

    def test_get_renders_csrf_and_preserves_proxy_prefix(self):
        with patch.object(self.ui, "require_user", return_value=(self.user, None)), patch.object(self.ui, "playground_only_names_data", return_value=[{"name": "A"}]), patch.object(self.ui, "playground_by_name_data", return_value=self.payload):
            result = self.ui.inspection_editor(self.rf.get("/__ui/inspection/", {"name": "A", "inspectiontype": self.kind}, SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'csrfmiddlewaretoken', result.content)
        self.assertIn(b'/stadtgruen/spielplatzkontrolle/__ui/inspection/', result.content)

    def test_disallowed_role_cannot_query_or_write(self):
        with patch.object(self.ui, "require_user", return_value=({**self.user, "role": "maintenance"}, None)), patch.object(self.ui, "playground_by_name_data") as query:
            result = self.ui.inspection_editor(self.rf.get("/__ui/inspection/", {"name": "A", "inspectiontype": self.kind}))
        self.assertEqual(result.status_code, 403)
        query.assert_not_called()

    def test_post_uses_native_command_and_not_client_device_ids(self):
        import json
        from urllib.parse import urlencode
        from django.http import HttpResponse
        from django.middleware.csrf import get_token
        csrf_request = self.rf.get('/__ui/inspection/')
        token = get_token(csrf_request)
        form = {'name': 'A', 'inspectiontype': self.kind, 'checked_42': 'on',
                'comment_42': 'Geprüft', 'checked_999': 'on', 'confirm': 'yes',
                'csrfmiddlewaretoken': token}
        # Plain HTML forms use URL-encoded data; RequestFactory defaults to multipart.
        request = self.rf.post('/__ui/inspection/', urlencode(form),
                               content_type='application/x-www-form-urlencoded', HTTP_X_CSRFTOKEN=token,
                               HTTP_COOKIE=f'csrftoken={csrf_request.META["CSRF_COOKIE"]}')
        request.META['CSRF_COOKIE'] = csrf_request.META['CSRF_COOKIE']
        with patch.dict(os.environ, {'PLAYGROUND_UI_INSPECTION_WRITE_ENABLED': 'true'}), \
             patch.object(self.ui, 'require_user', return_value=(self.user, None)), \
             patch.object(self.ui, 'playground_only_names_data', return_value=[{'name': 'A'}]), \
             patch.object(self.ui, 'playground_by_name_data', return_value=self.payload), \
             patch('playground_check.django_project.inspection_device_commands.create_inspection',
                   return_value=HttpResponse('{"errorMessage":""}', content_type='application/json')) as save:
            result = self.ui.inspection_editor(request)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(save.call_count, 1)
        report = json.loads(save.call_args.args[0].body)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]['playdeviceFid'], 42)
        self.assertEqual(report[0]['inspectionComment'], 'Geprüft')
