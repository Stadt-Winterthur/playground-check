"""API regression contracts for writes. No production database connections.

Oracle is the FID master. The web application may create transfer IDs (TIDs)
for inspections and defect photos, but must not manufacture new FIDs.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("PLAYGROUND_SECURITY_KEY", "test-security-key-at-least-32-characters-long")

from playground_check import service
from playground_check.server import Application


class Cursor:
    def __init__(self, row=None):
        self.row = row
        self.rowcount = 1

    def fetchone(self):
        return self.row


class Database:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith("LOCK TABLE"):
            return Cursor()
        if self.responses:
            return Cursor(self.responses.pop(0))
        return Cursor()


class WriteOperationContractTest(unittest.TestCase):
    def setUp(self):
        self.app = Application()
        self.db = Database()
        self.user = {
            "fid": 42, "mailAddress": "test@winterthur.ch", "role": "administrator",
            "firstName": "Test", "lastName": "User",
        }

    def request(self, method, path, body, *, user=True):
        pathname, _, query = path.partition("?")
        payload = json.dumps(body).encode("utf-8")
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": pathname, "QUERY_STRING": query,
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        }
        captured = {}

        def start(status, headers):
            captured["status"] = int(status.split()[0])

        @contextmanager
        def fake_connect():
            yield self.db

        with (
            patch.object(service, "connect", fake_connect),
            patch.object(service, "require_user", return_value=(self.user, None) if user else (None, service.Response.text("Unauthorized", 401))),
            patch.object(service, "current_user", return_value=self.user if user else None),
        ):
            raw = b"".join(self.app(environ, start))
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            result = raw
        return captured["status"], result

    def assert_no_write(self):
        self.assertFalse(any(re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql, re.I) for sql, _ in self.db.calls))

    def test_device_save_updates_existing_fid_without_new_identifier(self):
        status, body = self.request("POST", "/Playdevice/", {"properties": {
            "fid": 1234, "recommendedYearOfRenovation": 2030,
            "renovationType": 3, "cannotBeChecked": False,
        }})
        self.assertEqual((status, body), (200, {"errorMessage": ""}))
        self.assertEqual(len(self.db.calls), 1)
        sql, params = self.db.calls[0]
        self.assertIn('UPDATE "gr_v_spielgeraete"', sql)
        self.assertNotIn("INSERT", sql.upper())
        self.assertEqual(params[-1], 1234)
        self.assertEqual(params[:2], (2030, 3))

    def test_device_save_without_properties_does_not_write(self):
        status, body = self.request("POST", "/Playdevice/", {})
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-5"}))
        self.assert_no_write()

    def test_update_defect_uses_existing_tid_not_new_fid(self):
        self.db.responses = [{"responsible_user_fid": None}]
        with patch.object(service, "_record_assignment_change") as history:
            status, body = self.request("POST", "/Defect/", {
                "tid": 901, "priority": 1, "defectDescription": "Befestigung pruefen",
            })
        self.assertEqual((status, body), (200, {"errorMessage": ""}))
        self.assertEqual(len(self.db.calls), 2)
        sql, params = self.db.calls[1]
        self.assertIn('UPDATE "wgr_sp_insp_mangel"', sql)
        self.assertRegex(sql, r"WHERE tid=%s")
        self.assertEqual(params[-1], 901)
        self.assertNotIn("INSERT", sql.upper())
        history.assert_called_once()

    def test_update_defect_missing_body_does_not_write(self):
        status, body = self.request("POST", "/Defect/", {})
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-4"}))
        self.assert_no_write()

    def test_update_defect_missing_tid_returns_existing_error(self):
        self.db.responses = [None]
        status, body = self.request("POST", "/Defect/", {
            "tid": 991, "priority": 1, "defectDescription": "Test",
        })
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-3"}))
        self.assert_no_write()

    def test_inspection_empty_report_is_rejected_without_write(self):
        status, body = self.request("POST", "/Inspection/", [])
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-0"}))
        self.assert_no_write()

    def test_inspection_mixed_types_rejected_without_write(self):
        status, body = self.request("POST", "/Inspection/", [
            {"inspectionType": "Visuelle Inspektion (VI)"},
            {"inspectionType": "Hauptinspektion (HI)"},
        ])
        self.assertEqual((status, body), (200, {"errorMessage": "SPK-6"}))
        self.assert_no_write()

    def test_maintenance_role_cannot_create_inspection(self):
        self.user["role"] = "maintenance"
        status, body = self.request("POST", "/Inspection/", [
            {"inspectionType": "Visuelle Inspektion (VI)", "playdeviceFid": 123},
        ])
        self.assertEqual(status, 403)
        self.assert_no_write()

    def test_inspection_insert_uses_tid_and_existing_playground_fid(self):
        self.db.responses = [
            {"fid": 12}, {"id": 1}, {"fid_spielplatz": 34},
            {"exists": 1}, {"fid_spielplatz": 34}, None,
            {"target": None}, {"tid": 802},
            {"nicht_zu_pruefen": False, "nicht_pruefbar": False},
        ]
        status, body = self.request("POST", "/Inspection/", [{
            "inspectionType": "Visuelle Inspektion (VI)",
            "playdeviceFid": 123, "inspectionText": "Pruefung", "inspectionDone": True,
        }])
        self.assertEqual((status, body), (200, {"errorMessage": ""}))
        inserts = [(sql, params) for sql, params in self.db.calls if sql.strip().upper().startswith("INSERT")]
        self.assertEqual(len(inserts), 2)
        inspection_sql, inspection_params = inserts[0]
        report_sql, report_params = inserts[1]
        self.assertIn('INSERT INTO "wgr_sp_inspektion"', inspection_sql)
        self.assertIn('INSERT INTO "wgr_sp_insp_bericht"', report_sql)
        self.assertRegex(inspection_sql, r"max\(tid\)\+1")
        self.assertRegex(report_sql, r"max\(tid\)\+1")
        self.assertRegex(inspection_sql, r"RETURNING tid")
        self.assertEqual(inspection_params[1], 34)
        self.assertEqual(report_params[0], 802)
        for sql, _ in inserts:
            columns = sql.split("VALUES", 1)[0]
            self.assertNotRegex(columns, r"(?i)(?<!_)\bfid\s*[,)]")

    def test_inspection_unauthorized_rejected_without_write(self):
        status, _ = self.request("POST", "/Inspection/", [{}], user=False)
        self.assertEqual(status, 401)
        self.assert_no_write()

    def test_defect_photo_allocates_tid_and_links_existing_defect_tid(self):
        self.db.responses = [{"tid": 5500}]
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"test").decode("ascii")
        status, body = self.request("PUT", "/Defect/Picture/901/", {
            "base64StringPicture": png, "base64StringPictureThumb": png,
            "afterFixing": True,
        })
        self.assertEqual((status, body), (200, {"tid": 5500}))
        self.assertEqual(len(self.db.calls), 2)
        self.assertIn('LOCK TABLE "wgr_sp_insp_mangel_foto"', self.db.calls[0][0])
        sql, params = self.db.calls[1]
        self.assertIn('INSERT INTO "wgr_sp_insp_mangel_foto"', sql)
        self.assertIn("COALESCE(MAX(tid),0)+1", sql)
        self.assertIn("RETURNING tid", sql)
        self.assertEqual(params[0], 901)
        self.assertEqual(params[-1], True)
        self.assertNotRegex(sql.split("VALUES", 1)[0], r"(?i)(?<!_)\bfid\b")

    def test_defect_photo_invalid_base64_rejected_without_write(self):
        status, body = self.request("PUT", "/Defect/Picture/901/", {
            "base64StringPicture": "not base64!!!",
        })
        self.assertEqual(status, 400)
        self.assertIn(b"Base64", body)
        self.assert_no_write()

    def test_playdevice_picture_dry_run_does_not_write(self):
        status, _ = self.request("PUT", "/Playdevice/123/Picture/?dryRun=true", {"data": "invalid"})
        self.assertEqual(status, 200)
        self.assert_no_write()


if __name__ == "__main__":
    unittest.main()
