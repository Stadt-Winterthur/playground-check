"""Local-only visual fixtures built from the real templates and scripts.

No real database, credentials, mail, WMS or production web requests are used.
Run from responsive.cjs, not as a deployed application.
"""
import os
from pathlib import Path
import shutil
import tempfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from unittest.mock import MagicMock, patch
os.environ.setdefault('PLAYGROUND_SECURITY_KEY','browser-fixture-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','playground_check.django_project.settings')
import django
django.setup()
from django.test import RequestFactory
from playground_check.django_project import python_ui as ui,python_ui_workflows as wf
from playground_check import domain_support,user_repository

USER={'fid':17,'role':'administrator','mailAddress':'anna@example.org','firstName':'Anna','lastName':'Muster'}
KIND='Visuelle Inspektion (VI)'
CRITERION={'check':'Sichtkontrolle der Schrauben und Verbindungen','maintenance':'Lockere Verbindungen nachziehen','checkShortText':'Schrauben und Nieten'}
FEATURES=[{'properties':{'fid':i,'type':{'description':'Kletterkombination mit Rutschbahn','name':'Klettergerät','standard':'SN EN 1176'},'supplier':'Beispiellieferant','comment':'Regelmässige Kontrolle','generalInspectionCriteria':[CRITERION,CRITERION]},'geometry':{'coordinates':[2700212,1262696]}} for i in range(42,46)]
PAYLOAD={'name':'Spielplatz Musterpark','id':123,'inspectionTypeOptions':[KIND],'playdevices':FEATURES,'documentsOfAcceptance':[{'fid':1,'name':'Abnahmeprotokoll 2026'}],'certificateDocuments':[]}
PREFIX='/test-app'


def inspection_response(method, path, body=b''):
    rf = RequestFactory()
    if method == 'POST':
        request = rf.post(path, body, content_type='application/x-www-form-urlencoded', SCRIPT_NAME=PREFIX)
        request._dont_enforce_csrf_checks = True
    else:
        request = rf.get(path, SCRIPT_NAME=PREFIX)
    with patch.object(ui, 'require_user', return_value=(USER, None)), \
         patch.object(ui, 'playground_only_names_data', return_value=[{'name': PAYLOAD['name']}]), \
         patch.object(ui, 'playground_by_name_data', return_value=PAYLOAD), \
         patch('playground_check.django_project.inspection_device_commands.create_inspection', side_effect=AssertionError('fixture must never save')):
        return ui.inspection_editor(request)


def build(root):
    rf=RequestFactory()
    def request(name):return rf.get('/'+name+'/',SCRIPT_NAME=PREFIX)
    def save(name,response):(root/(name+'.html')).write_bytes(response.content)
    def render(name,template,data,private=True):
        save(name,ui._render(request(name),template,{'private':private,'user':USER,**data}))
    save('home',ui.home(request('')))
    from playground_check.django_project.localization import app_manifest
    (root / "manifest.webmanifest").write_bytes(app_manifest(request("manifest.webmanifest")).content)
    save('login',wf.login(request('login')))
    render('home-private','home.html',{})
    render('profile','profile.html',{'display_name':'Anna Muster','email':'anna.muster@example.org','role':'administrator'})
    render('profile-long','profile.html',{'display_name':'Anna Muster','email':'sehr.lange.funktionsbezeichnung.geoinformation@stadtverwaltung-winterthur.example.org','role':'administrator'})
    render('detail','detail.html',{'playground':PAYLOAD,'is_admin':True})
    render('assigned','assigned.html',{'rows':[{'name':PAYLOAD['name']}],'inspection_mode':True,'inspection_types':[KIND]})
    render('defect','defect_detail.html',{'tid':321,'defect':{'playdeviceFid':42,'defectDescription':'Schraube locker','responsibleUserFid':17,'assignmentStatus':'zugewiesen'},'users':[{'fid':17,'first_name':'Anna','last_name':'Muster'}],'assigned_name':'Anna Muster','can_respond':True})
    render('defects','defects.html',{'rows':[{'tid':321,'playground_name':'Musterpark','description':'Schraube locker','priority':1}],'state':'open'})
    render('admin','admin_users.html',{'rows':[{'email':'anna.muster@example.org','first_name':'Anna','last_name':'Muster','active':True,'role':'administrator'}]})
    with patch.object(ui,'require_user',return_value=(USER,None)),patch.object(ui,'playground_only_names_data',return_value=[{'name':PAYLOAD['name']}]),patch.object(ui,'playground_by_name_data',return_value=PAYLOAD):
        save('inspection',ui.inspection_editor(rf.get('/inspection/',{'name':PAYLOAD['name'],'inspectiontype':KIND},SCRIPT_NAME=PREFIX)))
        save('inspection-success',ui._render(request('inspection'),'inspection_success.html',{'name':PAYLOAD['name'],'kind':KIND,'private':True,'user':USER}))
    db=MagicMock();db.__enter__.return_value=db
    with patch.object(ui,'require_user',return_value=(USER,None)),patch.object(domain_support,'playground_by_device_data',return_value=PAYLOAD),patch('playground_check.db.connect',return_value=db),patch.object(user_repository,'assignable_users',return_value=[{'fid':17,'first_name':'Anna','last_name':'Muster'}]):
        save('create-defect',wf.defect_editor(rf.get('/defect/edit/',{'playdeviceFid':42},SCRIPT_NAME=PREFIX)))
    shutil.copytree(Path(ui.__file__).resolve().parents[1]/'static',root/'static')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='spk-browser-') as directory:
        root=Path(directory);build(root)
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
            def do_GET(self):
                self.path=self.path.removeprefix(PREFIX)
                if self.path.startswith('/inspection/'):
                    return self.inspection_page('GET')
                if self.path == '/':
                    self.path = '/home.html'
                if self.path.startswith('/Playdevice/'):
                    self.path='/static/assets/no-device-photo.svg'
                super().do_GET()
            def do_POST(self):
                self.path = self.path.removeprefix(PREFIX)
                if self.path.startswith('/inspection/'):
                    return self.inspection_page('POST')
                self.send_error(405)
            def inspection_page(self, method):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0))) if method == 'POST' else b''
                response = inspection_response(method, self.path, body)
                self.send_response(response.status_code)
                for key, value in response.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.content)
            def end_headers(self):
                self.send_header('Content-Security-Policy', ui.home(RequestFactory().get('/'))['Content-Security-Policy'])
                if self.path == '/static/sw.js':
                    self.send_header('Service-Worker-Allowed', PREFIX + '/')
                    self.send_header('Cache-Control', 'no-cache')
                super().end_headers()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        print(server.server_address[1],flush=True)
        server.serve_forever()
