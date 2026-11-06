"""Native account queries backed by shared identity and repository functions.

Historical wire formats remain supported without invoking old HTTP handlers."""
from __future__ import annotations

from playground_check import domain_support as service
from playground_check.http import Response
from .operation_errors import operation_errors
from .api_wire import to_http_response, to_legacy_request


def _authorized(request, role=None):
    user, error = service.require_user(to_legacy_request(request), role)
    return user, to_http_response(error) if error is not None else None


@operation_errors()
def current_account(request):
    user, denied = _authorized(request)
    if denied is not None:
        return denied
    return to_http_response(Response.json(user))


@operation_errors()
def list_users(request):
    _, denied = _authorized(request, "administrator")
    if denied is not None:
        return denied
    email = request.query_params.get("email", "").strip().lower()
    with service.connect() as db:
        rows = service.user_repository.users(db, email)
    return to_http_response(Response.json([
        service._user_dict(row) for row in rows if row.get("email")
    ]))


@operation_errors()
def assignable_users(request):
    _, denied = _authorized(request)
    if denied is not None:
        return denied
    with service.connect() as db:
        rows = service.user_repository.assignable_users(db)
    return to_http_response(Response.json([service._user_dict(row) for row in rows]))


@operation_errors(lambda: to_http_response(Response.text("Abmeldung derzeit nicht möglich. Bitte erneut versuchen.")))
def logout(request):
    # Do not clear the browser credential until revocation has committed.
    # Return an explicit failure if persistent revocation is unavailable.
    service.revoke_request_session(to_legacy_request(request))
    response = Response(b"", 204, "application/json; charset=utf-8")
    response.headers.append(("Cache-Control", "no-store"))
    response.headers.append(service._auth_cookie("", clear=True))
    return to_http_response(response)
