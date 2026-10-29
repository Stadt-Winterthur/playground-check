"""Native DRF-facing defect writes, pictures and mail delivery.

Keep the existing PostgreSQL repositories, response contracts, TID allocation
and SMTP transaction boundary; do not dispatch via legacy HTTP handlers.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import date, datetime

from playground_check import domain_support as service
from playground_check.http import Response
from playground_check.mail_service import MailAttachment, MailConfigurationError, compose_defect_mail, deliver

from .api_wire import to_http_response, to_legacy_request


def _authorized(request, **params):
    legacy = to_legacy_request(request, **params)
    user, error = service.require_user(legacy)
    return legacy, user, to_http_response(error) if error is not None else None


def _respond(result):
    return to_http_response(result)


def update_defect(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = legacy.json() or {}
    if not body:
        return _respond(Response.json({"errorMessage": "SPK-4"}))
    if not service._priority_two_fields_complete(body):
        return _respond(Response.json({"errorMessage": "SPK-10"}))
    try:
        responsible = service.defect_write_rules.responsible_user_fid(body)
        date_done = service._date_value(body.get("dateDone"))
        with service.connect() as db:
            current = service.defect_write_repository.current_responsible(db, body.get("tid"))
            if not current:
                return _respond(Response.json({"errorMessage": "SPK-3"}))
            (new_responsible, assignment_changed, status, created, comment) = (
                service.defect_write_rules.update_assignment_fields(
                    body, current.get("responsible_user_fid"), parse_date=service._date_value,
                )
            )
            service.defect_write_repository.update_defect(
                db, body, date_done, service.defect_write_rules.responsible_body_id(body),
                new_responsible, status, created, comment,
                user["fid"] if date_done else None,
            )
            service._record_assignment_change(
                db, int(body.get("tid")), user, current.get("responsible_user_fid"), new_responsible,
            )
        return _respond(Response.json({"errorMessage": ""}))
    except Exception:
        return _respond(Response.json({"errorMessage": "SPK-3"}))


def create_defect(request):
    legacy, user, denied = _authorized(request)
    if denied is not None:
        return denied
    body = legacy.json() or {}
    body.pop("done", None)
    if not body.get("defectDescription"):
        return _respond(Response.json(body))
    if not service._priority_two_fields_complete(body):
        body["errorMessage"] = "SPK-10"
        return _respond(Response.json(body))
    try:
        responsible = service.defect_write_rules.responsible_user_fid(body)
        date_done = date.today() if body.get("dateDone") is not None else None
        with service.connect() as db:
            row = service.defect_write_repository.insert_defect(
                db, body, user, date_done, responsible,
                service.defect_write_rules.responsible_body_id(body),
                datetime.now() if responsible > 0 else None,
            )
            if responsible > 0:
                service._record_assignment_change(db, int(row["tid"]), user, None, responsible)
            body["assignmentHistory"] = service._assignment_history(db, int(row["tid"]))
        body["tid"] = row["tid"]
        body.setdefault("errorMessage", "")
    except Exception:
        body["errorMessage"] = "SPK-3"
    return _respond(Response.json(body))


def get_defect_picture(request, tid: int):
    legacy = to_legacy_request(request, tid=tid)
    # Original dry-run behavior intentionally bypasses authentication and DB.
    if service._bool(legacy.query.get("dryRun")):
        return _respond(Response(b"", 200, "application/json; charset=utf-8"))
    _, error = service.require_user(legacy)
    if error is not None:
        return _respond(error)
    with service.connect() as db:
        row = service.remaining_reads_repository.defect_picture(
            db, tid, service._bool(legacy.query.get("thumb")),
        )
    if not row or row["value"] is None:
        return _respond(Response.text("Kein Bild vorhanden.", 404))
    data, mime = service._decode_image(row["value"])
    return _respond(Response.file(data, mime) if data else Response.text("Kein Bild vorhanden.", 404))


def put_defect_picture(request, tid: int):
    legacy, _, denied = _authorized(request, tid=tid)
    if denied is not None:
        return denied
    if service._image_request_too_large(legacy):
        return _respond(Response.text("Bild-Upload ist zu gross.", 413))
    body = legacy.json() or {}
    picture = body.get("base64StringPicture") or ""
    thumbnail = body.get("base64StringPictureThumb") or ""
    for value in (picture, thumbnail):
        error = service._image_upload_error(value)
        if error:
            return _respond(Response.text(error, 400))
    with service.connect() as db:
        row = service.picture_write_repository.insert_defect_picture(
            db, tid, picture, thumbnail, service._bool(body.get("afterFixing")),
        )
    return _respond(Response.json({"tid": row["tid"]}) if row else Response(b"", 400))


def send_info_mail(request, tid: int):
    _, user, denied = _authorized(request, tid=tid)
    if denied is not None:
        return denied
    try:
        with service.connect() as db:
            row = service.mail_repository.defect(db, tid)
            if not row:
                return _respond(Response.text("Mangel nicht gefunden.", 404))
            recipient = service.mail_repository.recipient(db, row.get("responsible_user_fid"))
            if not recipient or not recipient.get("active") or not recipient.get("email") or not service._valid_mail_address(recipient["email"]):
                return _respond(Response.text("Die zuständige Person hat keine gültige aktive E-Mail-Adresse.", 400))
            device_row = service.mail_repository.device(db, row["playdevice_fid"])
            if not device_row:
                return _respond(Response.text("Zugehöriges Spielgerät nicht gefunden.", 404))
            pictures = service.mail_repository.pictures(db, tid)
            attachments = []
            for index, picture in enumerate(pictures, 1):
                data, mime = service._decode_image(picture.get("picture"))
                if data:
                    if mime not in service.ALLOWED_IMAGE_MIME_TYPES:
                        return _respond(Response.text("Ungültiger Bildtyp in den Mängelfotos.", 400))
                    ext = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}[mime]
                    attachments.append(MailAttachment(f"Mangel-{tid}-Foto-{index}.{ext}", mime, data))
            message = compose_defect_mail(row, device_row, recipient, user, attachments)
            recipient_fid = recipient["fid"]
        # SMTP is outside the database transaction. Only mark sent after success.
        deliver(message, recipient["email"])
        with service.connect() as db:
            service.mail_repository.mark_sent(db, tid, recipient["name"], recipient_fid)
            updated = service.mail_repository.defect(db, tid)
            result = service._defect_dict(db, updated) if updated else None
        return _respond(Response.json(result))
    except (OSError, TimeoutError, MailConfigurationError, smtplib.SMTPException) as exc:
        logging.getLogger(__name__).error("Infomail for defect %s failed: %s", tid, exc)
        return _respond(Response.text("Infomail konnte nicht an den Mailserver übergeben werden.", 502))
    except Exception:
        logging.getLogger(__name__).exception("Infomail error for defect %s", tid)
        return _respond(Response.text("Infomail konnte nicht abgeschlossen werden. Bitte Versandstatus prüfen.", 500))
