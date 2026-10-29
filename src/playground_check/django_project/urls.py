"""Explicit Django API routes; unmigrated requests retain legacy WSGI."""

from django.urls import path

from . import account_document_push_views, defect_views, inspection_device_views

from .views import django_health, health, public_playgrounds, inspection_types, renovation_types, public_playground_detail, playground_by_name, playground_only_names, playground_by_device, playground_by_id, playground_invalid_id, playground_map_image

urlpatterns = [
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
]
