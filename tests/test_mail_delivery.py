"""No live SMTP or database required for notification contract tests."""
from __future__ import annotations

import io
import json
import os
import smtplib
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
from playground_check import service
from playground_check.mail_service import MailAttachment, MailConfigurationError, compose_defect_mail, deliver
from playground_check.server import Application


class Db:
    def __init__(self):
        self.writes = []
        self.rowcount = 1
    def execute(self, sql, params=None):
        if sql.startswith("UPDATE"):
            self.writes.append((sql, params))
        self.sql = sql
        return self
    def fetchone(self):
        if 'WHERE tid=%s' in self.sql and 'wgr_sp_insp_mangel' in self.sql:
            return dict(tid=321, playdevice_fid=123, priority=2, description='Defekt',
                        responsible_body_id=1, responsible_user_fid=45, date_creation=None)
        if 'wgr_sp_kontrolleur' in self.sql:
            return dict(fid=45, name='Muster Max', email='max.muster@win.ch', active=True)
        if 'gr_v_spielgeraete' in self.sql:
            return dict(playground_name='Spielplatz', address='Winterthur', device_type='Schaukel')
        return None
    def fetchall(self):
        return []


class MailTests(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.app = Application()

    def request(self, *, smtp_ok):
        environment = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/Defect/321/send-mail',
                       'wsgi.input': io.BytesIO(b'{}'), 'CONTENT_TYPE': 'application/json',
                       'CONTENT_LENGTH': '2'}
        captured = {}
        def start(status, headers):
            captured['status'] = int(status.split(' ')[0])
        @contextmanager
        def connect():
            yield self.db
        def deliver(message, recipient):
            self.assertEqual(recipient, 'max.muster@win.ch')
            if not smtp_ok:
                raise OSError('connection refused')
        with patch.object(service, 'connect', connect), patch.object(service, 'require_user', return_value=(
                {'fid': 1, 'firstName': 'Test', 'lastName': 'User'}, None)), patch(
                'playground_check.mail_service.deliver', side_effect=deliver), patch.object(
                service, '_defect_dict', return_value={'tid': 321, 'infoMailSentAt': 'now'}):
            result = b''.join(self.app(environment, start))
        return captured['status'], result

    def test_smtp_failure_does_not_mark_sent(self):
        status, _ = self.request(smtp_ok=False)
        self.assertEqual(status, 502)
        self.assertEqual(self.db.writes, [])

    def test_success_marks_sent_only_after_delivery(self):
        status, data = self.request(smtp_ok=True)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['tid'], 321)
        self.assertEqual(len(self.db.writes), 1)
        self.assertIn('infomail_gesendet_am', self.db.writes[0][0])
        self.assertEqual(self.db.writes[0][1], ('Muster Max', 321, 45))

    def test_sender_comes_from_environment(self):
        with patch.dict(os.environ, {"SMTP_FROM": "test-sender@example.org"}):
            message = compose_defect_mail(
                {"tid": 321}, {}, {"name": "Max", "email": "max@example.org"},
                {}, [])
        self.assertEqual(message["From"], "test-sender@example.org")

    def test_sender_missing_is_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MailConfigurationError):
                compose_defect_mail({"tid": 321}, {},
                    {"name": "Max", "email": "max@example.org"}, {}, [])

    def test_smtp_port_comes_from_environment(self):
        from email.message import EmailMessage
        message = EmailMessage()
        message["From"] = "test-sender@example.org"
        message["To"] = "max@example.org"
        with patch.dict(os.environ, {"SMTP_PORT": "2525", "SMTP_HOST": "smtp.example.org"}):
            with patch("playground_check.mail_service.smtplib.SMTP") as smtp:
                deliver(message, "max@example.org")
        smtp.assert_called_once_with("smtp.example.org", 2525, timeout=10.0)

    def test_smtp_port_missing_or_invalid(self):
        from email.message import EmailMessage
        message = EmailMessage()
        for value in (None, "abc", "0", "65536"):
            environment = {} if value is None else {"SMTP_PORT": value}
            with self.subTest(port=value), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(MailConfigurationError):
                    deliver(message, "max@example.org")

    def test_subject_html_escaping_and_attachment(self):
        message = compose_defect_mail(
            {'tid':321, 'description':'<script>alert(1)</script>', 'priority':2},
            {'playground_name':'Spielplatz'},
            {'name':'Max Muster','email':'max.muster@win.ch'},
            {'firstName':'Test', 'lastName':'User'},
            [MailAttachment('Foto.png', 'image/png', b'png-data')])
        self.assertIn('&lt;script&gt;', message.get_body(preferencelist=('html',)).get_content())
        self.assertEqual(len(list(message.iter_attachments())), 1)
        self.assertNotIn('X-Unsent', message)


if __name__ == '__main__':
    unittest.main()
