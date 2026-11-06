"""Document operations backed by the existing PostgreSQL repositories.

Preserves the legacy authentication, validation, binary response, and
PostgreSQL-side document FID allocation contracts without legacy HTTP dispatch.
"""
from __future__ import annotations

import base64
import binascii

from playground_check import domain_support as service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request
from .operation_errors import operation_errors
from .api_input import object_body, mapping
from .uploads import is_multipart, multipart_parts, pdf_file, UploadTooLarge


def _authorized(request, role=None, *, read_body=True, **params):
    legacy = to_legacy_request(request, read_body=read_body, **params)
    _, error = service.require_user(legacy, role)
    return legacy, to_http_response(error) if error is not None else None


@operation_errors(lambda: to_http_response(Response(b"", 500)))
def get_document(request, fid: int):
    legacy, denied = _authorized(request, fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    if not storage:
        return to_http_response(Response(b"", 400))
    table, column = storage
    with service.connect() as db:
        row = service.remaining_reads_repository.document_blob(db, table, column, fid)
    if not row:
        return to_http_response(Response(b"", 400))
    content, _ = service._document_parts(row["content"])
    return to_http_response(Response.file(content, "application/pdf"))


@operation_errors(lambda: to_http_response(Response.json({"errorMessage": "Dokument konnte nicht gespeichert werden."})))
def create_document(request):
    multipart = is_multipart(request)
    legacy, denied = _authorized(request, "administrator", read_body=not multipart)
    if denied is not None:
        return denied
    if multipart:
        body, files = multipart_parts(request, {'document'})
        mapping(body, strings=('type', 'name'), integers=('playgroundId',))
    else:
        body = object_body(legacy, strings=('type', 'name', 'contentBase64'), integers=('playgroundId',))
    storage = service._document_storage(str(body.get("type") or "").strip().lower())
    name = str(body.get("name") or "").strip()
    try:
        playground_id = int(body.get("playgroundId"))
    except (TypeError, ValueError):
        return to_http_response(Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400))
    if not storage or playground_id <= 0 or not name or len(name) > 255:
        return to_http_response(Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400))
    if multipart:
        content = pdf_file(files.get('document'))
    else:
        encoded = body.get('contentBase64') or ''
        if len(encoded) > 4 * ((service.DOCUMENT_MAX_BYTES + 2) // 3):
            raise UploadTooLarge()
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return to_http_response(Response.json({"errorMessage": "Ungültige Dokumentdaten."}, 400))
        if len(content) > service.DOCUMENT_MAX_BYTES:
            raise UploadTooLarge()
        if not content.startswith(b'%PDF-'):
            return to_http_response(Response.json({"errorMessage": "Nur PDF-Dateien erlaubt."}, 400))
    table, column = storage
    with service.connect() as db:
        fid = service.document_write_repository.insert_document(
            db, table, column, playground_id, service._document_with_name(content, name)
        )
    return to_http_response(Response.json({"fid": fid, "name": name}))


@operation_errors(lambda: to_http_response(Response.json({"errorMessage": "Dokumentname konnte nicht gespeichert werden."})))
def rename_document(request, fid: int):
    legacy, denied = _authorized(request, "administrator", fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    body = object_body(legacy, strings=('name',))
    name = str(body.get("name") or "").strip()
    if not storage or not name or len(name) > 255:
        return to_http_response(Response.json({"errorMessage": "Ungültiger Dokumentname."}, 400))
    table, column = storage
    with service.connect() as db:
        row = service.document_write_repository.document_content(db, table, column, fid)
        if not row or not row.get("content"):
            return to_http_response(Response.json({"errorMessage": "Dokument nicht gefunden."}, 404))
        service.document_write_repository.rename_document(
            db, table, column, fid, service._document_with_name(row["content"], name)
        )
    return to_http_response(Response.json({"fid": fid, "name": name}))


@operation_errors(lambda: to_http_response(Response.json({"errorMessage": "Dokument konnte nicht gelöscht werden."})))
def delete_document(request, fid: int):
    legacy, denied = _authorized(request, "administrator", fid=fid)
    if denied is not None:
        return denied
    storage = service._document_storage(legacy.query.get("type", "").strip().lower())
    if not storage:
        return to_http_response(Response.json({"errorMessage": "Ungültiger Dokumenttyp."}, 400))
    table, _ = storage
    with service.connect() as db:
        row = service.document_write_repository.delete_document(db, table, fid)
        if not row:
            return to_http_response(Response.json({"errorMessage": "Dokument nicht gefunden."}, 404))
    return to_http_response(Response.json({"fid": fid}))
