"""DRF endpoints for accounts, documents and push subscriptions.

Authorization, SQL transactions, ID allocation and wire response contracts
remain owned by the established service functions during the transition.
"""
from __future__ import annotations

from rest_framework.decorators import api_view, authentication_classes, permission_classes

from playground_check import service
from .legacy_adapter import dispatch


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def login(request):
    return dispatch(request, service.login)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def logout(request):
    return dispatch(request, service.logout)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def account_me(request):
    return dispatch(request, service.get_current_account)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def assignable_users(request):
    return dispatch(request, service.get_assignable_users)


@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([])
@permission_classes([])
def users(request):
    handlers = {
        "GET": service.get_users,
        "PUT": service.update_user,
        "DELETE": service.delete_user,
    }
    return dispatch(request, handlers[request.method])


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def document_create(request):
    return dispatch(request, service.post_document)


@api_view(["GET", "DELETE"])
@authentication_classes([])
@permission_classes([])
def document_item(request, fid: int):
    handler = service.get_document if request.method == "GET" else service.delete_document
    return dispatch(request, handler, fid=fid)


@api_view(["PUT"])
@authentication_classes([])
@permission_classes([])
def document_rename(request, fid: int):
    return dispatch(request, service.rename_document, fid=fid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def push_register(request):
    return dispatch(request, service.push_register)


@api_view(["DELETE"])
@authentication_classes([])
@permission_classes([])
def push_unregister(request):
    return dispatch(request, service.push_unregister)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def push_me(request):
    return dispatch(request, service.push_me)
