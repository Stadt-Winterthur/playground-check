"""Domain-facing exports for native commands, backed by shared implementations.

Adapters explicitly bind configuration, transactions and detail strategies.
No legacy HTTP handler or WSGI server is imported here.
"""
from __future__ import annotations

from typing import Any, Mapping
from psycopg import Connection

from . import account_identity, defect_serialization, playground_access
from .domain_values import UNAUTHORIZED, DOTNET_MIN_DATE, VALID_ROLES, VALID_RESPONSIBILITIES
from .document_codec import DOCUMENT_NAME_MARKER
from .image_codec import ALLOWED_IMAGE_MIME_TYPES
from .domain_values import _bool, _date_value, _valid_mail_address
from .document_codec import _document_parts, _document_with_name, _document_name_from_tail, _document_storage
from .image_codec import _decode_image, _mime, _image_upload_error, _image_request_too_large
from .assignment_service import _user_name, _record_assignment_change, _assignment_history
from .account_identity import _user_dict
from .defect_serialization import _defect_creator_name
from .playground_access import _playdevice_rows, _criteria, _inspection_history
from playground_check import session_repository
from playground_check.auth import EMAIL, GIVEN_NAME, NAME, ROLE, decode_token, hash_passphrase, issue_token, verify_passphrase
from playground_check.config import settings
from playground_check.upload_limits import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES, IMAGE_REQUEST_MAX_BYTES
from playground_check.db import connect
from playground_check import remaining_reads_repository
from playground_check import user_repository, user_write_repository, document_write_repository, push_repository, assignment_repository, mail_repository, inspection_validation_repository
from playground_check import playground_repository, inspection_defect_repository, playground_detail_service, inspection_defect_service, defect_write_rules, defect_write_repository, inspection_write_repository, picture_write_repository, playdevice_write_repository
from playground_check.http import Request, Response
from playground_check.playground_reads import inspection_suspended as _suspended, public_feature as _public_feature
from playground_check.map_image_queries import map_image_base64
from playground_check.playground_detail_serializers import (
    report_dict as _report_dict,
    criterion_dict as _criterion_dict,
    playdevice_feature,
)


def _request_token(request: Request) -> str:
    return account_identity._request_token(request, config=settings)


def _auth_cookie(token: str, *, clear: bool = False) -> tuple[str, str]:
    return account_identity._auth_cookie(token, config=settings, clear=clear)


def token_user(request: Request, role: str | None = None) -> dict[str, Any] | None:
    return account_identity.token_user(request, role, config=settings)


def current_user(request: Request, role: str | None = None, dry_run: bool = False) -> dict[str, Any] | None:
    return account_identity.current_user(request, role, dry_run, connect_db=connect, config=settings)


def require_user(request: Request, role: str | None = None) -> tuple[dict[str, Any] | None, Response | None]:
    return account_identity.require_user(request, role, resolve_user=current_user)


def revoke_request_session(request: Request) -> None:
    account_identity.revoke_request_session(request, connect_db=connect, config=settings)


def _defect_dict(db: Connection, row: Mapping[str, Any], pictures: bool = True) -> dict[str, Any]:
    return defect_serialization._defect_dict(db, row, pictures,
                                           creator_name=_defect_creator_name, history=_assignment_history)


_priority_two_fields_complete = defect_write_rules.priority_two_fields_complete


def playground_only_names_data(user: Mapping[str, Any] | None, query: Mapping[str, str]) -> list[dict[str, Any]]:
    return playground_access.playground_only_names_data(user, query, connect_db=connect)


def _playdevice(db: Connection, row: Mapping[str, Any], inspection_type: str, with_defects: bool, with_inspections: bool) -> dict[str, Any]:
    return playground_access._playdevice(db, row, inspection_type, with_defects, with_inspections,
                                        load_criteria=_criteria, load_history=_inspection_history,
                                        serialize_defect=_defect_dict)


def _playground_result(db: Connection, row: Mapping[str, Any], inspection_type: str, with_defects: bool, with_inspections: bool) -> dict[str, Any]:
    """Compatibility entry point shared by the legacy and DRF read paths."""
    from .device_detail_batch import build_devices
    devices = _playdevice_rows(db, row["id"])
    features = build_devices(db, devices, inspection_type, with_defects, with_inspections, DOTNET_MIN_DATE)
    return playground_detail_service.build_playground_detail(
        db, row, inspection_type, with_defects, with_inspections,
        load_devices=lambda db, fid: devices,
        build_device=lambda db, item, *args: features[item["fid"]],
        document_name=_document_name_from_tail,
        compatibility_bugs=settings.compatibility_bugs,
        min_date=DOTNET_MIN_DATE,
    )


def playground_by_name_data(query: Mapping[str, str]) -> dict[str, Any]:
    return playground_access.playground_by_name_data(query, connect_db=connect, build_result=_playground_result)


def playground_by_id_data(fid: int, query: Mapping[str, str]) -> dict[str, Any] | None:
    return playground_access.playground_by_id_data(fid, query, connect_db=connect, build_result=_playground_result)


def playground_by_device_data(fid: int) -> dict[str, Any]:
    return playground_access.playground_by_device_data(fid, connect_db=connect,
                                                     load_devices=_playdevice_rows, build_device=_playdevice)
