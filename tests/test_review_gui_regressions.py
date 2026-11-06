"""Review GUI workflows: validate context, preserve input and delete auth cookie."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock
os.environ.setdefault('PLAYGROUND_SECURITY_KEY','test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','playground_check.django_project.settings')
import django
django.setup()
from django.test import RequestFactory
from django.http import HttpResponse
from playground_check.django_project import python_ui as ui, python_ui_workflows as wf
from playground_check import domain_support, user_repository

USER={'fid':17,'role':'administrator','mailAddress':'anna@example.org','firstName':'Anna','lastName':'Muster'}
DEVICE={'name':'Musterpark','playdevices':[{'properties':{'fid':42,'type':{'name':'Schaukel'}}}]}

class GuiReviewTests(unittest.TestCase):
    def setUp(self):self.rf=RequestFactory()
    def context(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(ui,'require_user',return_value=(USER,None)))
        stack.enter_context(patch.object(domain_support,'playground_by_device_data',return_value=DEVICE))
        db=MagicMock();db.__enter__.return_value=db
        stack.enter_context(patch('playground_check.db.connect',return_value=db))
        stack.enter_context(patch.object(user_repository,'assignable_users',return_value=[{'fid':18,'first_name':'Max','last_name':'Beispiel'}]))
        return stack
    def post(self,path,data):
        r=self.rf.post(path,data);r._dont_enforce_csrf_checks=True;return r
    def test_new_defect_binds_device_and_named_choices(self):
        with self.context():r=wf.defect_editor(self.rf.get('/defect/edit/',{'playdeviceFid':42}))
        text=r.content.decode()
        self.assertIn('name="playdeviceFid" value="42"',text)
        self.assertIn('Musterpark',text);self.assertIn('Schaukel',text)
        self.assertIn('name="responsibleUserFid"',text)
        self.assertNotIn('hx-post=',text)
    def test_priority_b_uses_correct_command_contract_and_redirects(self):
        data={'playdeviceFid':42,'defectDescription':'Defekt','priority':'2','defectsResponsibleBodyId':'1','responsibleUserFid':'18'}
        with self.context(),patch.object(wf,'_native',return_value=HttpResponse('{"errorMessage":"","tid":321}')) as native:
            r=wf.defect_editor(self.post('/defect/edit/',data))
        self.assertEqual(r.status_code,303);self.assertIn('tid=321',r['Location'])
        payload=native.call_args.args[2]
        self.assertEqual((payload['defectsResponsibleBodyId'],payload['responsibleUserFid']),(1,18))
        self.assertNotIn('responsibleUser',payload)
    def test_invalid_defect_retains_description_without_command(self):
        with self.context(),patch.object(wf,'_native') as command:
            r=wf.defect_editor(self.post('/defect/edit/',{'playdeviceFid':42,'defectDescription':'Bitte behalten','priority':'2'}))
        self.assertEqual(r.status_code,400);self.assertIn(b'Bitte behalten',r.content);command.assert_not_called()
    def test_logout_post_clears_scoped_cookie_and_redirects(self):
        r=wf.logout(self.post('/logout/',{}))
        self.assertEqual(r.status_code,302)
        self.assertEqual(r.cookies[wf.settings.auth_cookie_name]['max-age'],'0')
        self.assertEqual(r.cookies[wf.settings.auth_cookie_name]['path'],wf.settings.base_path or '/')
    def test_logout_new_session_endpoint_is_post_only_and_revokes_session(self):
        from django.test import Client
        from playground_check.django_project.urls import urlpatterns
        from django.urls import resolve
        endpoint = resolve('/session/end/')
        self.assertIs(endpoint.func, wf.logout)
        self.assertEqual(Client().get('/session/end/').status_code, 405)
        with patch('playground_check.domain_support.revoke_request_session') as revoke:
            result = Client().post('/session/end/')
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result['Location'], '/login/')
        self.assertEqual(result.cookies[wf.settings.auth_cookie_name]['max-age'], '0')
        revoke.assert_called_once()

    def test_logout_does_not_require_csrf_token(self):
        from django.test import Client
        with patch('playground_check.domain_support.revoke_request_session') as revoke:
            response = Client(enforce_csrf_checks=True).post('/session/end/')
        self.assertEqual(response.status_code, 302)
        revoke.assert_called_once()
        self.assertEqual(response.cookies[wf.settings.auth_cookie_name]['max-age'], '0')

    def test_logout_form_does_not_include_csrf_token(self):
        request = self.rf.get('/defects/', SCRIPT_NAME='/stadtgruen/spielplatzkontrolle')
        response = ui._render(request, 'error.html',
                              {'private': True, 'user': USER, 'message': 'Test'})
        from html.parser import HTMLParser
        class LogoutFormParser(HTMLParser):
            inside = False
            fields = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'form' and 'data-logout' in attrs:
                    self.inside = True
                if self.inside and tag == 'input':
                    self.fields.append(attrs.get('name'))
            def handle_endtag(self, tag):
                if tag == 'form':
                    self.inside = False
        parser = LogoutFormParser()
        parser.feed(response.content.decode())
        self.assertNotIn('csrfmiddlewaretoken', parser.fields)
    def test_inactive_unchanged_assignment_is_allowed(self):
        previous={'tid':321,'playdevice_fid':42,'responsible_user_fid':18,'date_done':None}
        payload={'tid':321,'playdeviceFid':42,'responsibleUserFid':18,'defectDescription':'Alt','assignmentStatus':'zugewiesen'}
        db=MagicMock();db.__enter__.return_value=db
        with patch.object(ui,'require_user',return_value=(USER,None)),patch.object(ui,'connect',return_value=db),patch('playground_check.inspection_defect_repository.defect_by_tid',return_value=previous),patch('playground_check.django_project.defect_commands.update_defect',return_value=HttpResponse('{"errorMessage":""}')) as command,patch.object(user_repository,'assignable_users',return_value=[]) as assignable:
            r=ui.defect_detail(self.post('/defect/',{'tid':321,'action':'save','description':'Neu','priority':'1','body_id':'1','person_id':'18'}))
        self.assertEqual(r.status_code,302);command.assert_called_once();assignable.assert_not_called()
    def test_detail_validation_error_retains_input(self):
        row={'tid':321,'playdevice_fid':42,'responsible_user_fid':18}
        serialized={'tid':321,'playdeviceFid':42,'responsibleUserFid':18,'defectDescription':'Alt','defectComment':'','assignmentStatus':''}
        db=MagicMock();db.__enter__.return_value=db
        with patch.object(ui,'require_user',return_value=(USER,None)),patch.object(ui,'connect',return_value=db),patch('playground_check.inspection_defect_repository.defect_by_tid',return_value=row),patch.object(domain_support,'_defect_dict',return_value=serialized),patch.object(user_repository,'assignable_users',return_value=[]):
            r=ui.defect_detail(self.post('/defect/',{'tid':321,'action':'save','description':'Ungespeichert','defect_comment':'Bemerkung','priority':'2','body_id':'-1','person_id':'-1'}))
        self.assertEqual(r.status_code,400);self.assertIn(b'Ungespeichert',r.content);self.assertIn(b'Bemerkung',r.content)
    def test_proxy_navigation_uses_path_info(self):
        request=self.rf.get('/defects/',SCRIPT_NAME='/stadtgruen/spielplatzkontrolle')
        r=ui._render(request,'error.html',{'private':True,'user':USER,'message':'Test'})
        self.assertIn(b'aria-current="page"',r.content)
        self.assertIn(b'/stadtgruen/spielplatzkontrolle/admin/users/',r.content)
        self.assertIn(b'/stadtgruen/spielplatzkontrolle/session/end/',r.content)

if __name__=='__main__':unittest.main()
