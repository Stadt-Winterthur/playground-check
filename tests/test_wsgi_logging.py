"""Exercise the production WSGI import in a fresh process, without ELK traffic."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_CHECK = textwrap.dedent('''
    import importlib
    import logging
    import os
    import sys
    import threading
    from unittest.mock import patch
    from playground_check.config import settings
    from playground_check.logging_ext import ElkLogHandler, configure_logging

    delivered = []
    event = threading.Event()
    def capture(self, payload):
        delivered.append(payload)
        event.set()

    with patch.object(ElkLogHandler, '_post', capture):
        import playground_check.django_project.wsgi
        assert 'playground_check.server' not in sys.modules
        root = logging.getLogger()
        console = [h for h in root.handlers if getattr(h, '_playground_console', False)]
        elk = [h for h in root.handlers if isinstance(h, ElkLogHandler)]
        expected_elk = bool(settings.elk_url) and os.environ['ASPNETCORE_ENVIRONMENT'] != 'Development'
        assert len(console) == 1, len(console)
        assert len(elk) == int(expected_elk), len(elk)
        original_handlers = list(root.handlers)

        # Cached imports and explicit repeated setup must keep existing handlers.
        importlib.import_module('playground_check.django_project.wsgi')
        configure_logging(settings)
        configure_logging(settings)
        assert root.handlers == original_handlers

        if expected_elk:
            handler = elk[0]
            assert handler._worker.is_alive()
            assert handler.environment == 'logging-test'
            assert handler.service == 'playground-review-test'
            assert handler.verify_ssl is True
            logging.getLogger('playground_check.django_project.python_ui').info('WSGI logging regression test')
            assert event.wait(3), 'No event delivered through the configured handler'
            assert len(delivered) == 1, len(delivered)
            assert delivered[0]['message'] == 'WSGI logging regression test'
            assert delivered[0]['level'] == 'INFO'
            assert delivered[0]['service'] == 'playground-review-test'
            root.removeHandler(handler)
            handler.close()
            assert not handler._worker.is_alive()
        else:
            assert not any(t.name == 'playground-elk-log' for t in threading.enumerate())
''')


class WSGILoggingTests(unittest.TestCase):
    def check_bootstrap(self, *, elk_url, environment):
        env = {
            **os.environ,
            'PYTHONPATH': str(ROOT / 'src'),
            'DJANGO_SETTINGS_MODULE': 'playground_check.django_project.settings',
            'PLAYGROUND_SECURITY_KEY': 'test-security-key-at-least-32-characters-long',
            'PLAYGROUND_POSTGRES_DSN': '',
            'PLAYGROUND_ELK_URL': elk_url,
            'ELK__Url': '',
            'PLAYGROUND_ELK_ENVIRONMENT': 'logging-test',
            'PLAYGROUND_ELK_SERVICE': 'playground-review-test',
            'PLAYGROUND_ELK_VERIFY_SSL': 'true',
            'ASPNETCORE_ENVIRONMENT': environment,
        }
        result = subprocess.run([sys.executable, '-c', BOOTSTRAP_CHECK], cwd=ROOT,
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_production_wsgi_initializes_elk_and_delivers_once(self):
        self.check_bootstrap(elk_url='https://elk.example.invalid/test', environment='Production')

    def test_without_elk_url_wsgi_initializes_console_only(self):
        self.check_bootstrap(elk_url='', environment='Production')

    def test_development_keeps_existing_no_elk_policy(self):
        self.check_bootstrap(elk_url='https://elk.example.invalid/test', environment='Development')
