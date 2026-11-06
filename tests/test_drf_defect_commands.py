"""Step 38: native defect command contracts and SMTP transaction ordering."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django  # noqa: F401
    import rest_framework  # noqa: F401
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django/DRF not installed")
class NativeDefectCommandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playground_check.django_project import wsgi  # noqa: F401
        from playground_check.django_project import defect_commands
        cls.native = defect_commands

    def test_unauthorized_write_stops_before_repository(self):
        from django.test import RequestFactory
        from playground_check.http import Response
        native = self.native
        with patch.object(native.service, "require_user", return_value=(None, Response.text("denied", 401))), \
             patch.object(native.service, "connect", side_effect=AssertionError("DB accessed")):
            response = native.update_defect(RequestFactory().post("/Defect/", data="{}", content_type="application/json"))
        self.assertEqual((response.status_code, response.content), (401, b"denied"))

    def test_create_missing_description_never_writes_and_preserves_body(self):
        from django.test import RequestFactory
        native = self.native
        user = {"fid": 17, "mailAddress": "staff@example.org"}
        with patch.object(native.service, "require_user", return_value=(user, None)), \
             patch.object(native.service, "connect", side_effect=AssertionError("DB accessed")):
            response = native.create_defect(RequestFactory().put(
                "/Defect/", data='{"tid":42,"done":true}', content_type="application/json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'{"tid":42}')

    def test_picture_dry_run_has_no_authentication_or_database(self):
        from django.test import RequestFactory
        native = self.native
        with patch.object(native.service, "require_user", side_effect=AssertionError("auth")), \
             patch.object(native.service, "connect", side_effect=AssertionError("database")):
            response = native.get_defect_picture(RequestFactory().get("/Defect/Picture/77/?dryRun=true"), 77)
        self.assertEqual((response.status_code, response.content), (200, b""))

    def test_mail_not_marked_sent_when_smtp_fails_and_connections_closed(self):
        from django.test import RequestFactory
        native = self.native
        user = {"fid": 17, "mailAddress": "staff@example.org"}
        events = []
        class Connection:
            def __enter__(self):
                events.append("open")
                return "db"
            def __exit__(self, *args):
                events.append("closed")
        def fail_deliver(*args):
            events.append("smtp")
            raise OSError("connection refused")
        row = {"playdevice_fid": 12, "responsible_user_fid": 9}
        recipient = {"fid": 9, "active": True, "email": "to@example.org", "name": "Recipient"}
        with patch.object(native.service, "require_user", return_value=(user, None)), \
             patch.object(native.service, "connect", return_value=Connection()), \
             patch.object(native.service.mail_repository, "defect", return_value=row), \
             patch.object(native.service.mail_repository, "recipient", return_value=recipient), \
             patch.object(native.service.mail_repository, "device", return_value={"fid": 12}), \
             patch.object(native.service.mail_repository, "pictures", return_value=[]), \
             patch.object(native, "compose_defect_mail", return_value="message"), \
             patch.object(native, "deliver", side_effect=fail_deliver), \
             patch.object(native.service.mail_repository, "mark_sent", side_effect=AssertionError("marked sent")):
            response = native.send_info_mail(RequestFactory().post("/Defect/55/send-mail/"), 55)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(events, ["open", "closed", "smtp"])
