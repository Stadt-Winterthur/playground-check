"""Shared image decoding, signature checks and byte-based upload limits."""
import base64
import binascii
from typing import Any
from .http import Request
from .upload_limits import IMAGE_MAX_BYTES, IMAGE_REQUEST_MAX_BYTES

ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


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
        return "Bild ist zu gross (maximal 10 MiB)."
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
