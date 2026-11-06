"""Shared legacy PDF filename metadata format and whitelisted document storage."""
import base64
import binascii

DOCUMENT_NAME_MARKER = b"\n%PLAYGROUND-CHECK-FILENAME:"


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


def _document_name_from_tail(value: bytes | bytearray | memoryview | None, fallback: str) -> str:
    _, name = _document_parts(value)
    return name or fallback


def _document_storage(kind: str) -> tuple[str, str] | None:
    if kind == "abnahme":
        return "wgr_sp_abnahmen", "abnahmedokument"
    if kind == "zertifikat":
        return "wgr_sp_zertifikat", "zertifikatsdokument"
    return None
