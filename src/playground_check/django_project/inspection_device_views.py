"""DRF routing for inspection creation and playdevice/picture operations.

The legacy service remains responsible for authorization, validation, SQL
transactions and binary/JSON response contracts during this migration.
"""
from __future__ import annotations

from .defect_views import _dispatch
from playground_check import service
from rest_framework.decorators import api_view, authentication_classes, permission_classes


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def create_inspection(request):
    return _dispatch(request, service.post_inspections)


@api_view(["POST", "PUT"])
@authentication_classes([])
@permission_classes([])
def playdevice(request):
    handler = service.save_playdevice if request.method == "POST" else service.exchange_playdevice_picture
    return _dispatch(request, handler)


@api_view(["GET", "PUT"])
@authentication_classes([])
@permission_classes([])
def playdevice_picture(request, fid: int):
    handler = service.get_playdevice_picture if request.method == "GET" else service.put_playdevice_picture
    return _dispatch(request, handler, fid=fid)
