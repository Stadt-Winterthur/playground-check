from playground_check import service as legacy_service
"""Step 36: native document and push endpoints preserve API contracts."""
import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")
try:
    import django
except ImportError:
    django = None


@unittest.skipUnless(django is not None, "Django/DRF not installed")
class NativeDocumentsPushTests(unittest.TestCase):
    def setUp(self):
        from django.test import RequestFactory
        from playground_check import domain_support as service
        from playground_check.django_project import account_document_push_views as views
        self.rf = RequestFactory()
        self.views = views
        self.auth = patch.object(service, "require_user", return_value=({"fid": 31}, None))
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.db = MagicMock()
        self.db.__enter__.return_value = "db"
        self.connector = patch.object(service, "connect", return_value=self.db)
        self.connector.start()
        self.addCleanup(self.connector.stop)

    def test_pdf_download_keeps_bytes_and_avoids_legacy_handler(self):
        from playground_check import domain_support as service
        with patch.object(legacy_service, "get_document", side_effect=AssertionError("legacy invoked")), \
             patch.object(service.remaining_reads_repository, "document_blob", return_value={"content": b"%PDF-1.4\\n%%EOF"}):
            response = self.views.document_item(self.rf.get("/Document/9/?type=abnahme"), fid=9)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.4\\n%%EOF")
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_upload_allocates_document_fid_through_existing_repository(self):
        from playground_check import domain_support as service
        payload = {"type": "abnahme", "name": "Abnahme.pdf", "playgroundId": 55,
                   "contentBase64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode()}
        with patch.object(legacy_service, "post_document", side_effect=AssertionError("legacy invoked")), \
             patch.object(service.document_write_repository, "insert_document", return_value=801) as insert:
            response = self.views.document_create(self.rf.post("/Document/", json.dumps(payload), content_type="application/json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"fid": 801, "name": "Abnahme.pdf"})
        self.assertEqual(insert.call_args.args[0], "db")

    def test_invalid_upload_and_unauthorized_edit_never_write(self):
        from playground_check import domain_support as service
        from playground_check.http import Response
        with patch.object(service.document_write_repository, "insert_document", side_effect=AssertionError("must not write")):
            response = self.views.document_create(self.rf.post("/Document/", json.dumps({"type": "abnahme", "name": "x", "playgroundId": 1, "contentBase64": "AAAA"}), content_type="application/json"))
        self.assertEqual(response.status_code, 400)
        with patch.object(service, "require_user", return_value=(None, Response.text("denied", 401))), \
             patch.object(service.document_write_repository, "delete_document", side_effect=AssertionError("must not write")):
            response = self.views.document_item(self.rf.delete("/Document/9/?type=abnahme"), fid=9)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"denied")

    def test_rename_and_delete_use_given_document_fid(self):
        from playground_check import domain_support as service
        with patch.object(service.document_write_repository, "document_content", return_value={"content": b"%PDF-1.4"}), \
             patch.object(service.document_write_repository, "rename_document") as rename:
            response = self.views.document_rename(self.rf.put("/Document/9/Name/?type=abnahme", json.dumps({"name": "Neu.pdf"}), content_type="application/json"), fid=9)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rename.call_args.args[3], 9)
        with patch.object(service.document_write_repository, "delete_document", return_value={"fid": 9}) as delete:
            response = self.views.document_item(self.rf.delete("/Document/9/?type=abnahme"), fid=9)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(delete.call_args.args[2], 9)

    def test_push_operations_preserve_user_fid_and_contract(self):
        from playground_check import domain_support as service
        subscription = {"endpoint": "https://example.org/push", "p256dh": "key", "auth": "secret"}
        with patch.object(legacy_service, "push_register", side_effect=AssertionError("legacy invoked")), \
             patch.object(service.push_repository, "register_subscription") as register:
            response = self.views.push_register(self.rf.post("/PushSubscription/Register/", json.dumps(subscription), content_type="application/json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(register.call_args.args[:5], ("db", 31, "https://example.org/push", "key", "secret"))
        with patch.object(service.push_repository, "unregister_subscription") as unregister:
            response = self.views.push_unregister(self.rf.delete("/PushSubscription/Unregister/", json.dumps({"endpoint": "https://example.org/push"}), content_type="application/json"))
        self.assertEqual(response.status_code, 200)
        unregister.assert_called_once_with("db", 31, "https://example.org/push")
        with patch.object(service.push_repository, "active_subscriptions", return_value=[{"endpoint": "https://example.org/push", "p256dh": "key", "auth": "secret", "user_agent": None}]) as repo:
            response = self.views.push_me(self.rf.get("/PushSubscription/Me/"))
        self.assertEqual(json.loads(response.content)[0]["endpoint"], "https://example.org/push")
        repo.assert_called_once_with("db", 31)
