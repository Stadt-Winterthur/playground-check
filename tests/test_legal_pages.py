"""Local legal pages, anonymous access and ordered navigation links."""
import os
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')
import django
django.setup()
from django.test import Client
from playground_check.django_project import python_ui


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.hrefs=[]; self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.hrefs.append(dict(attrs).get('href', ''))


class LegalPagesTests(unittest.TestCase):
    def test_imprint_is_a_public_local_page_without_identity_or_database_access(self):
        with patch('playground_check.domain_support.connect', side_effect=AssertionError('database queried')):
            response = Client().get('/imprint/', HTTP_COOKIE='playground.auth=expired')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<h1 id="imprint-title">Impressum</h1>', html)
        for text in ('Stadtgrün Winterthur', 'Turbinenstrasse 16', '8403 Winterthur', 'Fachstelle Geoinformation'):
            self.assertIn(text, html)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn('Location', response)
        self.assertNotIn('https://stadt.winterthur.ch/impressum', html)
        self.assertEqual(Client().post('/imprint/').status_code, 405)

    def test_legal_pages_keep_validated_account_and_navigation(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        user = {'fid': 31, 'role': 'administrator', 'mailAddress': 'test@example.invalid'}
        for route in ('/privacy/', '/imprint/'):
            with self.subTest(route=route), patch.object(python_ui, 'require_user', return_value=(user, None)) as identity:
                response = Client().get(route, SCRIPT_NAME=prefix)
                identity.assert_called_once()
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn('class="authenticated"', html)
                self.assertIn('class="side-navigation"', html)
                self.assertIn(prefix+'/admin/users/', Links(html).hrefs)
                self.assertIn(prefix+'/profile/', Links(html).hrefs)
                self.assertIn(prefix+'/session/end/', html)
                self.assertNotIn('class="header-login"', html)
                self.assertIn('no-store', response['Cache-Control'])

    def test_legal_pages_stay_public_if_session_is_invalid_or_unavailable(self):
        for route in ('/privacy/', '/imprint/'):
            for failure in (False, True):
                with self.subTest(route=route, failure=failure), patch.object(
                    python_ui, 'require_user', return_value=(None, object()),
                    side_effect=RuntimeError('database unavailable') if failure else None,
                ):
                    response = Client().get(route, HTTP_COOKIE='playground.auth=expired')
                    self.assertEqual(response.status_code, 200)
                    html = response.content.decode()
                    self.assertIn('class="anonymous"', html)
                    self.assertIn('class="header-login"', html)
                    self.assertNotIn('class="side-navigation"', html)
                    self.assertNotIn('Location', response)
                    self.assertNotIn('playground.auth', response.cookies)

    def test_sidebar_and_footer_do_not_duplicate_header_legal_links(self):
        user = {'fid':31, 'role':'inspector', 'mailAddress':'test@example.invalid'}
        prefix = '/stadtgruen/spielplatzkontrolle'
        with patch.object(python_ui, 'require_user', return_value=(user, None)):
            response = Client().get('/profile/', SCRIPT_NAME=prefix)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        sidebar = html.split('<aside class="side-navigation"',1)[1].split('</aside>',1)[0]
        self.assertNotIn(prefix+'/privacy/', Links(sidebar).hrefs)
        self.assertNotIn(prefix+'/imprint/', Links(sidebar).hrefs)
        self.assertNotIn('<footer ', html)

    def test_both_pages_cross_link_under_base_path_without_login(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        for route, target in [('/imprint/', '/privacy/'), ('/privacy/', '/imprint/')]:
            response = Client().get(route, SCRIPT_NAME=prefix)
            self.assertEqual(response.status_code, 200)
            self.assertIn(prefix+target, Links(response.content.decode()).hrefs)


    def test_legal_links_in_header_for_signed_in_and_anonymous_visitors(self):
        from django.test import RequestFactory
        prefix = '/stadtgruen/spielplatzkontrolle'
        for private in (True, False):
            with self.subTest(private=private):
                response = python_ui._render(
                    RequestFactory().get('/privacy/', SCRIPT_NAME=prefix), 'error.html',
                    {'private': private, 'user': {'fid': 31, 'role': 'inspector'} if private else None,
                     'message': 'Test'})
                html = response.content.decode()
                for target in ('/privacy/', '/imprint/'):
                    self.assertEqual(Links(html).hrefs.count(prefix+target), 1)
                header = html.split('<header class="app-header">', 1)[1].split('</header>', 1)[0]
                menu = header.split('<details ', 1)[1].split('</details>', 1)[0]
                links = Links(menu).hrefs
                self.assertEqual(links[-2:], [prefix+'/privacy/', prefix+'/imprint/'])
                self.assertNotIn(' open', menu.split('>', 1)[0])
                if private:
                    self.assertIn('menu-legal-links', menu)
                    self.assertIn(prefix+'/profile/', links)
                    self.assertIn(prefix+'/push/', links)
                    self.assertIn(prefix+'/session/end/', header)
                else:
                    self.assertIn('aria-label="Informationen"', menu)
                    self.assertIn(prefix+'/login/', Links(header).hrefs)
                    self.assertNotIn(prefix+'/profile/', links)


if __name__ == '__main__': unittest.main()
