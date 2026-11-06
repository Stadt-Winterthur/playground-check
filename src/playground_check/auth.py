from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import settings

EMAIL = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
GIVEN_NAME = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
NAME = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
ROLE = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"


def hash_passphrase(passphrase: str, email: str | None = None) -> str:
    salt = settings.salt
    iterations = 100_000
    if email:
        salt = hmac.new(settings.salt, email.strip().lower().encode("utf-8"), hashlib.sha256).digest()
        iterations = 600_000
    value = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, 32)
    return base64.b64encode(value).decode("ascii")


def verify_passphrase(stored_hash: str, passphrase: str, email: str) -> tuple[bool, bool]:
    current = hash_passphrase(passphrase, email)
    if hmac.compare_digest(stored_hash or "", current):
        return True, False
    legacy = hash_passphrase(passphrase)
    if hmac.compare_digest(stored_hash or "", legacy):
        return True, True
    return False, False


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    # Compatibility note: the original service does not emit the fid claim even though
    # the Angular client attempts to read it. That observable quirk is preserved.
    payload = {
        EMAIL: user["mailAddress"],
        GIVEN_NAME: user["firstName"],
        NAME: user["lastName"],
        ROLE: user["role"],
        "iss": settings.token_issuer,
        "aud": settings.token_issuer,
        "jti": uuid.uuid4().hex,
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    unsigned = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(settings.security_key.encode(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{_b64url(signature)}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        head, body, signature = token.split(".")
        header = json.loads(_unb64url(head))
        if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
            return None
        unsigned = f"{head}.{body}"
        expected = hmac.new(settings.security_key.encode(), unsigned.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64url(signature)):
            return None
        payload = json.loads(_unb64url(body))
        # Pre-F02 stateless tokens intentionally require a fresh login.
        if not isinstance(payload, dict) or not isinstance(payload.get("jti"), str):
            return None
        if re.fullmatch(r"[0-9a-f]{32}", payload["jti"]) is None:
            return None
        now = int(time.time())
        if int(payload.get("exp", 0)) <= now or int(payload.get("nbf", 0)) > now:
            return None
        if payload.get("iss") != settings.token_issuer or payload.get("aud") != settings.token_issuer:
            return None
        return payload
    except Exception:
        return None
