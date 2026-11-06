"""Regression contract: PostgreSQL transfer IDs are not Oracle master FIDs.

All tests use a fake database and never connect to either production system.
"""
from __future__ import annotations

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


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class TransferDatabase:
    def __init__(self, next_tid=87001, fail=False):
        self.calls = []
        self.next_tid = next_tid
        self.fail = fail

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query.startswith('LOCK TABLE'):
            return FakeCursor()
        if query.startswith('INSERT INTO "wgr_sp_insp_mangel"'):
            if self.fail:
                raise RuntimeError('simulated database failure')
            return FakeCursor({"tid": self.next_tid})
        raise AssertionError(f"Unexpected SQL: {query}")


class DefectTransferContractTest(unittest.TestCase):
    def setUp(self):
        self.app = Application()
        self.user = {"fid": 42, "mailAddress": "test@winterthur.ch", "role": "administrator"}
        self.db = TransferDatabase()

    def request(self, method, path, body):
        payload = json.dumps(body).encode("utf-8")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload),
        }
        capture = {}

        def start_response(status, headers):
            capture["status"] = int(status.split()[0])
            capture["headers"] = dict(headers)

        @contextmanager
        def fake_connect():
            yield self.db

        with (
            patch.object(service, "require_user", return_value=(self.user, None)),
            patch.object(service, "connect", fake_connect),
            patch.object(service, "_assignment_history", return_value=[]),
        ):
            result = b"".join(self.app(environ, start_response))
        return capture["status"], json.loads(result)

    def test_put_defect_creates_transfer_id_without_generating_fid(self):
        status, result = self.request("PUT", "/Defect/", {
            "playdeviceFid": 123,
            "priority": 1,
            "defectDescription": "Lose Schraube",
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["tid"], 87001)
        self.assertNotIn("fid", result)
        self.assertEqual(result["errorMessage"], "")

        self.assertEqual(len(self.db.calls), 2)
        lock_sql, _ = self.db.calls[0]
        insert_sql, params = self.db.calls[1]
        self.assertEqual(lock_sql, 'LOCK TABLE "wgr_sp_insp_mangel" IN EXCLUSIVE MODE')
        self.assertRegex(insert_sql, r"(?is)INSERT\s+INTO\s+\"wgr_sp_insp_mangel\"")
        columns = re.search(r"\(\s*tid\s*,.*?\)\s*VALUES", insert_sql, re.I | re.S).group(0)
        self.assertRegex(columns, r"(?i)\btid\b")
        self.assertNotRegex(columns, r"(?i)(?<!_)\bfid\b")
        self.assertRegex(insert_sql, r"(?is)max\s*\(\s*tid\s*\)\s*\+\s*1")
        self.assertRegex(insert_sql, r"(?i)RETURNING\s+tid")
        self.assertEqual(params[0], 123)
        self.assertEqual(params[1], 1)
        self.assertEqual(params[2], "Lose Schraube")

    def test_missing_description_must_not_insert(self):
        status, result = self.request("PUT", "/Defect/", {"playdeviceFid": 123, "priority": 1})
        self.assertEqual(status, 200)
        self.assertNotIn("tid", result)
        self.assertEqual(self.db.calls, [])

    def test_priority_two_requires_responsible_body_and_user(self):
        status, result = self.request("PUT", "/Defect/", {
            "playdeviceFid": 123, "priority": 2, "defectDescription": "Gefahr",
            "defectsResponsibleBodyId": -1, "responsibleUserFid": -1,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["errorMessage"], "SPK-10")
        self.assertEqual(self.db.calls, [])

    def test_database_failure_returns_existing_error_contract(self):
        self.db.fail = True
        status, result = self.request("PUT", "/Defect/", {
            "playdeviceFid": 123, "priority": 1, "defectDescription": "Test",
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["errorMessage"], "SPK-3")
        self.assertNotIn("tid", result)

    def test_existing_tid_is_not_used_as_proposed_new_transfer_id(self):
        status, result = self.request("PUT", "/Defect/", {
            "tid": 7, "fid": 999, "playdeviceFid": 123,
            "priority": 1, "defectDescription": "Test",
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["tid"], 87001)
        self.assertEqual(len(self.db.calls), 2)
        # The API echoes the request body (including extra fields) for compatibility.
        # Only the INSERT columns and DB-returned TID determine actual persistence.
        self.assertEqual(result["fid"], 999)
        self.assertNotIn(999, self.db.calls[1][1])
        self.assertNotIn(7, self.db.calls[1][1])


if __name__ == "__main__":
    unittest.main()
