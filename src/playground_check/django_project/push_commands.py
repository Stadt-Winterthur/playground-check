"""Push subscription operations using the existing identity and SQL repositories."""
from __future__ import annotations

from playground_check import domain_support as service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request


def _authorized(request):
    legacy = to_legacy_request(request)
    user, error = service.require_user(legacy)
    return legacy, user, to_http_response(error) if error is not None else None


def register(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = legacy.json() or {}
    try:
        endpoint = body["endpoint"].strip()
        p256dh = body["p256dh"].strip()
        auth = body["auth"].strip()
        if not endpoint or not p256dh or not auth:
            raise ValueError("Incomplete subscription")
        with service.connect() as db:
            service.push_repository.register_subscription(
                db, user["fid"], endpoint, p256dh, auth,
                (body.get("userAgent") or legacy.headers.get("User-Agent", "")).strip() or None,
            )
        return to_http_response(Response.json({"errorMessage": ""}))
    except Exception:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))


def unregister(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = legacy.json() or {}
    try:
        endpoint = (body.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("Missing endpoint")
        with service.connect() as db:
            service.push_repository.unregister_subscription(db, user["fid"], endpoint)
        return to_http_response(Response.json({"errorMessage": ""}))
    except Exception:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}))


def subscriptions(request):
    _, user, denied = _authorized(request)
    if denied is not None:
        return denied
    with service.connect() as db:
        rows = service.push_repository.active_subscriptions(db, user["fid"])
    return to_http_response(Response.json([{
        "endpoint": row["endpoint"], "p256dh": row["p256dh"],
        "auth": row["auth"], "userAgent": row["user_agent"],
    } for row in rows]))
