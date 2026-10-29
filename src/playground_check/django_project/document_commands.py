"""Document operations backed by the existing PostgreSQL repositories.

Preserves the legacy authentication, validation, binary response, and
PostgreSQL-side document FID allocation contracts without legacy HTTP dispatch.
"""
from __future__ import annotations

import base64
import binascii

from playground_check import service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request


def _authorized(request, role=None, **params):
    legacy = to_legacy_request(request, **params)
    _, error = service.require_user(legacy, role)
    return legacy, to_http_response(error) if error is not None else None


def get_document(request, fid: int):
    legacy, denied = _authorized(request, fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    if not storage:
        return to_http_response(Response(b"", 400))
    table, column = storage
    try:
        with service.connect() as db:
            row = service.remaining_reads_repository.document_blob(db, table, column, fid)
        if not row:
            return to_http_response(Response(b"", 400))
        content, _ = service._document_parts(row["content"])
        return to_http_response(Response.file(content, "application/pdf"))
    except Exception:
        return to_http_response(Response(b"", 400))


def create_document(request):
    legacy, denied = _authorized(request, "administrator")
    if denied is not None:
        return denied
    body = legacy.json() or {}
    storage = service._document_storage(str(body.get("type") or "").strip().lower())
    name = str(body.get("name") or "").strip()
    try:
        playground_id = int(body.get("playgroundId"))
        content = base64.b64decode(str(body.get("contentBase64") or ""), validate=True)
    except (TypeError, ValueError, binascii.Error):
        return to_http_response(Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400))
    if not storage or playground_id <= 0 or not name or len(name) > 255:
        return to_http_response(Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400))
    if len(content) > service.DOCUMENT_MAX_BYTES or not content.startswith(b"%PDF-"):
        return to_http_response(Response.json({"errorMessage": "Es sind nur PDF-Dokumente bis 20 MB zulässig."}, 400))
    table, column = storage
    try:
        with service.connect() as db:
            fid = service.document_write_repository.insert_document(
                db, table, column, playground_id, service._document_with_name(content, name)
            )
        return to_http_response(Response.json({"fid": fid, "name": name}))
    except Exception:
        return to_http_response(Response.json({"errorMessage": "Dokument konnte nicht gespeichert werden."}, 400))


def rename_document(request, fid: int):
    legacy, denied = _authorized(request, "administrator", fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    body = legacy.json() or {}
    name = str(body.get("name") or "").strip()
    if not storage or not name or len(name) > 255:
        return to_http_response(Response.json({"errorMessage": "Ungültiger Dokumentname."}, 400))
    table, column = storage
    try:
        with service.connect() as db:
            row = service.document_write_repository.document_content(db, table, column, fid)
            if not row or not row.get("content"):
                return to_http_response(Response.json({"errorMessage": "Dokument nicht gefunden."}, 404))
            service.document_write_repository.rename_document(
                db, table, column, fid, service._document_with_name(row["content"], name)
            )
        return to_http_response(Response.json({"fid": fid, "name": name}))
    except Exception:
        return to_http_response(Response.json({"errorMessage": "Dokumentname konnte nicht gespeichert werden."}, 400))


def delete_document(request, fid: int):
    legacy, denied = _authorized(request, "administrator", fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    if not storage:
        return to_http_response(Response.json({"errorMessage": "Ungültiger Dokumenttyp."}, 400))
    table, _ = storage
    try:
        with service.connect() as db:
            row = service.document_write_repository.delete_document(db, table, fid)
            if not row:
                return to_http_response(Response.json({"errorMessage": "Dokument nicht gefunden."}, 404))
        return to_http_response(Response.json({"fid": fid}))
    except Exception:
        return to_http_response(Response.json({"errorMessage": "Dokument konnte nicht gelöscht werden."}, 400))
