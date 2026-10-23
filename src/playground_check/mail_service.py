"""Server-side defect notification email through local Postfix (SMTP)."""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from typing import Any, Mapping, Sequence


class MailConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MailAttachment:
    filename: str
    mime: str
    content: bytes


def compose_defect_mail(defect: Mapping[str, Any], device: Mapping[str, Any],
                        recipient: Mapping[str, Any], sender: Mapping[str, Any],
                        attachments: Sequence[MailAttachment]) -> EmailMessage:
    sender_email = (os.getenv("SMTP_FROM") or "").strip()
    if not sender_email or "\n" in sender_email or "\r" in sender_email:
        raise MailConfigurationError("Invalid SMTP_FROM")
    e = lambda value: escape(str(value or ""))
    priority = {1: "A (sofort)", 2: "B (mittelfristig)", 3: "C (im Folgejahr beurteilen)"}.get(defect.get("priority"), "Nicht angegeben")
    responsibility = {1: "Revier", 2: "Spielplatzverantwortlicher", 3: "Projektleiter"}.get(defect.get("responsible_body_id"), "Nicht angegeben")
    year = device.get("construction_date")
    year = getattr(year, "year", None) or "Nicht angegeben"
    sender_name = " ".join(filter(None, [sender.get("firstName"), sender.get("lastName")]))
    details = [
        ("Mangelnummer", defect["tid"]), ("Spielplatz", device.get("playground_name")),
        ("Adresse", device.get("address")), ("Geräteart", device.get("device_type")),
        ("Lieferant", device.get("supplier")), ("Erstellungsjahr", year),
        ("Bemerkung zum Spielgerät", device.get("device_comment") or "Keine Bemerkung"),
        ("Dringlichkeit", priority), ("Zuständigkeit nach Typ", responsibility),
        ("Erstellt am", defect.get("date_creation")),
        ("Status", "Erledigt" if defect.get("date_done") else "Offen"),
    ]
    rows = "".join(f"<tr><td><strong>{e(label)}:</strong></td><td>{e(value) or 'Nicht angegeben'}</td></tr>" for label, value in details)
    def paragraph(value: Any) -> str:
        return e(value).replace("\n", "<br>")
    html = (
        '<!DOCTYPE html><html lang="de"><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.45;color:#222">'
        f'<p>Guten Tag {e(recipient["name"])}</p>'
        '<p><strong>Der folgende Mangel ist pendent:</strong></p>'
        f'<table cellpadding="4" cellspacing="0" style="border-collapse:collapse">{rows}</table>'
        f'<p><strong>Beschrieb des Mangels:</strong><br>{paragraph(defect.get("description") or "Keine Beschreibung")}</p>'
        f'<p><strong>Bemerkung zur Erledigung:</strong><br>{paragraph(defect.get("comment") or "Keine Bemerkung")}</p>'
        f'<p>Freundliche Grüsse<br>{e(sender_name)}</p></body></html>'
    )
    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = recipient["email"]
    message["Subject"] = f'Mangel {defect["tid"]}: {str(defect.get("description") or "Spielgerät").replace(chr(10), " ").replace(chr(13), " ")}'[:240]
    message.set_content("Eine neue Mängelmeldung liegt vor. Bitte HTML-Ansicht verwenden.")
    message.add_alternative(html, subtype="html")
    for attachment in attachments:
        if len(attachment.content) > 10 * 1024 * 1024:
            raise MailConfigurationError("Image attachment exceeds size limit")
        major, minor = attachment.mime.split("/", 1)
        message.add_attachment(attachment.content, maintype=major, subtype=minor, filename=attachment.filename)
    return message


def deliver(message: EmailMessage, recipient: str) -> None:
    host = os.getenv("SMTP_HOST", "localhost")
    raw_port = (os.getenv("SMTP_PORT") or "").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise MailConfigurationError("SMTP_PORT must be a valid integer in .env") from exc
    if not 1 <= port <= 65535:
        raise MailConfigurationError("SMTP_PORT must be between 1 and 65535")
    timeout = float(os.getenv("SMTP_TIMEOUT", "10"))
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        smtp.send_message(message, from_addr=message["From"], to_addrs=[recipient])
