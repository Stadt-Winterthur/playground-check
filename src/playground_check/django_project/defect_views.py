"""DRF boundary for native defect commands, reads and assignments."""
from __future__ import annotations

from rest_framework.decorators import api_view, authentication_classes, permission_classes

from . import defect_commands, defect_native


@api_view(["GET", "POST", "PUT"])
@authentication_classes([])
@permission_classes([])
def defect(request):
    if request.method == "GET":
        return defect_native.get_defect(request)
    if request.method == "POST":
        return defect_commands.update_defect(request)
    return defect_commands.create_defect(request)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def defect_overview(request):
    return defect_native.get_defect_overview(request)


@api_view(["GET", "PUT"])
@authentication_classes([])
@permission_classes([])
def defect_picture(request, tid: int):
    if request.method == "GET":
        return defect_commands.get_defect_picture(request, tid)
    return defect_commands.put_defect_picture(request, tid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_send_mail(request, tid: int):
    return defect_commands.send_info_mail(request, tid)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_accept(request, tid: int):
    return defect_native.assignment_status(request, tid, accepted=True)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def defect_reject(request, tid: int):
    return defect_native.assignment_status(request, tid, accepted=False)
