"""Python-rendered UI preview contracts."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
try:
    from django.test import RequestFactory
except ImportError:
    RequestFactory = None

@unittest.skipUnless(RequestFactory is not None, 'Django not installed')
class PythonUITest(unittest.TestCase):
    def setUp(self):
        from playground_check.django_project import python_ui
        self.ui = python_ui
        self.rf = RequestFactory()

    def test_preview_home(self):
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)):
            result = self.ui.home(self.rf.get('/'))
        self.assertEqual(result.status_code, 200)
        self.assertIn('frame-ancestors', result['Content-Security-Policy'])

    def test_html_escaping(self):
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *_): return self
            def fetchall(self): return [dict(name='<script>',street_name='A&B',house_no='1')]
        with patch.object(self.ui, 'require_user', return_value=({'fid': 1}, None)), patch.object(self.ui, 'connect', return_value=DB()):
            result = self.ui.playgrounds(self.rf.get('/playgrounds/'))
        self.assertNotIn(b'<script>',result.content)
        self.assertIn(b'&lt;script&gt;',result.content)

    def test_db_failure_does_not_expose_exception(self):
        with patch.object(self.ui, 'require_user', return_value=({'fid': 1}, None)), patch.object(self.ui,'connect',side_effect=RuntimeError('secret')):
            result = self.ui.playgrounds(self.rf.get('/playgrounds/'))
        self.assertEqual(result.status_code,503)
        self.assertNotIn(b'secret',result.content)

    def test_reverse_proxy_links_and_css(self):
        request = self.rf.get('/', **{'SCRIPT_NAME': '/stadtgruen/spielplatzkontrolle'})
        with patch.object(self.ui, "require_user", return_value=({"fid": 1}, None)):
            response = self.ui.home(request)
        html = response.content.decode('utf-8')
        prefix = '/stadtgruen/spielplatzkontrolle'
        self.assertIn(f'href="{prefix}/static/css/python-ui.css"', html)
        self.assertIn(f'href="{prefix}/"', html)
        self.assertIn(f'href="{prefix}/playgrounds/"', html)

    def test_reverse_proxy_search_form(self):
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *_): return self
            def fetchall(self): return []
        request = self.rf.get('/playgrounds/', **{'SCRIPT_NAME': '/stadtgruen/spielplatzkontrolle'})
        with patch.object(self.ui, 'require_user', return_value=({'fid': 1}, None)), patch.object(self.ui, 'connect', return_value=DB()):
            response = self.ui.playgrounds(request)
        html = response.content.decode('utf-8')
        self.assertIn('action="/stadtgruen/spielplatzkontrolle/playgrounds/"', html)
