"""Reusable domain helpers for native DRF commands.

Functions are extracted unchanged from the historical service implementation.
Legacy HTTP handlers remain separate for compatibility tests.
"""
from __future__ import annotations
import base64
import binascii
from datetime import date, datetime
from email.errors import HeaderParseError
from email.headerregistry import Address
from http.cookies import SimpleCookie
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import urlopen
from psycopg import Connection
from playground_check.auth import EMAIL, GIVEN_NAME, NAME, ROLE, decode_token, hash_passphrase, issue_token, verify_passphrase
from playground_check.config import settings
from playground_check.db import connect
from playground_check import remaining_reads_repository
from playground_check import user_repository, user_write_repository, document_write_repository, push_repository, assignment_repository, mail_repository, inspection_validation_repository
from playground_check import playground_repository, inspection_defect_repository, playground_detail_service, inspection_defect_service, defect_write_rules, defect_write_repository, inspection_write_repository, picture_write_repository, playdevice_write_repository
from playground_check.http import Request, Response
from playground_check.playground_reads import inspection_suspended as _suspended, public_feature as _public_feature
from playground_check.map_image_queries import map_image_base64
from playground_check.playground_detail_serializers import (
    report_dict as _report_dict,
    criterion_dict as _criterion_dict,
    playdevice_feature,
)


UNAUTHORIZED = "Sie sind entweder nicht als Kontrolleur in der Spielplatzkontrolle-Datenbank erfasst oder Sie haben keine Zugriffsberechtigung."


VALID_ROLES = {"administrator", "inspector", "maintenance"}


DOCUMENT_NAME_MARKER = b"\n%PLAYGROUND-CHECK-FILENAME:"


DOCUMENT_MAX_BYTES = 20 * 1024 * 1024


IMAGE_MAX_BYTES = 10 * 1024 * 1024


IMAGE_REQUEST_MAX_BYTES = 25 * 1024 * 1024


ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _document_parts(value: bytes | bytearray | memoryview | None) -> tuple[bytes, str]:
    data = bytes(value or b"")
    index = data.rfind(DOCUMENT_NAME_MARKER)
    if index < 0:
        return data, ""
    encoded = data[index + len(DOCUMENT_NAME_MARKER):].splitlines()[0].strip()
    try:
        name = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return data, ""
    return data[:index], name


def _document_with_name(value: bytes, name: str) -> bytes:
    content, _ = _document_parts(value)
    encoded = base64.urlsafe_b64encode(name.strip().encode("utf-8")).rstrip(b"=")
    return content + DOCUMENT_NAME_MARKER + encoded + b"\n"


def _document_storage(kind: str) -> tuple[str, str] | None:
    if kind == "abnahme":
        return "wgr_sp_abnahmen", "abnahmedokument"
    if kind == "zertifikat":
        return "wgr_sp_zertifikat", "zertifikatsdokument"
    return None


VALID_RESPONSIBILITIES = {
    "Revier Mitte", "Revier Süd", "Revier West", "Revier Ost", "Dispo",
    "Revier", "Spielplatzverantwortlicher", "Projektleiter",
}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _date_value(value: Any) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return date.fromisoformat(text[:10])


def _user_dict(row: Mapping[str, Any], include_password: bool = False) -> dict[str, Any]:
    return {
        "fid": row.get("fid", -1),
        "lastName": (row.get("last_name") or "").strip(),
        "firstName": (row.get("first_name") or "").strip(),
        "mailAddress": (row.get("email") or "").strip().lower(),
        "passPhrase": row.get("pwd", "") if include_password else "",
        "active": bool(row.get("active")),
        "role": row.get("role") or "",
        "responsibility": row.get("responsibility") or "",
        "errorMessage": "",
        "isNew": bool(row.get("is_new")),
    }


def _request_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raw_cookie = request.headers.get("Cookie", "")
    if raw_cookie:
        try:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get(settings.auth_cookie_name)
            if morsel:
                return morsel.value
        except Exception:
            pass
    return ""


def _auth_cookie(token: str, *, clear: bool = False) -> tuple[str, str]:
    path = settings.base_path or "/"
    parts = [f"{settings.auth_cookie_name}={token}", f"Path={path}", "HttpOnly", "SameSite=Strict"]
    if settings.token_issuer.lower().startswith("https://"):
        parts.append("Secure")
    if clear:
        parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"] )
    else:
        parts.append("Max-Age=28800")
    return ("Set-Cookie", "; ".join(parts))


def token_user(request: Request, role: str | None = None) -> dict[str, Any] | None:
    token = _request_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    result = {
        "fid": -1,
        "mailAddress": str(payload.get(EMAIL, "")).strip().lower(),
        "firstName": str(payload.get(GIVEN_NAME, "")),
        "lastName": str(payload.get(NAME, "")),
        "role": str(payload.get(ROLE, "")),
        "active": True,
    }
    if not result["mailAddress"] or (role and result["role"] != role):
        return None
    return result


def current_user(request: Request, role: str | None = None, dry_run: bool = False) -> dict[str, Any] | None:
    # The original getAuthorizedUser deliberately returns null for dry runs.
    if dry_run:
        return None
    claimed = token_user(request, role)
    if not claimed:
        return None
    with connect() as db:
        row = user_repository.user_by_email(db, claimed["mailAddress"])
    if not row or not row["active"]:
        return None
    user = _user_dict(row)
    if role and user["role"] != role:
        return None
    return user


def require_user(request: Request, role: str | None = None) -> tuple[dict[str, Any] | None, Response | None]:
    user = current_user(request, role, _bool(request.query.get("dryRun")))
    return (user, None) if user else (None, Response.text(UNAUTHORIZED, 401))


def _valid_mail_address(value: str) -> bool:
    try:
        parsed = Address(addr_spec=value)
    except (TypeError, ValueError, HeaderParseError, IndexError):
        return False
    return parsed.addr_spec == value


def _user_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = assignment_repository.user_name_row(db, fid)
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _record_assignment_change(
    db: Connection, defect_tid: int, changed_by: Mapping[str, Any], previous_fid: Any, new_fid: Any
) -> None:
    previous = int(previous_fid) if previous_fid else None
    new = int(new_fid) if new_fid else None
    if previous == new:
        return
    changed_by_name = f"{changed_by.get('firstName') or ''} {changed_by.get('lastName') or ''}".strip()
    assignment_repository.record_assignment_change(
        db, defect_tid, changed_by.get("fid"), changed_by_name or None,
        previous, _user_name(db, previous) or None, new, _user_name(db, new) or None,
    )


def _assignment_history(db: Connection, defect_tid: int) -> list[dict[str, Any]]:
    rows = assignment_repository.assignment_history_rows(db, defect_tid)
    return [{
        "id": row.get("id"),
        "changedAt": row.get("changed_at"),
        "changedByFid": row.get("changed_by_fid") or -1,
        "changedByName": row.get("changed_by_name") or "",
        "previousUserFid": row.get("previous_fid") or -1,
        "previousUserName": row.get("previous_name") or "",
        "newUserFid": row.get("new_fid") or -1,
        "newUserName": row.get("new_name") or "",
    } for row in rows]


def _defect_creator_name(db: Connection, fid: Any) -> str:
    if not fid:
        return ""
    row = remaining_reads_repository.defect_creator_row(db, fid)
    if not row:
        return ""
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _defect_dict(db: Connection, row: Mapping[str, Any], pictures: bool = True) -> dict[str, Any]:
    picture_rows = (
        remaining_reads_repository.defect_picture_rows(db, row["tid"])
        if pictures else []
    )
    return inspection_defect_service.defect_payload(
        row,
        picture_rows=picture_rows,
        done_by_name=_defect_creator_name(db, row.get("done_by")),
        created_by_name=_defect_creator_name(db, row.get("created_by_fid")),
        assignment_history=_assignment_history(db, int(row["tid"])),
    )


_priority_two_fields_complete = defect_write_rules.priority_two_fields_complete


def _decode_image(value: bytes | str | None) -> tuple[bytes | None, str | None]:
    if value is None:
        return None, None
    raw = value if isinstance(value, bytes) else value.encode()
    printable = bool(raw) and all(32 <= byte <= 126 or byte in (9, 10, 13) for byte in raw[:128])
    if printable:
        text = raw.decode("utf-8", "replace").strip()
        if len(text) >= 16 and len(text) % 2 == 0 and all(char in "0123456789abcdefABCDEF" for char in text):
            try:
                text = bytes.fromhex(text).decode("utf-8").strip()
            except Exception:
                pass
        mime = None
        if text.lower().startswith("data:") and "," in text:
            meta, text = text.split(",", 1)
            mime = meta[5:].split(";", 1)[0]
        try:
            raw = base64.b64decode(text.replace(" ", "+") + "=" * (-len(text) % 4), validate=False)
        except (ValueError, binascii.Error):
            return None, None
        return raw, mime or _mime(raw)
    return raw, _mime(raw)


def _mime(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _image_upload_error(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "Bilddaten fehlen."
    text = value.strip()
    declared_mime = None
    if text.lower().startswith("data:") and "," in text:
        meta, text = text.split(",", 1)
        declared_mime = meta[5:].split(";", 1)[0].lower()
        if ";base64" not in meta.lower():
            return "Bilddaten müssen Base64-kodiert sein."
    try:
        raw = base64.b64decode(text.replace(" ", "+") + "=" * (-len(text) % 4), validate=True)
    except (ValueError, binascii.Error):
        return "Bilddaten sind nicht gültig Base64-kodiert."
    if len(raw) > IMAGE_MAX_BYTES:
        return "Bild ist zu gross (maximal 10 MB)."
    mime = _mime(raw)
    if mime not in ALLOWED_IMAGE_MIME_TYPES:
        return "Nicht unterstützter Bildtyp."
    if declared_mime and declared_mime != mime:
        return "Angegebener Bildtyp stimmt nicht mit den Bilddaten überein."
    return None


def _image_request_too_large(request: Request) -> bool:
    try:
        return int(request.environ.get("CONTENT_LENGTH") or 0) > IMAGE_REQUEST_MAX_BYTES
    except (TypeError, ValueError):
        return False

