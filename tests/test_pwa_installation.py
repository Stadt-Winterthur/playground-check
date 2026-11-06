"""Installation metadata must work behind the production reverse-proxy prefix."""
import json
import os
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.parse import urljoin

os.environ.setdefault('PLAYGROUND_SECURITY_KEY', 'test-security-key-at-least-32-characters-long')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground_check.django_project.settings')

import django
from django.test import RequestFactory
from playground_check.django_project import python_ui as ui, frontend

django.setup()


class InstallationTests(unittest.TestCase):
    def test_metadata_and_worker_use_actual_application_prefix(self):
        for prefix in ('', '/stadtgruen/spielplatzkontrolle'):
            with self.subTest(prefix=prefix), patch.object(ui, 'settings', replace(ui.settings, base_path=prefix, service_worker_enabled=True)):
                response = ui.home(RequestFactory().get('/', SCRIPT_NAME=prefix))
                html = response.content.decode()
                self.assertIn(f'rel="manifest" href="{prefix}/manifest.webmanifest"', html)
                self.assertIn(f'data-worker-url="{prefix}/static/sw.js"', html)
                self.assertIn(f'data-worker-scope="{prefix}/"', html)
                self.assertIn("manifest-src 'self'", response['Content-Security-Policy'])
                self.assertIn("worker-src 'self'", response['Content-Security-Policy'])

    def test_disabled_worker_is_not_registered(self):
        with patch.object(ui, 'settings', replace(ui.settings, service_worker_enabled=False)):
            response = ui.home(RequestFactory().get('/'))
        self.assertNotIn(b'pwa-register.js', response.content)
        self.assertIn(b'rel="manifest"', response.content)

    def test_public_manifest_icons_and_worker_scope(self):
        prefix = '/stadtgruen/spielplatzkontrolle'
        request = RequestFactory().get('/', SCRIPT_NAME=prefix)
        response = frontend.frontend(request, 'static/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')
        manifest = json.loads(response.content)
        base = f'https://example.org{prefix}/static/manifest.webmanifest'
        for key in ('start_url', 'scope'):
            self.assertEqual(urljoin(base, manifest[key]), f'https://example.org{prefix}/')
        for size in (192, 512):
            icon = next(i for i in manifest['icons'] if i['sizes'] == f'{size}x{size}')
            icon_response = frontend.frontend(request, 'static/' + icon['src'])
            self.assertEqual(icon_response.status_code, 200)
            self.assertEqual(icon_response['Content-Type'], 'image/png')
            self.assertEqual(struct.unpack('>II', icon_response.content[16:24]), (size, size))
        worker = frontend.frontend(request, 'static/sw.js')
        self.assertEqual(worker['Service-Worker-Allowed'], prefix + '/')
        self.assertEqual(worker['Cache-Control'], 'no-cache')
