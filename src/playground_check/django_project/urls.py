"""Native Django UI, API endpoints and compatibility redirects."""

from django.urls import path, re_path
from .frontend import frontend
from .python_ui import (home as python_ui_home, playgrounds as python_ui_playgrounds,
    workspace as python_ui_workspace, assigned_playgrounds as python_ui_assigned,
    playground_detail as python_ui_detail, defects as python_ui_defects,
    inspection_editor as python_ui_inspection, defect_detail as python_ui_defect_detail,
    my_profile as python_ui_profile, push_settings as python_ui_push)

from . import account_document_push_views, defect_views, inspection_device_views

from .views import django_health, health, public_playgrounds, inspection_types, renovation_types, public_playground_detail, playground_by_name, playground_only_names, playground_by_device, playground_by_id, playground_invalid_id, playground_map_image

from . import python_ui_workflows as gui_workflows

urlpatterns = [
    path("login/", gui_workflows.login, name="python-ui-login"),
    path("defect/edit/", gui_workflows.defect_editor, name="python-ui-defect-edit"),
    path("device/edit/", gui_workflows.device_editor, name="python-ui-device-edit"),
    path("device/checkability/", gui_workflows.device_checkability, name="python-ui-device-checkability"),
    path("device/map/", gui_workflows.playdevice_map, name="python-ui-device-map"),
    path("device/photo/", gui_workflows.playdevice_photo, name="python-ui-device-photo"),
    path("document/upload/", gui_workflows.document_editor, name="python-ui-document-upload"),
    path("detail/documents/", gui_workflows.playground_document_action, name="python-ui-playground-documents"),
    path("admin/users/", gui_workflows.admin_users, name="python-ui-admin-users"),
    path("", python_ui_home, name="python-ui-home"),
    path("playgrounds/", python_ui_playgrounds, name="python-ui-playgrounds"),
    path("workspace/", python_ui_workspace, name="python-ui-workspace"),
    path("assigned/", python_ui_assigned, name="python-ui-assigned"),
    path("detail/", python_ui_detail, name="python-ui-detail"),
    path("defects/", python_ui_defects, name="python-ui-defects"),
    path("inspection/", python_ui_inspection, name="python-ui-inspection"),
    path("defect/", python_ui_defect_detail, name="python-ui-defect-detail"),
    path("profile/", python_ui_profile, name="python-ui-profile"),
    path("push/", python_ui_push, name="python-ui-push"),
    path("Account/Login/", account_document_push_views.login, name="account-login"),
    path("Account/Logout/", account_document_push_views.logout, name="account-logout"),
    path("Account/Me/", account_document_push_views.account_me, name="account-me"),
    path("Account/Users/Assignable/", account_document_push_views.assignable_users, name="account-assignable-users"),
    path("Account/Users/", account_document_push_views.users, name="account-users"),
    path("Document/", account_document_push_views.document_create, name="document-create"),
    path("Document/<int:fid>/", account_document_push_views.document_item, name="document-item"),
    path("Document/<int:fid>/Name/", account_document_push_views.document_rename, name="document-rename"),
    path("PushSubscription/Register/", account_document_push_views.push_register, name="push-register"),
    path("PushSubscription/Unregister/", account_document_push_views.push_unregister, name="push-unregister"),
    path("PushSubscription/Me/", account_document_push_views.push_me, name="push-me"),
    path("Inspection/", inspection_device_views.create_inspection, name="inspection-create"),
    path("Playdevice/", inspection_device_views.playdevice, name="playdevice-write"),
    path("Playdevice/<int:fid>/Picture/", inspection_device_views.playdevice_picture, name="playdevice-picture"),
    path("Defect/", defect_views.defect, name="defect"),
    path("Defect/Overview/", defect_views.defect_overview, name="defect-overview"),
    path("Defect/Picture/<int:tid>/", defect_views.defect_picture, name="defect-picture"),
    path("Defect/<int:tid>/send-mail/", defect_views.defect_send_mail, name="defect-send-mail"),
    path("Defect/<int:tid>/accept/", defect_views.defect_accept, name="defect-accept"),
    path("Defect/<int:tid>/reject/", defect_views.defect_reject, name="defect-reject"),
    path("__django/health", django_health, name="django-health"),
    path("api/health", health, name="api-health"),
    path("Inspection/types/", inspection_types, name="inspection-types"),
    path("Inspection/renovationtypes/", renovation_types, name="renovation-types"),
    path("Collections/Playgrounds/Items/", public_playgrounds, name="public-playgrounds"),
    path("Collections/Playgrounds/Items/<str:uuid>/", public_playground_detail, name="public-playground-detail"),
    path("Playground/mapimage/", playground_map_image, name="playground-map-image"),
    path("Playground/byname/", playground_by_name, name="playground-by-name"),
    path("Playground/onlynames/", playground_only_names, name="playground-only-names"),
    path("Playground/byplaydevice/<int:fid>/", playground_by_device, name="playground-by-device"),
    path("Playground/<int:fid>/", playground_by_id, name="playground-by-id"),
    path("Playground/<str:invalid_id>/", playground_invalid_id, name="playground-invalid-id"),
    re_path(r"^(?P<path>.*)$", frontend, name="frontend-fallback"),
]
