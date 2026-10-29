"""Native DRF account commands using the existing domain repositories.

The legacy Request/Response *formats* are retained at the HTTP boundary, but
these commands do not dispatch through service.login/update_user/delete_user.
Keep the legacy-specific security behavior until it can be replaced with a
separately versioned domain API.
"""
from __future__ import annotations

from playground_check import service
from playground_check.http import Response
from .legacy_adapter import to_http_response, to_legacy_request


def login(request):
    legacy = to_legacy_request(request)
    body = legacy.json()
    if not isinstance(body, dict) or body.get("mailAddress") is None:
        return to_http_response(Response.text("Keine oder falsche Login-Daten.", 400))
    email = str(body.get("mailAddress", "")).lower().strip()
    password = body.get("passPhrase")
    if (
        not email or any(char.isspace() for char in email)
        or not service._valid_mail_address(email)
        or not isinstance(password, str) or not password.strip()
    ):
        return to_http_response(Response.text("Keine oder falsche Login-Daten.", 400))
    dry_run = service._bool(legacy.query.get("dryRun"))
    try:
        with service.connect() as db:
            row = None if dry_run else service.user_repository.user_by_email(db, email)
            if row:
                if row.get("last_login_attempt") is not None:
                    elapsed = (row["database_time"] - row["last_login_attempt"]).total_seconds()
                    if elapsed < 3:
                        response = Response.text("Zu viele Login-Versuche. Bitte versuchen Sie es in Kürze erneut.", 429)
                        response.headers.append(("Retry-After", str(max(1, 3 - int(elapsed)))))
                        return to_http_response(response)
                service.user_write_repository.record_login_attempt(db, email)
                password_ok, needs_upgrade = service.verify_passphrase(row.get("pwd") or "", password, email)
                if password_ok and row.get("active"):
                    if needs_upgrade:
                        service.user_write_repository.update_password(
                            db, email, service.hash_passphrase(password, email)
                        )
                    user = service._user_dict(row)
                    user["lastName"] = user["lastName"] or "Nachname unbekannt"
                    user["firstName"] = user["firstName"] or "Vorname unbekannt"
                    token = service.issue_token(user)
                    response = Response.json({"securityTokenString": token, "user": user})
                    response.headers.append(service._auth_cookie(token))
                    return to_http_response(response)
                return to_http_response(Response.text("Keine oder falsche Login-Daten.", 401))
            # Preserve legacy dryRun behavior until changed deliberately.
            service.user_write_repository.register_pending_user(
                db, body.get("lastName") or "", body.get("firstName") or "", email,
                service.hash_passphrase(password, email),
            )
        return to_http_response(Response.text(
            service.UNAUTHORIZED + "Der Administrator wird informiert und wird Ihnen gegebenenfalls den Zugriff gewähren.", 401
        ))
    except Exception:
        return to_http_response(Response.text(
            "Ein kritischer Fehler ist aufgetreten. Bitte kontaktieren Sie den Administrator.", 400
        ))


def update_user(request):
    legacy = to_legacy_request(request)
    _, error = service.require_user(legacy, "administrator")
    if error is not None:
        return to_http_response(error)
    body = legacy.json()
    if not isinstance(body, dict):
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))
    password = str(body.get("passPhrase") or "")
    body["passPhrase"] = ""
    email = str(body.get("mailAddress") or "").strip().lower()
    if not email or "@" not in email:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))
    role = str(body.get("role") or "").strip()
    responsibility = str(body.get("responsibility") or "").strip()
    if role not in service.VALID_ROLES or (responsibility and responsibility not in service.VALID_RESPONSIBILITIES):
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))
    change_passphrase = service._bool(legacy.query.get("changePassphrase"))
    try:
        with service.connect() as db:
            existing = service.user_repository.users_by_email(db, email)
            if len(existing) != 1:
                return to_http_response(Response.json({"errorMessage": "SPK-3"}))
            active_admins = service.user_write_repository.active_admin_count(db)
            old = existing[0]
            if old["role"] == "administrator" and active_admins == 1:
                if body.get("role") != "administrator" or not service._bool(body.get("active")):
                    return to_http_response(Response.json({"errorMessage": "SPK-3"}))
            affected = service.user_write_repository.update_user(
                db, email, body.get("lastName") or "", body.get("firstName") or "",
                role, responsibility or None, service._bool(body.get("active")), service._bool(body.get("isNew")),
            )
            password_affected = 0
            if change_passphrase:
                password = password.strip()
                if len(password) < 8:
                    return to_http_response(Response.json({"errorMessage": "SPK-9"}))
                password_affected = service.user_write_repository.update_password(
                    db, email, service.hash_passphrase(password, email)
                )
            if affected == 1 and (not change_passphrase or password_affected == 1):
                body.setdefault("errorMessage", "")
                return to_http_response(Response.json(body))
    except Exception:
        pass
    return to_http_response(Response.json({"errorMessage": "SPK-3"}))


def delete_user(request):
    legacy = to_legacy_request(request)
    _, error = service.require_user(legacy, "administrator")
    if error is not None:
        return to_http_response(error)
    email = legacy.query.get("email", "").strip().lower()
    if not email:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))
    with service.connect() as db:
        users = service.user_repository.users_by_email(db, email)
        if len(users) != 1:
            return to_http_response(Response.json({"errorMessage": "SPK-3"}))
        count = service.user_write_repository.active_admin_count(db)
        if users[0]["role"] == "administrator" and count == 1:
            return to_http_response(Response.json({"errorMessage": "SPK-3"}))
        if service.user_write_repository.deactivate_user(db, email) == 1:
            return to_http_response(Response(b"", 200, "application/json; charset=utf-8"))
    return to_http_response(Response.json({"errorMessage": "SPK-3"}))
