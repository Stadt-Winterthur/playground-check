"""DRF endpoints for accounts, documents and push subscriptions.

Authorization, SQL transactions, ID allocation and wire response contracts
remain owned by the established service functions during the transition.
"""
from __future__ import annotations

from rest_framework.decorators import api_view, authentication_classes, permission_classes

from . import account_queries, account_commands, document_commands, push_commands


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def login(request):
    return account_commands.login(request)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def logout(request):
    return account_queries.logout()


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def account_me(request):
    return account_queries.current_account(request)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def assignable_users(request):
    return account_queries.assignable_users(request)


@api_view(["GET", "PUT", "DELETE"])
@authentication_classes([])
@permission_classes([])
def users(request):
    if request.method == "GET":
        return account_queries.list_users(request)
    if request.method == "PUT":
        return account_commands.update_user(request)
    return account_commands.delete_user(request)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def document_create(request):
    return document_commands.create_document(request)


@api_view(["GET", "DELETE"])
@authentication_classes([])
@permission_classes([])
def document_item(request, fid: int):
    if request.method == "GET":
        return document_commands.get_document(request, fid)
    return document_commands.delete_document(request, fid)


@api_view(["PUT"])
@authentication_classes([])
@permission_classes([])
def document_rename(request, fid: int):
    return document_commands.rename_document(request, fid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def push_register(request):
    return push_commands.register(request)


@api_view(["DELETE"])
@authentication_classes([])
@permission_classes([])
def push_unregister(request):
    return push_commands.unregister(request)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def push_me(request):
    return push_commands.subscriptions(request)
