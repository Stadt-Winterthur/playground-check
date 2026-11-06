"""Push subscription operations using the existing identity and SQL repositories."""
from __future__ import annotations

from playground_check import domain_support as service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request
from .api_input import object_body
from .operation_errors import operation_errors


def _authorized(request):
    legacy = to_legacy_request(request)
    user, error = service.require_user(legacy)
    return legacy, user, to_http_response(error) if error is not None else None


@operation_errors()
def register(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = object_body(legacy, strings=('endpoint', 'p256dh', 'auth', 'userAgent'))
    endpoint = (body.get("endpoint") or "").strip()
    p256dh = (body.get("p256dh") or "").strip()
    auth = (body.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}, 400))
    with service.connect() as db:
        service.push_repository.register_subscription(
            db, user["fid"], endpoint, p256dh, auth,
            (body.get("userAgent") or legacy.headers.get("User-Agent", "")).strip() or None,
        )
    return to_http_response(Response.json({"errorMessage": ""}))


@operation_errors()
def unregister(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = object_body(legacy, strings=('endpoint',))
    endpoint = (body.get("endpoint") or "").strip()
    if not endpoint:
        return to_http_response(Response.json({"errorMessage": "SPK-3"}, 400))
    with service.connect() as db:
        service.push_repository.unregister_subscription(db, user["fid"], endpoint)
    return to_http_response(Response.json({"errorMessage": ""}))


@operation_errors()
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
