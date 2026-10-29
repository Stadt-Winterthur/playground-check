"""Native DRF account reads while preserving the established wire contracts.

Authentication is revalidated through the existing account model. These views
call repositories directly, never routing through the old HTTP service handler.
The login, password-change and admin write paths stay unchanged for now.
"""
from __future__ import annotations

from playground_check import service
from playground_check.http import Response
from .api_wire import to_http_response, to_legacy_request


def _authorized(request, role=None):
    user, error = service.require_user(to_legacy_request(request), role)
    return user, to_http_response(error) if error is not None else None


def current_account(request):
    user, denied = _authorized(request)
    if denied is not None:
        return denied
    return to_http_response(Response.json(user))


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


def assignable_users(request):
    _, denied = _authorized(request)
    if denied is not None:
        return denied
    with service.connect() as db:
        rows = service.user_repository.assignable_users(db)
    return to_http_response(Response.json([service._user_dict(row) for row in rows]))


def logout():
    response = Response(b"", 204, "application/json; charset=utf-8")
    response.headers.append(service._auth_cookie("", clear=True))
    return to_http_response(response)
