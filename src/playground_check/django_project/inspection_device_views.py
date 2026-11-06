"""DRF routes for native inspection and playdevice commands."""
from __future__ import annotations

from rest_framework.decorators import api_view, authentication_classes, permission_classes

from . import inspection_device_commands


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def create_inspection(request):
    return inspection_device_commands.create_inspection(request)


@api_view(["POST", "PUT"])
@authentication_classes([])
@permission_classes([])
def playdevice(request):
    if request.method == "POST":
        return inspection_device_commands.save_playdevice(request)
    return inspection_device_commands.exchange_playdevice_picture(request)


@api_view(["GET", "PUT"])
@authentication_classes([])
@permission_classes([])
def playdevice_picture(request, fid: int):
    if request.method == "GET":
        return inspection_device_commands.get_playdevice_picture(request, fid)
    return inspection_device_commands.put_playdevice_picture(request, fid)
