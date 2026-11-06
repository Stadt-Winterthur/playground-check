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
        self.payload = {"inspectionTypeOptions": [self.kind], "playdevices": [{"fid": 42, "name": "Schaukel", "properties": {"generalInspectionCriteria": [{"check": "Sichtkontrolle", "maintenance": "Schrauben pruefen"}]}}], "inspectionSuspended": False}

    def test_anonymous_cannot_access_form_or_post(self):
        for method in ("get", "post"):
            with self.subTest(method=method), patch.object(self.ui, "require_user", return_value=(None, object())), patch.object(self.ui, "playground_by_name_data") as fetch:
                request = getattr(self.rf, method)("/inspection/?name=A&inspectiontype=B")
                if method == "post":
                    self.assertEqual(self.ui.inspection_editor(request).status_code, 401)
                else:
                    self.assertEqual(self.ui.inspection_editor(request).status_code, 401)
                fetch.assert_not_called()

    def test_get_without_csrf_token_preserves_proxy_prefix(self):
        with patch.object(self.ui, "require_user", return_value=(self.user, None)), patch.object(self.ui, "playground_only_names_data", return_value=[{"name": "A"}]), patch.object(self.ui, "playground_by_name_data", return_value=self.payload):
            result = self.ui.inspection_editor(self.rf.get("/inspection/", {"name": "A", "inspectiontype": self.kind}, SCRIPT_NAME="/stadtgruen/spielplatzkontrolle"))
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(b'csrfmiddlewaretoken', result.content)
        self.assertIn(b'/stadtgruen/spielplatzkontrolle/inspection/', result.content)
        self.assertIn(b'<details class="inspection-criterion">', result.content)
        self.assertNotIn(b'<details class="inspection-criterion" open>', result.content)
        self.assertNotIn('Zur Spielgeräteübersicht'.encode(), result.content)
        self.assertNotIn(b'FID ', result.content)

    def test_disallowed_role_cannot_query_or_write(self):
        with patch.object(self.ui, "require_user", return_value=({**self.user, "role": "maintenance"}, None)), patch.object(self.ui, "playground_by_name_data") as query:
            result = self.ui.inspection_editor(self.rf.get("/inspection/", {"name": "A", "inspectiontype": self.kind}))
        self.assertEqual(result.status_code, 403)
        query.assert_not_called()

    def test_device_page_is_separate_from_overview(self):
        from html.parser import HTMLParser
        class Panels(HTMLParser):
            def __init__(self, html):
                super().__init__(); self.visible = []; self.feed(html)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'data-inspection-device' in attrs and 'hidden' not in attrs:
                    self.visible.append(attrs['data-inspection-device'])
        for selected in ('', '42', '999'):
            with self.subTest(selected=selected), patch.object(self.ui, 'require_user', return_value=(self.user, None)), \
                 patch.object(self.ui, 'playground_only_names_data', return_value=[{'name': 'A'}]), \
                 patch.object(self.ui, 'playground_by_name_data', return_value=self.payload):
                result = self.ui.inspection_editor(self.rf.get('/inspection/', {
                    'name': 'A', 'inspectiontype': self.kind, 'selected_device': selected}))
                self.assertEqual(result.status_code, 404 if selected == '999' else 200)
                if selected == '999':
                    continue
                html = result.content.decode()
                self.assertEqual(Panels(html).visible, [selected] if selected else [])
                self.assertEqual('id="inspection-overview"' in html, not bool(selected))
                self.assertEqual('id="inspection-submit"' in html, not bool(selected))
                self.assertEqual('data-inspection-back' in html, bool(selected))
                if not selected:
                    self.assertIn('&amp;selected_device=42"', html)

    def test_navigation_preserves_inputs_and_never_saves_report(self):
        from urllib.parse import urlencode
        from html.parser import HTMLParser
        class Fields(HTMLParser):
            def __init__(self, html):
                super().__init__(); self.checked = []; self.feed(html)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'input' and 'checked' in attrs:
                    self.checked.append(attrs.get('name'))
        for selected in ('42', ''):
            request = self.rf.post('/inspection/', urlencode({
                'name': 'A', 'inspectiontype': self.kind, 'navigation_device': selected,
                'comment_42_0': 'Geprüft & dokumentiert', 'maintenance_comment_42_0': 'Nachgezogen',
                'inspection_done_42_0': 'on', 'maintenance_done_42_0': 'on',
            }), content_type='application/x-www-form-urlencoded')
            request._dont_enforce_csrf_checks = True
            with self.subTest(selected=selected), patch.dict(os.environ, {'PLAYGROUND_UI_INSPECTION_WRITE_ENABLED': 'true'}), \
                 patch.object(self.ui, 'require_user', return_value=(self.user, None)), \
                 patch.object(self.ui, 'playground_only_names_data', return_value=[{'name': 'A'}]), \
                 patch.object(self.ui, 'playground_by_name_data', return_value=self.payload), \
                 patch('playground_check.django_project.inspection_device_commands.create_inspection') as save:
                result = self.ui.inspection_editor(request)
                self.assertEqual(result.status_code, 200)
                html = result.content.decode()
                self.assertIn('Geprüft &amp; dokumentiert', html)
                self.assertIn('Nachgezogen', html)
                self.assertEqual(Fields(html).checked, ['inspection_done_42_0', 'maintenance_done_42_0'])
                save.assert_not_called()

    def _checkability_post(self, checked, reason, *, excluded=False, rowcount=1):
        from copy import deepcopy
        from urllib.parse import urlencode
        from unittest.mock import MagicMock
        payload = deepcopy(self.payload)
        payload['playdevices'][0]['properties']['notToBeChecked'] = excluded
        form = {'name': 'A', 'inspectiontype': self.kind, 'save_checkability': '42',
                'cannotBeCheckedReason_42': reason, 'comment_42_0': 'Entwurf erhalten',
                'inspection_done_42_0': 'on'}
        if checked:
            form['cannotBeChecked_42'] = '1'
        request = self.rf.post('/inspection/', urlencode(form), content_type='application/x-www-form-urlencoded')
        request._dont_enforce_csrf_checks = True
        db = MagicMock()
        db.__enter__.return_value = db
        db.execute.return_value.rowcount = rowcount
        db.execute.return_value.fetchone.return_value = {'not_to_be_checked': excluded}
        with patch.object(self.ui, 'require_user', return_value=(self.user, None)), \
             patch.object(self.ui, 'playground_only_names_data', return_value=[{'name': 'A'}]), \
             patch.object(self.ui, 'playground_by_name_data', return_value=payload), \
             patch.object(self.ui, 'connect', return_value=db), \
             patch('playground_check.django_project.inspection_device_commands.create_inspection') as report:
            result = self.ui.inspection_editor(request)
            report.assert_not_called()
        return result, db

    def test_cannot_be_checked_is_saved_with_reason_and_draft_preserved(self):
        result, db = self._checkability_post(True, '  Baustelle  ')
        self.assertEqual(result.status_code, 200)
        sql, params = db.execute.call_args.args
        self.assertEqual(params, (True, 'Baustelle', 42))
        self.assertIn('COALESCE(nicht_zu_pruefen, false)=false', sql)
        self.assertNotIn('empfohlenes_sanierungsjahr', sql)
        html = result.content.decode()
        self.assertIn('Prüfbarkeit gespeichert.', html)
        self.assertIn('Entwurf erhalten', html)
        self.assertIn('data-server-values="true"', html)
        self.assertIn('data-cannot-check="true"', html)
        self.assertIn('<div hidden data-inspection-criteria>', html)
        self.assertIn('data-inspection-history="last"', html)
        self.assertIn('data-inspection-history="previous"', html)

    def test_cannot_be_checked_can_be_cleared(self):
        result, db = self._checkability_post(False, 'Bisheriger Grund')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(db.execute.call_args.args[1], (False, '', 42))
        self.assertIn(b'data-cannot-check="false"', result.content)

    def test_reason_required_and_limited_on_server(self):
        for reason in ('', '   ', 'x' * 256):
            with self.subTest(reason_length=len(reason)):
                result, db = self._checkability_post(True, reason)
                self.assertEqual(result.status_code, 400)
                self.assertFalse(any(call.args[0].lstrip().startswith('UPDATE') for call in db.execute.call_args_list))
                self.assertIn('Entwurf erhalten', result.content.decode())

    def test_not_to_be_checked_is_read_only(self):
        result, db = self._checkability_post(True, 'Baustelle', excluded=True)
        self.assertEqual(result.status_code, 403)
        db.execute.assert_not_called()

    def test_concurrent_exemption_does_not_report_success(self):
        result, db = self._checkability_post(True, 'Baustelle', rowcount=0)
        self.assertEqual(result.status_code, 409)
        self.assertNotIn('Prüfbarkeit gespeichert.', result.content.decode())

    def test_final_report_omits_exempt_and_uncheckable_devices(self):
        from playground_check.inspection_submission import validate_reports
        devices = [{'fid': 42}, {'fid': 43, 'not_to_be_checked': True},
                   {'fid': 44, 'cannot_be_checked': True, 'cannot_be_checked_reason': 'Baustelle'}]
        criteria = {'wgr_v_sp_ger_insp_krit': {
            fid: [{'check_text': 'Prüfen', 'maintenance': 'Warten'}] for fid in (42, 43, 44)}}
        report = {'playdeviceFid': 42, 'inspectionText': 'Prüfen', 'maintenanceText': 'Warten',
                  'inspectionDone': True, 'maintenanceDone': True}
        with patch('playground_check.playground_repository.playdevice_rows', return_value=devices), \
             patch('playground_check.device_detail_batch.criteria_for_devices', return_value=criteria):
            result = validate_reports(None, {'id': 1}, self.kind, [report])
            self.assertEqual([r['playdeviceFid'] for r in result], [42])
            devices[2]['cannot_be_checked_reason'] = '   '
            with self.assertRaisesRegex(ValueError, 'Begründung'):
                validate_reports(None, {'id': 1}, self.kind, [report])

    def test_post_uses_native_command_and_not_client_device_ids(self):
        import json
        from urllib.parse import urlencode
        from django.http import HttpResponse
        from django.middleware.csrf import get_token
        csrf_request = self.rf.get('/inspection/')
        token = get_token(csrf_request)
        form = {'name': 'A', 'inspectiontype': self.kind, 'inspection_done_42_0': 'on', 'maintenance_done_42_0': 'on',
                'comment_42_0': 'Geprüft', 'checked_999': 'on',
                'csrfmiddlewaretoken': token}
        # Plain HTML forms use URL-encoded data; RequestFactory defaults to multipart.
        request = self.rf.post('/inspection/', urlencode(form),
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
