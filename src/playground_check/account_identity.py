"""One implementation of cookie/JWT identity and persistent session validation.

Connection providers and application configuration are explicit; adapters own
HTTP dispatch. This preserves the existing authentication and cookie policies.
"""
from http.cookies import SimpleCookie
from typing import Any, Mapping
from .auth import EMAIL, GIVEN_NAME, NAME, ROLE, decode_token
from . import session_repository, user_repository
from .domain_values import _bool, UNAUTHORIZED
from .http import Request, Response


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
        "uiLanguage": row.get("ui_language"),
    }


def _request_token(request: Request, *, config) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raw_cookie = request.headers.get("Cookie", "")
    if raw_cookie:
        try:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get(config.auth_cookie_name)
            if morsel:
                return morsel.value
        except Exception:
            pass
    return ""


def _auth_cookie(token: str, *, config, clear: bool = False) -> tuple[str, str]:
    path = config.base_path or "/"
    parts = [f"{config.auth_cookie_name}={token}", f"Path={path}", "HttpOnly", "SameSite=Strict"]
    if config.token_issuer.lower().startswith("https://"):
        parts.append("Secure")
    if clear:
        parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"] )
    else:
        parts.append("Max-Age=28800")
    return ("Set-Cookie", "; ".join(parts))


def token_user(request: Request, role: str | None = None, *, config) -> dict[str, Any] | None:
    token = _request_token(request, config=config)
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


def current_user(request: Request, role: str | None = None, dry_run: bool = False, *, connect_db, config) -> dict[str, Any] | None:
    # The original getAuthorizedUser deliberately returns null for dry runs.
    if dry_run:
        return None
    claimed = token_user(request, role, config=config)
    if not claimed:
        return None
    with connect_db() as db:
        row = user_repository.user_by_email(db, claimed["mailAddress"])
        claims = decode_token(_request_token(request, config=config))
        if (not row or not row["active"] or not claims
                or not session_repository.is_active(db, claims["jti"], row["fid"])):
            return None
    user = _user_dict(row)
    if role and user["role"] != role:
        return None
    return user


def require_user(request: Request, role: str | None = None, *, resolve_user) -> tuple[dict[str, Any] | None, Response | None]:
    user = resolve_user(request, role, _bool(request.query.get("dryRun")))
    return (user, None) if user else (None, Response.text(UNAUTHORIZED, 401))


def revoke_request_session(request: Request, *, connect_db, config) -> None:
    """Idempotent logout of the supplied signed token, including stale accounts."""
    claims = decode_token(_request_token(request, config=config))
    if claims is not None:
        with connect_db() as db:
            session_repository.revoke_session(db, claims["jti"])
